"""Inspect a PC save slot: does it parse, is it native PC data, what does it contain."""
import re
import struct
from pathlib import Path

from .names import decode_name, encode_name
from .savefile import SaveFileError, parse_pc

RACEHISTORY_MAGIC = 0x539


def _payload(slot: Path, logical: str):
    p = slot / encode_name(logical)
    if not p.is_file():
        return None
    return parse_pc(p.read_bytes()).payload


def summarize(slot) -> dict:
    slot = Path(slot)
    info = {"slot": str(slot), "files": 0, "errors": [], "native": None}
    for f in sorted(slot.iterdir()) if slot.is_dir() else []:
        if not f.is_file():
            continue
        info["files"] += 1
        try:
            parse_pc(f.read_bytes())
        except SaveFileError as e:
            info["errors"].append(f"{decode_name(f.name)}: {e}")

    try:
        rh = _payload(slot, "RaceHistory")
        if rh:
            le, be = struct.unpack_from("<I", rh)[0], struct.unpack_from(">I", rh)[0]
            info["native"] = le == RACEHISTORY_MAGIC
            if be == RACEHISTORY_MAGIC:
                info["native"] = False
        prof = _payload(slot, "Profile")
        if prof:
            n = struct.unpack_from("<I", prof)[0]
            if n > len(prof):
                n = struct.unpack_from(">I", prof)[0]
            xml = prof[4:4 + n].decode("utf-8", "replace")
            tags = dict(re.findall(r'<(Player_FirstName|Player_LastName|Player_TeamName)[^>]*>([^<]*)<', xml))
            info["driver"] = f"{tags.get('Player_FirstName', '')} {tags.get('Player_LastName', '')}".strip()
        sysf = _payload(slot, "SystemFile")
        if sysf:
            m = re.search(rb"DiRT Tour XP: ?[0-9]+", sysf)
            if m:
                info["summary"] = m.group().decode()
    except SaveFileError as e:
        info["errors"].append(str(e))
    return info


def print_summary(slot):
    i = summarize(slot)
    print(f"slot     : {i['slot']}")
    print(f"files    : {i['files']}")
    if "driver" in i:
        print(f"driver   : {i['driver']}")
    if "summary" in i:
        print(f"progress : {i['summary']}")
    state = {True: "native PC save", False: "still contains Xbox 360 (big-endian) data",
             None: "unknown"}[i["native"]]
    print(f"format   : {state}")
    for e in i["errors"]:
        print(f"ERROR    : {e}")
    return i
