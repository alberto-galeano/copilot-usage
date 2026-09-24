"""opencode sessions billed to the GitHub Copilot provider, from opencode.db (opencode 2.x)."""
import json
import os
import re
import sqlite3
import subprocess
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

from . import cache
from .config import DB, NANO, OPENCODE_DB
from .records import TOKEN_KINDS, blank_record


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
    cache_tokens = tokens.get("cache") or {}
    counts = {"input": tokens.get("input", 0), "cache_read": cache_tokens.get("read", 0),
              "cache_write": cache_tokens.get("write", 0),
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
    """(records, metadata) for opencode calls billed to GitHub Copilot."""
    stamp = (cache.file_stamp(OPENCODE_DB), cache.file_stamp(OPENCODE_DB + "-wal"),
             cache.file_stamp(DB), cache.file_stamp(DB + "-wal"))
    if cache.entries.get(OPENCODE_DB, (None,))[0] == stamp:
        return cache.entries[OPENCODE_DB][1]
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
        return cache.entries.get(OPENCODE_DB, (None, ([], {})))[1]

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
    cache.entries[OPENCODE_DB] = (stamp, (calls, meta))
    return calls, meta
