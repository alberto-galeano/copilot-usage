# copilot-usage

Local stats for GitHub Copilot CLI: AI credits, calls and tokens per model, read from `~/.copilot/session-state/*/events.jsonl`. Nothing leaves the machine. Python 3 stdlib only.

## Usage

```sh
ln -sf "$PWD/copilot_usage.py" ~/.local/bin/copilot-usage

copilot-usage                                  # table per month
copilot-usage --by day --since 2026-09-01      # or --by repo
copilot-usage serve                            # live dashboard at http://localhost:8765
```

## How the numbers are derived

- 1 AIC = 1e9 `totalNanoAiu` = $0.01.
- Per-model totals only appear on `session.shutdown`. While a session is open, `session.usage_checkpoint` running totals are credited to the active model, then reconciled per model at shutdown.
- Counters are cumulative per session but sometimes restart after a resume, so a drop is treated as a fresh counter.
- Only Copilot CLI on this machine is covered. VS Code, github.com chat and the coding agent bill to the same account but don't log here.

## Tiers

Premium, standard and light are guessed from model names by `TIER_RULES` at the top of `copilot_usage.py`. Edit it to match how your org classifies models.
