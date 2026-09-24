#!/usr/bin/env python3
"""Copilot usage per model, from Copilot CLI's ~/.copilot session-store.db and session logs,
plus opencode sessions that use the GitHub Copilot provider.

  copilot-usage [--since YYYY-MM-DD] [--by month|day|repo|branch]   print a table
  copilot-usage serve [--port 8765] [--budget AIC]                   live dashboard
"""
import argparse
import ctypes
import glob
import json
import os
import re
import sqlite3
import subprocess
import time
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

NANO = 1e9  # 1 AIU (= 1 AI credit = $0.01) is 1e9 nanoAIU
SESSIONS = os.path.expanduser("~/.copilot/session-state")
DB = os.path.expanduser("~/.copilot/session-store.db")
OPENCODE_DB = os.path.join(os.environ.get("XDG_DATA_HOME") or os.path.expanduser("~/.local/share"),
                           "opencode", "opencode.db")
HERE = os.path.dirname(os.path.realpath(__file__))
BURN_MINUTES = 15
BUDGET = None  # monthly AIC budget, set by serve --budget

# First match wins. Edit to match how your org classifies models.
TIER_RULES = [
    ("light", r"haiku|mini|flash|luna|nano"),
    ("premium", r"opus|-sol"),
    ("standard", r""),
]

RELEVANT = tuple(
    '{"type":"session.%s"' % kind
    for kind in ("start", "model_change", "usage_checkpoint", "shutdown")
)


def tier_of(model):
    return next(tier for tier, pattern in TIER_RULES if re.search(pattern, model))


def local_day_hour(ts):
    moment = datetime.fromisoformat(ts.replace("Z", "+00:00")).astimezone()
    return moment.strftime("%Y-%m-%d"), moment.hour


def parse_session(path):
    """Turn one events.jsonl into spend increments.

    Per-model totals only land on session.shutdown, so checkpoints (session-wide
    running totals) are credited to the active model as they arrive, then the
    shutdown reconciles per model. Counters are cumulative per session but
    sometimes restart after a resume, so a drop is treated as a fresh counter.
    """
    deltas = []
    prev = defaultdict(lambda: {"aiu": 0, "calls": 0, "tok": {}})
    credited = defaultdict(int)
    last_total = 0
    model, repo = "unknown", "-"

    with open(path, encoding="utf-8", errors="replace") as lines:
        for line in lines:
            if not line.startswith(RELEVANT):
                continue
            try:
                event = json.loads(line)
            except ValueError:
                continue
            kind, data, ts = event["type"], event.get("data", {}), event.get("timestamp", "")

            if kind == "session.start":
                ctx = data.get("context") or {}
                repo = ctx.get("repository") or os.path.basename(ctx.get("cwd") or "-")
            elif kind == "session.model_change":
                model = data.get("newModel", model)
            elif kind == "session.usage_checkpoint":
                total = data.get("totalNanoAiu", 0)
                if total < last_total:
                    last_total = 0
                if total > last_total:
                    deltas.append((ts, model, total - last_total, 0, {}))
                    credited[model] += total - last_total
                    last_total = total
            elif kind == "session.shutdown":
                metrics_by_model = data.get("modelMetrics", {})
                for name, metrics in metrics_by_model.items():
                    before = prev[name]
                    aiu = metrics.get("totalNanoAiu", 0)
                    calls = metrics.get("requests", {}).get("count", 0)
                    usage = metrics.get("usage", {})
                    if aiu < before["aiu"] or calls < before["calls"]:
                        before = {"aiu": 0, "calls": 0, "tok": {}}
                    tokens = {k: v - before["tok"].get(k, 0) for k, v in usage.items()}
                    deltas.append((ts, name, aiu - before["aiu"] - credited.pop(name, 0),
                                   calls - before["calls"], tokens))
                    prev[name] = {"aiu": aiu, "calls": calls, "tok": usage}
                for name, aiu in credited.items():
                    deltas.append((ts, name, -aiu, 0, {}))
                credited.clear()
                last_total = data.get("totalNanoAiu", 0)
                model = data.get("currentModel", model)

    return {"deltas": deltas, "repo": repo, "model": model}


_cache = {}


def load_sessions():
    sessions = {}
    for path in glob.glob(os.path.join(SESSIONS, "*", "events.jsonl")):
        stat = os.stat(path)
        stamp = (stat.st_mtime_ns, stat.st_size)
        if _cache.get(path, (None,))[0] != stamp:
            _cache[path] = (stamp, parse_session(path))
        sessions[os.path.basename(os.path.dirname(path))] = _cache[path][1]
    return sessions


def file_stamp(path):
    try:
        stat = os.stat(path)
        return stat.st_mtime_ns, stat.st_size
    except OSError:
        return None


SUMS = ("aiu", "calls", "prompts", "in", "out", "cache", "cache_write", "reasoning", "ms",
        "out_timed", "premium", "c_input", "c_cache_read", "c_cache_write", "c_output", "saved",
        "itl", "itl_n", "filtered")
LISTS = ("ttft", "ottft", "dur")  # per-call milliseconds, kept raw so the dashboard can take percentiles
NANO_SUMS = ("c_input", "c_cache_read", "c_cache_write", "c_output", "saved")
KEYS = ("day", "hour", "session", "model", "initiator", "effort", "endpoint", "finish")
TOKEN_KINDS = ("input", "cache_read", "cache_write", "output")


def blank_record(**fields):
    return {**dict.fromkeys(SUMS, 0), **{name: [] for name in LISTS}, **fields}


def token_costs(details_json):
    """nanoAIU per token kind, plus what the cache reads would have cost extra at the input price."""
    try:
        details = {d["tokenType"]: d for d in json.loads(details_json or "[]")}
        rate = {kind: d["costPerBatch"] / d["batchSize"] for kind, d in details.items()}
        costs = {kind: details[kind]["tokenCount"] * rate[kind] if kind in details else 0
                 for kind in TOKEN_KINDS}
        saved = 0
        if "input" in rate and "cache_read" in rate:
            saved = details["cache_read"]["tokenCount"] * (rate["input"] - rate["cache_read"])
        return costs, max(0, saved)
    except (ValueError, TypeError, KeyError, ZeroDivisionError):
        return dict.fromkeys(TOKEN_KINDS, 0), 0


def call_record(row):
    costs, saved = token_costs(row["token_details_json"])
    ms = row["duration_ms"] or 0
    itl = row["inter_token_latency_ms"]
    return blank_record(**{
        "session": row["session_id"], "ts": row["created_at"].replace(" ", "T"), "model": row["model"],
        "initiator": row["initiator"] or "other", "effort": row["reasoning_effort"] or "unknown",
        "endpoint": row["api_endpoint"] or "unknown", "finish": row["finish_reason"] or "unknown",
        "aiu": row["total_nano_aiu"] or 0, "calls": 1, "prompts": int(row["initiator"] == "user"),
        "in": row["input_tokens"] or 0, "out": row["output_tokens"] or 0,
        "cache": row["cache_read_tokens"] or 0, "cache_write": row["cache_write_tokens"] or 0,
        "reasoning": row["reasoning_tokens"] or 0, "ms": ms,
        "out_timed": (row["output_tokens"] or 0) if ms else 0,
        # Premium-request billing only charges the multiplier on user-initiated calls.
        "premium": (row["request_multiplier"] or 0) if row["initiator"] == "user" else 0,
        **{"c_" + kind: cost for kind, cost in costs.items()}, "saved": saved,
        "itl": round(itl or 0, 2), "itl_n": int(itl is not None),
        "filtered": row["content_filter_triggered"] or 0,
        "ttft": [round(row["time_to_first_token_ms"])] if row["time_to_first_token_ms"] is not None else [],
        "ottft": [round(row["output_ttft_ms"])] if row["output_ttft_ms"] is not None else [],
        "dur": [ms] if ms else [],
    })


def epoch(ts):
    if not ts:
        return None
    moment = datetime.fromisoformat(ts.replace("Z", "+00:00").replace(" ", "T"))
    return (moment if moment.tzinfo else moment.replace(tzinfo=timezone.utc)).timestamp()


SESSION_COUNTS = {
    "turns": "SELECT session_id, COUNT(*) FROM turns GROUP BY 1",
    "checkpoints": "SELECT session_id, COUNT(*) FROM checkpoints GROUP BY 1",
    "files": "SELECT session_id, COUNT(*) FROM session_files GROUP BY 1",
    "prs": "SELECT session_id, COUNT(*) FROM session_refs WHERE ref_type = 'pr' GROUP BY 1",
    "commits": "SELECT session_id, COUNT(*) FROM session_refs WHERE ref_type = 'commit' GROUP BY 1",
    "subagents": "SELECT session_id, COUNT(DISTINCT agent_id) FROM assistant_usage_events GROUP BY 1",
    "tool_runs": "SELECT session_id, COUNT(*) FROM forge_trajectory_events WHERE exit_code IS NOT NULL GROUP BY 1",
    "tool_fails": "SELECT session_id, COUNT(*) FROM forge_trajectory_events WHERE exit_code != 0 GROUP BY 1",
}


def session_meta(conn):
    meta = {}
    for row in conn.execute("SELECT * FROM sessions"):
        meta[row["id"]] = {
            "repo": row["repository"] or os.path.basename(row["cwd"] or "") or "-",
            "branch": row["branch"] or "-", "host": row["host_type"] or "unknown", "client": "Copilot CLI",
            "summary": (row["summary"] or "").strip().split("\n")[0][:120],
            "start": epoch(row["created_at"]), "end": epoch(row["updated_at"]),
        }
    for field, query in SESSION_COUNTS.items():
        try:
            for session_id, count in conn.execute(query):
                if session_id in meta:
                    meta[session_id][field] = count
        except sqlite3.Error:  # older CLI versions lack some of these tables
            pass
    return meta


def copilot_prices(conn):
    """Latest nanoAIU-per-token rates and premium multiplier per model, as Copilot CLI last saw them."""
    prices = {}
    for row in conn.execute("SELECT model, initiator, request_multiplier, token_details_json "
                            "FROM assistant_usage_events ORDER BY created_at"):
        try:
            details = json.loads(row["token_details_json"] or "[]")
        except ValueError:
            details = []
        price = prices.setdefault(row["model"], {"rates": {}, "multiplier": 0})
        for d in details:
            try:
                price["rates"][d["tokenType"]] = d["costPerBatch"] / d["batchSize"]
            except (KeyError, TypeError, ZeroDivisionError):
                pass
        if row["initiator"] == "user" and row["request_multiplier"] is not None:
            price["multiplier"] = row["request_multiplier"]
    return prices


def db_load():
    """(one record per model call, metadata per session, prices per model) from session-store.db
    (exists since CLI ~1.0.7x)."""
    stamp = (file_stamp(DB), file_stamp(DB + "-wal"))
    if _cache.get(DB, (None,))[0] == stamp:
        return _cache[DB][1]
    try:
        conn = sqlite3.connect(f"{Path(DB).as_uri()}?mode=ro", uri=True, timeout=2)
        conn.row_factory = sqlite3.Row
        calls = [call_record(row) for row in
                 conn.execute("SELECT * FROM assistant_usage_events ORDER BY created_at")]
        meta = session_meta(conn)
        prices = copilot_prices(conn)
        conn.close()
    except (sqlite3.Error, IndexError):
        return _cache.get(DB, (None, ([], {}, {})))[1]
    _cache[DB] = (stamp, (calls, meta, prices))
    return calls, meta, prices


def iso_ms(ms):
    return datetime.fromtimestamp(ms / 1000, timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


_remotes = {}


def git_repo(directory):
    """(owner/name, host) from the origin remote, like Copilot CLI records it."""
    if directory not in _remotes:
        try:
            url = subprocess.run(["git", "-C", directory, "config", "--get", "remote.origin.url"],
                                 capture_output=True, text=True, timeout=5).stdout.strip()
        except (OSError, subprocess.SubprocessError):
            url = ""
        match = re.search(r"[:/]([^/:]+/[^/]+?)(?:\.git)?/?$", url)
        _remotes[directory] = (match.group(1) if match else os.path.basename(directory) or "-",
                               "github" if "github.com" in url else "unknown")
    return _remotes[directory]


def opencode_call(data, session_id, initiator, prices):
    tokens = data.get("tokens") or {}
    cache = tokens.get("cache") or {}
    counts = {"input": tokens.get("input", 0), "cache_read": cache.get("read", 0),
              "cache_write": cache.get("write", 0),
              # Copilot counts reasoning as output; opencode keeps it separate.
              "output": tokens.get("output", 0) + tokens.get("reasoning", 0)}
    model = data["model"]["id"]
    price = prices.get(model, {"rates": {}, "multiplier": 0})
    rates = price["rates"]
    if rates:
        costs = {kind: counts[kind] * rates.get(kind, 0) for kind in TOKEN_KINDS}
        aiu = sum(costs.values())
        saved = counts["cache_read"] * max(0, rates.get("input", 0) - rates.get("cache_read", 0))
    else:
        # opencode's own price table leaves out cache writes, so this undercounts.
        costs, aiu, saved = dict.fromkeys(TOKEN_KINDS, 0), (data.get("cost") or 0) * 100 * NANO, 0
    times = data.get("time") or {}
    ms = max(0, times["completed"] - times["created"]) if times.get("completed") else 0
    return blank_record(**{
        "session": session_id, "ts": iso_ms(times["created"]), "model": model, "initiator": initiator,
        "effort": data["model"].get("variant") or "unknown", "endpoint": "unknown",
        "finish": (data.get("finish") or "unknown").replace("-", "_"),
        "aiu": round(aiu), "calls": 1, "prompts": int(initiator == "user"),
        "in": sum(counts[kind] for kind in ("input", "cache_read", "cache_write")),
        "out": counts["output"], "cache": counts["cache_read"], "cache_write": counts["cache_write"],
        "reasoning": tokens.get("reasoning", 0), "ms": ms, "out_timed": counts["output"] if ms else 0,
        "premium": price["multiplier"] if initiator == "user" else 0,
        **{"c_" + kind: cost for kind, cost in costs.items()}, "saved": saved,
        "dur": [ms] if ms else [],
    })


def opencode_load(prices):
    """(records, metadata) for opencode calls billed to GitHub Copilot, from opencode.db (opencode 2.x)."""
    stamp = (file_stamp(OPENCODE_DB), file_stamp(OPENCODE_DB + "-wal"), file_stamp(DB), file_stamp(DB + "-wal"))
    if _cache.get(OPENCODE_DB, (None,))[0] == stamp:
        return _cache[OPENCODE_DB][1]
    if stamp[0] is None:
        return [], {}
    try:
        conn = sqlite3.connect(f"{Path(OPENCODE_DB).as_uri()}?mode=ro", uri=True, timeout=2)
        conn.row_factory = sqlite3.Row
        sessions = {row["id"]: row for row in conn.execute("SELECT * FROM session_v2")}
        messages = conn.execute("SELECT session_id, type, data FROM session_message "
                                "WHERE type IN ('user', 'assistant') ORDER BY session_id, seq").fetchall()
        conn.close()
    except sqlite3.Error:
        return _cache.get(OPENCODE_DB, (None, ([], {})))[1]

    def root(session_id):
        while sessions.get(session_id) is not None and sessions[session_id]["parent_id"] in sessions:
            session_id = sessions[session_id]["parent_id"]
        return session_id

    calls, meta, prompted, turns, subagents = [], {}, set(), defaultdict(int), defaultdict(int)
    for session_id, row in sessions.items():
        if row["parent_id"]:
            subagents[root(session_id)] += 1
    for message in messages:
        session_id = message["session_id"]
        if message["type"] == "user":
            prompted.add(session_id)
            turns[session_id] += 1
            continue
        first_after_prompt = session_id in prompted
        prompted.discard(session_id)
        try:
            data = json.loads(message["data"])
            if not data["model"]["providerID"].startswith("github-copilot"):
                continue
        except (ValueError, KeyError, TypeError, AttributeError):
            continue
        top = root(session_id)
        if top != session_id:
            initiator = "sub-agent"
        elif first_after_prompt:
            initiator = "user"
        else:
            initiator = "agent"
        try:
            calls.append(opencode_call(data, top, initiator, prices))
        except (KeyError, TypeError):
            continue

    for session_id in {call["session"] for call in calls}:
        row = sessions[session_id]
        repo, host = git_repo(row["directory"])
        meta[session_id] = {
            "repo": repo, "branch": "-", "host": host, "client": "opencode",
            "summary": (row["title"] or "").strip()[:120],
            "start": row["time_created"] / 1000, "end": row["time_updated"] / 1000,
            "turns": turns[session_id], "subagents": subagents[session_id],
            **({"files": row["summary_files"]} if row["summary_files"] is not None else {}),
        }
    _cache[OPENCODE_DB] = (stamp, (calls, meta))
    return calls, meta


def load_calls():
    calls, meta, prices = db_load()
    opencode_calls, opencode_meta = opencode_load(prices)
    return calls + opencode_calls, {**meta, **opencode_meta}


def log_records(sessions, db_start):
    """Records from events.jsonl, only for spend the database doesn't cover."""
    for session_id, session in sessions.items():
        cutoff = db_start.get(session_id)
        for ts, model, aiu, calls, tok in session["deltas"]:
            if cutoff and ts >= cutoff:
                continue
            yield blank_record(
                session=session_id, ts=ts, model=model, initiator="unknown", effort="unknown",
                endpoint="unknown", finish="unknown", aiu=aiu, calls=calls,
                **{"in": tok.get("inputTokens", 0)}, out=tok.get("outputTokens", 0),
                cache=tok.get("cacheReadTokens", 0), cache_write=tok.get("cacheWriteTokens", 0),
                reasoning=tok.get("reasoningTokens", 0))


def all_records(sessions):
    calls, _meta = load_calls()
    db_start = {}
    for record in calls:
        db_start.setdefault(record["session"], record["ts"])
    return calls + list(log_records(sessions, db_start))


def usage_rows(records):
    rows = {}
    for record in records:
        day, hour = local_day_hour(record["ts"])
        key = (day, hour, *(record[k] for k in KEYS[2:]))
        row = rows.get(key)
        if row is None:
            row = rows[key] = blank_record()
        for name in SUMS:
            row[name] += record[name]
        for name in LISTS:
            row[name] += record[name]
    return rows


def session_name(folder):
    try:
        with open(os.path.join(folder, "workspace.yaml"), encoding="utf-8", errors="replace") as f:
            for line in f:
                if line.startswith("name:"):
                    return line[5:].strip()
    except OSError:
        pass
    return os.path.basename(folder)[:8]


def session_info(session_ids, sessions, meta):
    info = {}
    for session_id in session_ids:
        known = meta.get(session_id, {})
        info[session_id] = {
            "repo": sessions.get(session_id, {}).get("repo", "-"), "branch": "-", "host": "unknown",
            **known,
            "label": known.get("summary") or session_name(os.path.join(SESSIONS, session_id)),
        }
    return info


def process_alive(pid):
    try:
        pid = int(pid)
    except ValueError:
        return False
    if os.name == "nt":
        query_limited_information, still_active = 0x1000, 259
        kernel32 = ctypes.windll.kernel32
        handle = kernel32.OpenProcess(query_limited_information, False, pid)
        if not handle:
            return False
        exit_code = ctypes.c_ulong()
        kernel32.GetExitCodeProcess(handle, ctypes.byref(exit_code))
        kernel32.CloseHandle(handle)
        return exit_code.value == still_active
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        pass
    return True


def active_sessions(sessions, records, info):
    recent_from = (datetime.now(timezone.utc) - timedelta(minutes=BURN_MINUTES)).strftime("%Y-%m-%dT%H:%M:%S")
    spend, recent, latest = defaultdict(int), defaultdict(int), {}
    for record in records:
        session_id = record["session"]
        spend[session_id] += record["aiu"]
        if record["ts"] >= recent_from:
            recent[session_id] += record["aiu"]
        if record["ts"] >= latest.get(session_id, ("",))[0]:
            latest[session_id] = (record["ts"], record["model"])

    active = []
    for lock in glob.glob(os.path.join(SESSIONS, "*", "inuse.*.lock")):
        pid = lock.rsplit(".", 2)[1]
        folder = os.path.dirname(lock)
        session_id = os.path.basename(folder)
        if session_id not in sessions or not process_alive(pid):
            continue
        current = latest.get(session_id, ("", sessions[session_id]["model"]))[1]
        details = info.get(session_id, {})
        active.append({
            "id": session_id,
            "name": session_name(folder),
            "repo": details.get("repo") or sessions[session_id]["repo"],
            "branch": details.get("branch", "-"),
            "model": current,
            "tier": tier_of(current),
            "aic": spend[session_id] / NANO,
            "burn": recent[session_id] / NANO * 60 / BURN_MINUTES,
            "last": os.path.getmtime(os.path.join(folder, "events.jsonl")),
        })
    return sorted(active, key=lambda s: -s["last"])


def data_version():
    return str(hash(tuple(sorted((path, stamp) for path, (stamp, _) in _cache.items()))))


_built = {}


def usage_data():
    sessions = load_sessions()
    _calls, meta = load_calls()
    version = data_version()
    if _built.get("version") != version:
        records = all_records(sessions)
        rows = sorted(usage_rows(records).items())
        info = session_info({key[2] for key, _ in rows}, sessions, meta)
        in_aic = ("aiu",) + NANO_SUMS
        _built.update(version=version, sessions=sessions, records=records, data={
            "fields": list(KEYS) + ["aic" if name == "aiu" else name for name in SUMS] + list(LISTS),
            "rows": [[*key, *(round(row[name] / NANO, 3) if name in in_aic else row[name] for name in SUMS),
                      *(row[name] for name in LISTS)] for key, row in rows],
            "sessions": info,
            "tiers": {model: tier_of(model) for model in {key[3] for key, _ in rows}},
        })
    return _built


def api_payload(known_version=""):
    built = usage_data()
    payload = {"now": time.time(), "version": built["version"], "budget": BUDGET,
               "burn_minutes": BURN_MINUTES,
               "active": active_sessions(built["sessions"], built["records"], built["data"]["sessions"])}
    if known_version != built["version"]:
        payload.update(built["data"])
    return payload


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        url = urlparse(self.path)
        if url.path == "/api/usage":
            known = parse_qs(url.query).get("v", [""])[0]
            self.reply(json.dumps(api_payload(known), separators=(",", ":")).encode(), "application/json")
        elif url.path == "/":
            with open(os.path.join(HERE, "dashboard.html"), "rb") as f:
                self.reply(f.read(), "text/html; charset=utf-8")
        else:
            self.send_error(404)

    def reply(self, body, content_type):
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


def serve(port):
    print("Indexing session logs...")
    usage_data()
    print(f"Dashboard at http://localhost:{port}  (Ctrl+C to stop)")
    ThreadingHTTPServer(("127.0.0.1", port), Handler).serve_forever()


def print_table(since, by):
    sessions = load_sessions()
    _calls, meta = load_calls()
    detail = lambda session_id, field: (meta.get(session_id, {}).get(field)
                                        or sessions.get(session_id, {}).get(field, "-"))
    group_of = {"month": lambda day, session_id: day[:7], "day": lambda day, session_id: day,
                "repo": lambda day, session_id: detail(session_id, "repo"),
                "branch": lambda day, session_id: f"{detail(session_id, 'repo')} @ {detail(session_id, 'branch')}"}[by]
    groups = defaultdict(lambda: defaultdict(lambda: defaultdict(int)))
    for (day, _hour, session_id, model, *_rest), row in usage_rows(all_records(sessions)).items():
        if day < since:
            continue
        for field in ("aiu", "calls", "in", "out", "cache"):
            groups[group_of(day, session_id)][model][field] += row[field]

    for key in sorted(groups):
        models = groups[key]
        total = sum(m["aiu"] for m in models.values()) or 1
        print(f"\n{key}   {total / NANO:,.0f} AIC  (${total / NANO / 100:,.2f})")
        print(f"  {'model':<24}{'tier':<10}{'AIC':>10}{'share':>8}{'calls':>8}"
              f"{'in(M)':>9}{'cached':>8}{'out(M)':>8}")
        for model, m in sorted(models.items(), key=lambda kv: -kv[1]["aiu"]):
            cached = f"{m['cache'] / m['in']:.0%}" if m["in"] else "-"
            print(f"  {model:<24}{tier_of(model):<10}{m['aiu'] / NANO:>10,.0f}"
                  f"{m['aiu'] / total:>8.0%}{m['calls']:>8,}"
                  f"{m['in'] / 1e6:>9.1f}{cached:>8}{m['out'] / 1e6:>8.2f}")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    parser.add_argument("command", nargs="?", choices=["serve"])
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--since", default="", help="YYYY-MM-DD")
    parser.add_argument("--by", choices=["month", "day", "repo", "branch"], default="month")
    parser.add_argument("--budget", type=float, help="monthly AIC budget to track on the dashboard")
    args = parser.parse_args()

    if args.command == "serve":
        global BUDGET
        BUDGET = args.budget
        try:
            serve(args.port)
        except KeyboardInterrupt:
            pass
    else:
        print_table(args.since, args.by)


if __name__ == "__main__":
    main()
