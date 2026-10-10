"""Machine-specific settings.

Values come from (highest priority first):
  1. real environment variables
  2. a `.env` file in the current directory or the repository root
  3. defaults derived from the current Windows user

Nothing machine-specific is hard-coded in the code base; copy `.env.example`
to `.env` if the defaults don't fit your setup.
"""
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

# DiRT 2 Xbox 360 title id (as used in Xbox360\Content\<profile>\<title id>\00000001\)
DEFAULT_TITLE_IDS = ("434D0819",)


def _load_dotenv():
    for candidate in (Path.cwd() / ".env", REPO_ROOT / ".env"):
        if candidate.is_file():
            for line in candidate.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, _, value = line.partition("=")
                key, value = key.strip(), value.strip().strip('"').strip("'")
                os.environ.setdefault(key, os.path.expandvars(value))
            return candidate
    return None


DOTENV_PATH = _load_dotenv()


def _documents_dir() -> Path:
    """The user's Documents folder (handles OneDrive / relocated folders)."""
    if sys.platform == "win32":
        try:
            import ctypes
            from ctypes import wintypes
            import uuid

            # FOLDERID_Documents
            fid = uuid.UUID("{FDD39AD0-238F-46AF-ADB4-6C85480369C7}")

            class GUID(ctypes.Structure):
                _fields_ = [("Data1", wintypes.DWORD), ("Data2", wintypes.WORD),
                            ("Data3", wintypes.WORD), ("Data4", ctypes.c_ubyte * 8)]

            g = GUID(fid.fields[0], fid.fields[1], fid.fields[2],
                     (ctypes.c_ubyte * 8)(*fid.bytes[8:]))
            out = ctypes.c_wchar_p()
            shell32 = ctypes.windll.shell32
            if shell32.SHGetKnownFolderPath(ctypes.byref(g), 0, None, ctypes.byref(out)) == 0:
                path = out.value
                ctypes.windll.ole32.CoTaskMemFree(out)
                return Path(path)
        except Exception:
            pass
    return Path.home() / "Documents"


def _env_path(name):
    v = os.environ.get(name)
    return Path(v) if v else None


def savegame_dir() -> Path:
    """...\\My Games\\DiRT2\\savegame"""
    return _env_path("DIRT2_SAVEGAME_DIR") or (_documents_dir() / "My Games" / "DiRT2" / "savegame")


def slot_name() -> str:
    return os.environ.get("DIRT2_SLOT", "Autosave0")


def slot_dir() -> Path:
    """The live PC save slot the game loads from."""
    return savegame_dir() / slot_name()


def game_exe():
    """Path to dirt2_game.exe (only needed for build checks and the RE tools)."""
    p = _env_path("DIRT2_GAME_EXE")
    if p:
        return p
    d = _env_path("DIRT2_GAME_DIR")
    return d / "dirt2_game.exe" if d else None


def x360_save():
    """Path to the Xbox 360 save package (or a folder of extracted objects)."""
    return _env_path("DIRT2_X360_SAVE")


def work_dir() -> Path:
    """Where backups, logs and analysis output are written."""
    p = _env_path("DIRT2_WORK_DIR") or (REPO_ROOT / "work")
    p.mkdir(parents=True, exist_ok=True)
    return p


def title_ids():
    v = os.environ.get("DIRT2_X360_TITLE_IDS")
    return tuple(x.strip().upper() for x in v.split(",")) if v else DEFAULT_TITLE_IDS


def require(value, what, env):
    if value is None:
        raise SystemExit(f"{what} is not configured: pass it on the command line or set {env} "
                         f"(environment variable or .env file, see .env.example)")
    return value
