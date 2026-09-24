"""Copilot CLI's session-store.db: one row per model call (exists since CLI ~1.0.7x)."""
import json
import os
import sqlite3
from pathlib import Path

from . import cache
from .config import DB
from .records import TOKEN_KINDS, blank_record, epoch


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
    """(one record per model call, metadata per session, prices per model)."""
    stamp = (cache.file_stamp(DB), cache.file_stamp(DB + "-wal"))
    if cache.entries.get(DB, (None,))[0] == stamp:
        return cache.entries[DB][1]
    try:
        conn = sqlite3.connect(f"{Path(DB).as_uri()}?mode=ro", uri=True, timeout=2)
        conn.row_factory = sqlite3.Row
        calls = [call_record(row) for row in
                 conn.execute("SELECT * FROM assistant_usage_events ORDER BY created_at")]
        meta = session_meta(conn)
        prices = copilot_prices(conn)
        conn.close()
    except (sqlite3.Error, IndexError):
        return cache.entries.get(DB, (None, ([], {}, {})))[1]
    cache.entries[DB] = (stamp, (calls, meta, prices))
    return calls, meta, prices
