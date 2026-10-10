import argparse
import os
import sys
import tempfile
from pathlib import Path

from . import __version__, config
from .stfs import StfsError


def _game_running():
    if sys.platform != "win32":
        return False
    import subprocess
    out = subprocess.run(["tasklist", "/FI", "IMAGENAME eq dirt2_game.exe"],
                         capture_output=True, text=True).stdout
    return "dirt2_game.exe" in out.lower()


def _resolve_x360(arg):
    from .x360 import find_saves
    if arg:
        return Path(arg)
    if config.x360_save():
        return config.x360_save()
    found = find_saves()
    if len(found) == 1:
        print(f"Using 360 save found at {found[0][0]}")
        return found[0][0]
    if not found:
        raise SystemExit("No Xbox 360 DiRT 2 save found on any drive. Plug in the USB stick, "
                         "or pass the file path / set DIRT2_X360_SAVE.")
    lines = "\n  ".join(str(f) for f, _ in found)
    raise SystemExit(f"Several 360 saves found, pick one and pass its path:\n  {lines}")


# ---------------------------------------------------------------- commands

def cmd_find(args):
    from .x360 import find_saves
    found = find_saves(args.roots)
    if not found:
        print("No DiRT 2 Xbox 360 saves found (looked for Xbox360\\Content\\*\\"
              f"{'|'.join(config.title_ids())}\\00000001\\* on every drive).")
        return
    for f, pkg in found:
        h = pkg.header
        print(f"{f}\n    {h.title_name or 'DiRT 2'} - {h.display_name!r}, "
              f"{len(pkg.iter_files())} objects")


def cmd_info(args):
    from .stfs import StfsPackage
    path = _resolve_x360(args.file)
    if path.is_dir():
        for f in sorted(path.iterdir()):
            print(f"{f.name:28} {f.stat().st_size:>8} bytes")
        return
    print(StfsPackage(path.read_bytes()).describe())


def cmd_extract(args):
    from .x360 import load_x360
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    for name, data in load_x360(_resolve_x360(args.file)).items():
        (out / name).write_bytes(data)
        print(f"extracted {out / name} ({len(data)} bytes)")


def cmd_prepare(args):
    from .stage import backup_slot, replace_slot, stage
    from .verify import summarize
    from .x360 import load_x360

    if _game_running():
        raise SystemExit("DiRT 2 is running - quit the game first.")
    slot = Path(args.slot) if args.slot else config.slot_dir()
    pc_base = Path(args.pc_base) if args.pc_base else slot
    if not pc_base.is_dir() or not any(pc_base.iterdir()):
        raise SystemExit(f"No PC save found in {pc_base}.\n"
                         "Start the PC game once, create a profile and let it autosave "
                         "(get to the main menu), quit, then run this again.")
    state = summarize(pc_base)
    if state["native"] is False and not args.pc_base:
        raise SystemExit(f"{pc_base} already contains staged Xbox 360 data. Run `assist` to finish "
                         "the conversion, or `restore` a backup / pass --pc-base <a PC save>.")
    if state["errors"]:
        raise SystemExit("The PC save doesn't parse:\n  " + "\n  ".join(state["errors"]))

    x360_files = load_x360(_resolve_x360(args.x360))
    backups = config.work_dir() / "backups"
    backups.mkdir(exist_ok=True)
    bk = backup_slot(slot, backups)
    if bk:
        print(f"Backed up current slot to {bk}")

    with tempfile.TemporaryDirectory(dir=config.work_dir()) as tmp:
        report = stage(x360_files, str(bk or pc_base), tmp)
        replace_slot(tmp, slot)
    for pc_name, logical, how in report:
        print(f"  {logical or pc_name:26} {how}")
    print(f"\nStaged into {slot}.\nNext: run  python -m dirt2conv assist  and start the game.")


def cmd_assist(args):
    from .assist import run
    from .verify import print_summary
    slot = Path(args.slot) if args.slot else config.slot_dir()
    run(mode=args.mode, force=args.force)
    if args.mode == "convert":
        print()
        i = print_summary(slot)
        if i["native"]:
            print("\nDone - the slot is a native PC save now. Launch the game normally.")
        else:
            print("\nThe slot still holds 360 data: the game didn't save while attached. "
                  "Run `assist` again and make the game save before quitting.")


def cmd_verify(args):
    from .verify import print_summary
    print_summary(Path(args.slot) if args.slot else config.slot_dir())


def cmd_backup(args):
    from .stage import backup_slot
    slot = Path(args.slot) if args.slot else config.slot_dir()
    backups = config.work_dir() / "backups"
    backups.mkdir(exist_ok=True)
    print(backup_slot(slot, backups) or f"nothing to back up in {slot}")


def cmd_restore(args):
    from .stage import backup_slot, replace_slot
    if _game_running():
        raise SystemExit("DiRT 2 is running - quit the game first.")
    backups = config.work_dir() / "backups"
    slot = Path(args.slot) if args.slot else config.slot_dir()
    if not args.backup:
        items = sorted(p for p in backups.glob("*") if p.is_dir()) if backups.is_dir() else []
        if not items:
            raise SystemExit("no backups found")
        for p in items:
            print(p)
        print("\npass one of the above to `restore`")
        return
    src = Path(args.backup)
    if not src.is_absolute() and not src.exists():
        src = backups / src
    bk = backup_slot(slot, backups)
    replace_slot(src, slot)
    print(f"restored {src} -> {slot}" + (f" (previous contents saved to {bk})" if bk else ""))


def cmd_dump(args):
    from .x360 import load_x360
    from .savefile import parse_360
    files = load_x360(_resolve_x360(args.file))
    data = parse_360(files[args.entry]).payload if args.decrypt else files[args.entry]
    end = len(data) if not args.length else args.offset + args.length
    for off in range(args.offset, min(end, len(data)), 16):
        chunk = data[off:off + 16]
        text = "".join(chr(b) if 0x20 <= b < 0x7F else "." for b in chunk)
        print(f"{off:08X}  {' '.join(f'{b:02X}' for b in chunk):<47}  {text}")


def build_parser():
    ap = argparse.ArgumentParser(
        prog="dirt2conv", description="Colin McRae: DiRT 2 save converter (Xbox 360 -> PC)")
    ap.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = ap.add_subparsers(dest="command", required=True)

    p = sub.add_parser("find", help="search drives (USB stick) for DiRT 2 Xbox 360 saves")
    p.add_argument("roots", nargs="*", help="extra folders to search")
    p.set_defaults(func=cmd_find)

    p = sub.add_parser("info", help="show the 360 save package contents")
    p.add_argument("file", nargs="?")
    p.set_defaults(func=cmd_info)

    p = sub.add_parser("extract", help="extract the objects from a 360 save package")
    p.add_argument("file", nargs="?")
    p.add_argument("-o", "--out", default=str(config.work_dir() / "x360_extracted"))
    p.set_defaults(func=cmd_extract)

    p = sub.add_parser("prepare", help="step 1: back up the PC slot and stage the 360 save into it")
    p.add_argument("x360", nargs="?", help="360 save package (default: DIRT2_X360_SAVE or auto-find)")
    p.add_argument("--slot", help="PC save slot folder (default: Documents\\My Games\\DiRT2\\savegame\\Autosave0)")
    p.add_argument("--pc-base", help="take the PC-only files from this save folder instead of the slot")
    p.set_defaults(func=cmd_prepare)

    p = sub.add_parser("assist", help="step 2: hook the game while it loads, so it converts and re-saves")
    p.add_argument("--slot")
    p.add_argument("--mode", choices=["convert", "recon"], default="convert",
                   help="recon = log only, change nothing")
    p.add_argument("--force", action="store_true", help="hook even if the exe build is unknown")
    p.set_defaults(func=cmd_assist)

    p = sub.add_parser("verify", help="check a PC save slot")
    p.add_argument("--slot")
    p.set_defaults(func=cmd_verify)

    p = sub.add_parser("backup", help="back up the PC save slot")
    p.add_argument("--slot")
    p.set_defaults(func=cmd_backup)

    p = sub.add_parser("restore", help="list backups, or restore one into the PC slot")
    p.add_argument("backup", nargs="?")
    p.add_argument("--slot")
    p.set_defaults(func=cmd_restore)

    p = sub.add_parser("dump", help="hex dump an object from a 360 save (analysis)")
    p.add_argument("entry")
    p.add_argument("file", nargs="?")
    p.add_argument("--decrypt", action="store_true")
    p.add_argument("-o", "--offset", type=lambda s: int(s, 0), default=0)
    p.add_argument("-l", "--length", type=lambda s: int(s, 0), default=256)
    p.set_defaults(func=cmd_dump)
    return ap


def main(argv=None):
    args = build_parser().parse_args(sys.argv[1:] if argv is None else argv)
    try:
        args.func(args)
    except StfsError as e:
        raise SystemExit(f"error: {e}")


if __name__ == "__main__":
    main()
