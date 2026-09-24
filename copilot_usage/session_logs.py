"""Copilot CLI's per-session events.jsonl logs, the only source for spend older than session-store.db."""
import glob
import json
import os
from collections import defaultdict

from . import cache
from .config import SESSIONS
from .records import blank_record

RELEVANT = tuple(
    '{"type":"session.%s"' % kind
    for kind in ("start", "model_change", "usage_checkpoint", "shutdown")
)


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


def load_sessions():
    sessions = {}
    for path in glob.glob(os.path.join(SESSIONS, "*", "events.jsonl")):
        stat = os.stat(path)
        stamp = (stat.st_mtime_ns, stat.st_size)
        if cache.entries.get(path, (None,))[0] != stamp:
            cache.entries[path] = (stamp, parse_session(path))
        sessions[os.path.basename(os.path.dirname(path))] = cache.entries[path][1]
    return sessions


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


def session_name(folder):
    try:
        with open(os.path.join(folder, "workspace.yaml"), encoding="utf-8", errors="replace") as f:
            for line in f:
                if line.startswith("name:"):
                    return line[5:].strip()
    except OSError:
        pass
    return os.path.basename(folder)[:8]
