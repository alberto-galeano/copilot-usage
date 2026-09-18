# copilot-usage

Local stats for GitHub Copilot CLI: AI credits, calls and tokens per model, read from `~/.copilot/session-store.db` and `~/.copilot/session-state/*/events.jsonl`. Nothing leaves the machine. Python 3 stdlib only.

## Usage

```sh
ln -sf "$PWD/copilot_usage.py" ~/.local/bin/copilot-usage

copilot-usage                                  # table per month
copilot-usage --by day --since 2026-09-01      # or --by repo, --by branch
copilot-usage serve                            # live dashboard at http://localhost:8765
copilot-usage serve --budget 25000             # also track a monthly AIC budget
```

## How the numbers are derived

- 1 AIC = 1e9 `totalNanoAiu` = $0.01.
- `session-store.db` has one row per model call in `assistant_usage_events` (model, tokens, nanoAIU, reasoning effort, initiator, latency, request multiplier). This is the primary source, and it exists from CLI ~1.0.7x onwards.
- Spend a session made before its first database row comes from `events.jsonl`: per-model totals on `session.shutdown`, with `session.usage_checkpoint` running totals credited to the active model in between. Those counters sometimes restart after a resume, so a drop is treated as a fresh counter. Sessions that were killed never wrote a shutdown, so log-only periods undercount.
- Premium requests = request multiplier summed over user-initiated calls only, which is how the older premium-request billing counts.
- Only Copilot CLI on this machine is covered. VS Code, github.com chat and the coding agent bill to the same account but don't log here.

## Dashboard

- Filters (date range, tier, model, repository, branch, effort, initiator, API endpoint, finish reason, host, session) live in the URL hash, so a view can be bookmarked. Bars, table rows and open sessions are clickable filters. Clicking a day switches the spend chart to hours.
- Spend is compared with the window of the same length right before it, and "This month" adds a month-end projection (against `--budget` if set).
- Token type splits the bill using the per-call price list in `token_details_json`. Cache savings are the cache reads re-priced at that call's input rate.
- Prompts are user-initiated calls. Subagent spend is calls with initiator `sub-agent`, and the subagent count is distinct `agent_id`s.
- The sessions table joins `sessions`, `turns`, `session_files`, `checkpoints` and `session_refs`. Those counts cover the whole session, not the selected range. A failed-commands column shows up once `forge_trajectory_events` has rows.
- Latency percentiles come from raw per-call durations. The page only re-downloads the data when the database or a session log changed.
- Export CSV downloads the filtered rows.

## Tiers

Premium, standard and light are guessed from model names by `TIER_RULES` at the top of `copilot_usage.py`. Edit it to match how your org classifies models.
