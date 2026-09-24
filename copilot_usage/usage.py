"""Merges every source into records, and builds the payload the dashboard polls."""
import ctypes
import glob
import os
import time
from collections import defaultdict
from datetime import datetime, timedelta, timezone

from . import cache
from .config import BURN_MINUTES, NANO, SESSIONS, tier_of
from .opencode import opencode_load
from .records import KEYS, LISTS, NANO_SUMS, SUMS, epoch, usage_rows
from .session_logs import load_sessions, log_records, session_name
from .session_store import db_load


def load_calls():
    calls, meta, prices = db_load()
    opencode_calls, opencode_meta = opencode_load(prices)
    return calls + opencode_calls, {**meta, **opencode_meta}


def all_records(sessions):
    calls, _meta = load_calls()
    db_start = {}
    for record in calls:
        db_start.setdefault(record["session"], record["ts"])
    return calls + list(log_records(sessions, db_start))


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


def plan_status(sessions, records):
    """Account-wide plan usage from the latest quota GitHub reported to Copilot CLI,
    brought up to date with the calls this machine logged since."""
    snapshots = [session["quota"] for session in sessions.values() if session.get("quota")]
    if not snapshots:
        return None
    reported_at, quota = max(snapshots, key=lambda snapshot: snapshot[0])
    if quota.get("isUnlimitedEntitlement") or not quota.get("entitlementRequests"):
        return None
    reset = datetime.fromisoformat(quota["resetDate"].replace("Z", "+00:00"))
    start = reset.replace(year=reset.year - 1, month=12) if reset.month == 1 else reset.replace(month=reset.month - 1)
    start = start.strftime("%Y-%m-%dT%H:%M:%S")
    local_before = sum(r["aiu"] for r in records if start <= r["ts"] <= reported_at) / NANO
    local_after = sum(r["aiu"] for r in records if r["ts"] > reported_at) / NANO
    reported = quota.get("usedRequests", 0)
    return {
        "limit": quota["entitlementRequests"], "reported": reported, "reported_at": epoch(reported_at),
        "used": reported + local_after, "outside": max(0, reported - local_before), "reset": quota["resetDate"],
    }


_built = {}


def usage_data():
    sessions = load_sessions()
    _calls, meta = load_calls()
    version = cache.version()
    if _built.get("version") != version:
        records = all_records(sessions)
        rows = sorted(usage_rows(records).items())
        info = session_info({key[2] for key, _ in rows}, sessions, meta)
        in_aic = ("aiu",) + NANO_SUMS
        plan = plan_status(sessions, records)
        _built.update(version=version, sessions=sessions, records=records, plan=plan, data={
            "fields": list(KEYS) + ["aic" if name == "aiu" else name for name in SUMS] + list(LISTS),
            "rows": [[*key, *(round(row[name] / NANO, 3) if name in in_aic else row[name] for name in SUMS),
                      *(row[name] for name in LISTS)] for key, row in rows],
            "sessions": info,
            "tiers": {model: tier_of(model) for model in {key[3] for key, _ in rows}},
        })
    return _built


def api_payload(known_version="", budget=None):
    built = usage_data()
    plan = built["plan"]
    payload = {"now": time.time(), "version": built["version"], "plan": plan,
               "budget": budget if budget is not None else plan and plan["limit"],
               "burn_minutes": BURN_MINUTES,
               "active": active_sessions(built["sessions"], built["records"], built["data"]["sessions"])}
    if known_version != built["version"]:
        payload.update(built["data"])
    return payload
