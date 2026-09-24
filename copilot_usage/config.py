import os
import re

NANO = 1e9  # 1 AIU (= 1 AI credit = $0.01) is 1e9 nanoAIU
SESSIONS = os.path.expanduser("~/.copilot/session-state")
DB = os.path.expanduser("~/.copilot/session-store.db")
OPENCODE_DB = os.path.join(os.environ.get("XDG_DATA_HOME") or os.path.expanduser("~/.local/share"),
                           "opencode", "opencode.db")
BURN_MINUTES = 15

# First match wins. Edit to match how your org classifies models.
TIER_RULES = [
    ("low", r"haiku|mini|flash|luna|nano"),
    ("high", r"opus|-sol"),
    ("medium", r""),
]


def tier_of(model):
    return next(tier for tier, pattern in TIER_RULES if re.search(pattern, model))
