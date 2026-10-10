"""Shared settings for the analysis tools (all paths come from dirt2conv.config / .env)."""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from dirt2conv import config  # noqa: E402

WORK = str(config.work_dir())
X360_EXTRACTED = os.path.join(WORK, "x360_extracted")      # `dirt2conv extract` output
PLAIN = os.path.join(WORK, "plain")                         # tools/dump_plain.py output
# A PC save used as reference for comparisons (default: the live slot)
PC_REF = os.environ.get("DIRT2_PC_REF_SAVE") or str(config.slot_dir())


def game_exe():
    p = config.game_exe()
    if p is None:
        raise SystemExit("set DIRT2_GAME_DIR (or DIRT2_GAME_EXE) in .env to use the exe analysis tools")
    return str(p)
