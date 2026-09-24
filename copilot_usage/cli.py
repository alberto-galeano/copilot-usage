"""Copilot usage per model, from Copilot CLI's ~/.copilot session-store.db and session logs,
plus opencode sessions that use the GitHub Copilot provider.

  copilot-usage [--since YYYY-MM-DD] [--by month|day|repo|branch]   print a table
  copilot-usage serve [--port 8765] [--budget AIC]                   live dashboard
"""
import argparse
from collections import defaultdict

from . import __version__
from .config import NANO, tier_of
from .records import usage_rows
from .server import serve
from .session_logs import load_sessions
from .usage import all_records, load_calls, plan_status


def print_table(since, by):
    sessions = load_sessions()
    _calls, meta = load_calls()
    detail = lambda session_id, field: (meta.get(session_id, {}).get(field)
                                        or sessions.get(session_id, {}).get(field, "-"))
    group_of = {"month": lambda day, session_id: day[:7], "day": lambda day, session_id: day,
                "repo": lambda day, session_id: detail(session_id, "repo"),
                "branch": lambda day, session_id: f"{detail(session_id, 'repo')} @ {detail(session_id, 'branch')}"}[by]
    groups = defaultdict(lambda: defaultdict(lambda: defaultdict(int)))
    records = all_records(sessions)
    for (day, _hour, session_id, model, *_rest), row in usage_rows(records).items():
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

    plan = plan_status(sessions, records)
    if plan:
        print(f"\nPlan: {plan['used']:,.0f} / {plan['limit']:,.0f} AIC ({plan['used'] / plan['limit']:.0%} used), "
              f"{plan['outside']:,.0f} from outside this machine, resets {plan['reset'][:10]}")


def main():
    parser = argparse.ArgumentParser(prog="copilot-usage", description=__doc__,
                                     formatter_class=argparse.RawTextHelpFormatter)
    parser.add_argument("command", nargs="?", choices=["serve"])
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--since", default="", help="YYYY-MM-DD")
    parser.add_argument("--by", choices=["month", "day", "repo", "branch"], default="month")
    parser.add_argument("--budget", type=float, help="monthly AIC budget for the dashboard (default: the plan limit GitHub reports)")
    args = parser.parse_args()

    if args.command == "serve":
        try:
            serve(args.port, args.budget)
        except KeyboardInterrupt:
            pass
    else:
        print_table(args.since, args.by)
