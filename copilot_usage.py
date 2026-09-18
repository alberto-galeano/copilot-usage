#!/usr/bin/env python3
"""Copilot CLI usage per model, from ~/.copilot/session-state/*/events.jsonl.

  copilot-usage [--since YYYY-MM-DD] [--by month|day|repo]   print a table
  copilot-usage serve [--port 8765]                          live dashboard
"""
import argparse
import glob
import json
import os
import re
import time
from collections import defaultdict
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

NANO = 1e9  # 1 AIU (= 1 AI credit = $0.01) is 1e9 nanoAIU
SESSIONS = os.path.expanduser("~/.copilot/session-state")
HERE = os.path.dirname(os.path.realpath(__file__))

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


def local_day(ts):
    return datetime.fromisoformat(ts.replace("Z", "+00:00")).astimezone().strftime("%Y-%m-%d")


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

    with open(path, errors="replace") as lines:
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
        sessions[path] = _cache[path][1]
    return sessions


def usage_rows(sessions):
    rows = defaultdict(lambda: {"aiu": 0, "calls": 0, "in": 0, "out": 0, "cache": 0})
    for session in sessions.values():
        for ts, model, aiu, calls, tok in session["deltas"]:
            row = rows[(local_day(ts), model, session["repo"])]
            row["aiu"] += aiu
            row["calls"] += calls
            row["in"] += tok.get("inputTokens", 0)
            row["out"] += tok.get("outputTokens", 0)
            row["cache"] += tok.get("cacheReadTokens", 0)
    return rows


def session_name(folder):
    try:
        with open(os.path.join(folder, "workspace.yaml")) as f:
            for line in f:
                if line.startswith("name:"):
                    return line[5:].strip()
    except OSError:
        pass
    return os.path.basename(folder)[:8]


def active_sessions(sessions):
    active = []
    for lock in glob.glob(os.path.join(SESSIONS, "*", "inuse.*.lock")):
        pid = lock.rsplit(".", 2)[1]
        folder = os.path.dirname(lock)
        session = sessions.get(os.path.join(folder, "events.jsonl"))
        if not session or not os.path.exists(f"/proc/{pid}"):
            continue
        active.append({
            "name": session_name(folder),
            "repo": session["repo"],
            "model": session["model"],
            "tier": tier_of(session["model"]),
            "aic": sum(d[2] for d in session["deltas"]) / NANO,
            "last": os.path.getmtime(os.path.join(folder, "events.jsonl")),
        })
    return sorted(active, key=lambda s: -s["last"])


def api_payload():
    sessions = load_sessions()
    rows = [
        {"day": day, "model": model, "tier": tier_of(model), "aic": r["aiu"] / NANO,
         "calls": r["calls"], "in": r["in"], "out": r["out"], "cache": r["cache"]}
        for (day, model, _repo), r in sorted(usage_rows(sessions).items())
    ]
    return {"now": time.time(), "rows": rows, "active": active_sessions(sessions)}


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/api/usage":
            self.reply(json.dumps(api_payload()).encode(), "application/json")
        elif self.path == "/":
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
    load_sessions()
    print(f"Dashboard at http://localhost:{port}  (Ctrl+C to stop)")
    ThreadingHTTPServer(("127.0.0.1", port), Handler).serve_forever()


def print_table(since, by):
    key_index = {"month": lambda day, repo: day[:7], "day": lambda day, repo: day,
                 "repo": lambda day, repo: repo}[by]
    groups = defaultdict(lambda: defaultdict(lambda: defaultdict(int)))
    for (day, model, repo), row in usage_rows(load_sessions()).items():
        if day < since:
            continue
        for field, value in row.items():
            groups[key_index(day, repo)][model][field] += value

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
    parser.add_argument("--by", choices=["month", "day", "repo"], default="month")
    args = parser.parse_args()

    if args.command == "serve":
        try:
            serve(args.port)
        except KeyboardInterrupt:
            pass
    else:
        print_table(args.since, args.by)


if __name__ == "__main__":
    main()
