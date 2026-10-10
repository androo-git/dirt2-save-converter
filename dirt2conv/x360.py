"""Locate and load Xbox 360 DiRT 2 save packages."""
import string
from pathlib import Path

from . import config
from .stfs import StfsError, StfsPackage

SAVED_GAME_DIR = "00000001"   # content type "Saved Game"


def load_x360(path) -> dict:
    """Return {logical object name: raw 360 object bytes} from a CON package
    or from a folder of already-extracted objects."""
    path = Path(path)
    if path.is_dir():
        return {f.name: f.read_bytes() for f in path.iterdir() if f.is_file()}
    pkg = StfsPackage(path.read_bytes())
    return {e.name: pkg.read(e) for e in pkg.iter_files()}


def describe(path):
    pkg = StfsPackage(Path(path).read_bytes())
    return pkg


def _candidates(root: Path, title_ids):
    # USB layout is <drive>\Xbox360\Content\<profile>\<title>\00000001\<file>; also accept
    # a root pointing at Content, a profile folder or the title folder itself.
    patterns = []
    for tid in title_ids:
        patterns += [f"Xbox360/Content/*/{tid}/{SAVED_GAME_DIR}", f"Content/*/{tid}/{SAVED_GAME_DIR}",
                     f"*/{tid}/{SAVED_GAME_DIR}", f"{tid}/{SAVED_GAME_DIR}", SAVED_GAME_DIR]
    seen = set()
    for pat in patterns:
        for d in root.glob(pat):
            if d.is_dir() and d.parent.name.upper() in title_ids:
                for f in d.iterdir():
                    if f.is_file() and f not in seen:
                        seen.add(f)
                        yield f


def find_saves(extra_roots=()):
    """Search every drive (and extra_roots) for DiRT 2 360 save packages."""
    roots = [Path(r) for r in extra_roots]
    roots += [Path(f"{c}:\\") for c in string.ascii_uppercase if Path(f"{c}:\\").exists()]
    found, seen = [], set()
    for root in roots:
        try:
            for f in _candidates(root, config.title_ids()):
                key = str(f.resolve()).lower()
                if key in seen:
                    continue
                seen.add(key)
                try:
                    pkg = StfsPackage(f.read_bytes())
                except (StfsError, OSError):
                    continue
                found.append((f, pkg))
        except OSError:
            continue
    return found
