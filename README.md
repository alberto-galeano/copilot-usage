# copilot-usage

Local stats for GitHub Copilot CLI: AI credits, calls and tokens per model, read from `~/.copilot/session-store.db` and `~/.copilot/session-state/*/events.jsonl`. Nothing leaves the machine. Python 3 stdlib only.

## Usage

```sh
ln -sf "$PWD/copilot_usage.py" ~/.local/bin/copilot-usage

copilot-usage                                  # table per month
copilot-usage --by day --since 2026-09-01      # or --by repo
copilot-usage serve                            # live dashboard at http://localhost:8765
```

## How the numbers are derived

- 1 AIC = 1e9 `totalNanoAiu` = $0.01.
- `session-store.db` has one row per model call in `assistant_usage_events` (model, tokens, nanoAIU, reasoning effort, initiator, latency, request multiplier). This is the primary source, and it exists from CLI ~1.0.7x onwards.
- Spend a session made before its first database row comes from `events.jsonl`: per-model totals on `session.shutdown`, with `session.usage_checkpoint` running totals credited to the active model in between. Those counters sometimes restart after a resume, so a drop is treated as a fresh counter. Sessions that were killed never wrote a shutdown, so log-only periods undercount.
- Premium requests = request multiplier summed over user-initiated calls only, which is how the older premium-request billing counts.
- Only Copilot CLI on this machine is covered. VS Code, github.com chat and the coding agent bill to the same account but don't log here.

## Tiers

Premium, standard and light are guessed from model names by `TIER_RULES` at the top of `copilot_usage.py`. Edit it to match how your org classifies models.
