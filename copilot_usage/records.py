"""The per-call record every source produces, and the hourly rows the dashboard receives."""
from datetime import datetime, timezone

SUMS = ("aiu", "calls", "prompts", "in", "out", "cache", "cache_write", "reasoning", "ms",
        "out_timed", "premium", "c_input", "c_cache_read", "c_cache_write", "c_output", "saved",
        "itl", "itl_n", "filtered")
LISTS = ("ttft", "ottft", "dur")  # per-call milliseconds, kept raw so the dashboard can take percentiles
NANO_SUMS = ("c_input", "c_cache_read", "c_cache_write", "c_output", "saved")
KEYS = ("day", "hour", "session", "model", "initiator", "effort", "endpoint", "finish")
TOKEN_KINDS = ("input", "cache_read", "cache_write", "output")


def blank_record(**fields):
    return {**dict.fromkeys(SUMS, 0), **{name: [] for name in LISTS}, **fields}


def local_day_hour(ts):
    moment = datetime.fromisoformat(ts.replace("Z", "+00:00")).astimezone()
    return moment.strftime("%Y-%m-%d"), moment.hour


def epoch(ts):
    if not ts:
        return None
    moment = datetime.fromisoformat(ts.replace("Z", "+00:00").replace(" ", "T"))
    return (moment if moment.tzinfo else moment.replace(tzinfo=timezone.utc)).timestamp()


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
