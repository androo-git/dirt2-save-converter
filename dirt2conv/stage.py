"""Build a hybrid PC save folder from a 360 save + a working PC save.

* Objects in RUNTIME_CONVERT keep their 360 (big-endian) payload, wrapped in a
  PC container. They are byte-swapped while the PC game loads them (see
  tools/frida_agent.js), after which the game re-saves them natively.
* Profile (XML) is converted offline here.
* Everything else (SystemFile, inputData, Net*) is copied from the PC save.
"""
import os
import re
import shutil
import struct

from .names import encode_name, logical_name
from .savefile import SaveFile, build_pc, parse_360, parse_pc, CHUNK_SIZE

RUNTIME_CONVERT = [
    "voiceCounters", "rvInteriorManager", "VehicleSettingsManager", "RaceHistory",
    "VideoPlayedManager", "VehicleSetupSavedData", "Unlocks", "FriendshipManager",
    "rewards_save", "career manager sdu name", "dlc_unlock", "missions", "eventSpeech",
]

# Profile XML tags whose value is kept from the PC profile (account/machine specific).
PROFILE_KEEP_PC = {"GamerID", "savegame_user_id", "profile_id"}

_TAG = re.compile(r'<(\w+) type="(\d)">(.*?)</\1>', re.S)


def _pad(payload: bytes) -> bytes:
    r = len(payload) % CHUNK_SIZE
    return payload + bytes(CHUNK_SIZE - r) if r else payload


def merge_profile(x360_payload: bytes, pc_payload: bytes, keep=PROFILE_KEEP_PC) -> bytes:
    n = struct.unpack(">I", x360_payload[:4])[0]
    xml = x360_payload[4:4 + n].decode("utf-8")
    m = struct.unpack("<I", pc_payload[:4])[0]
    pc_xml = pc_payload[4:4 + m].decode("utf-8")
    pc_vals = {k: v for k, _, v in _TAG.findall(pc_xml)}

    def sub(mt):
        k, t, v = mt.group(1), mt.group(2), mt.group(3)
        if k in keep and k in pc_vals:
            v = pc_vals[k]
        return f'<{k} type="{t}">{v}</{k}>'

    out = _TAG.sub(sub, xml).encode("utf-8")
    if not out.endswith(b"\0"):
        out += b"\0"
    return _pad(struct.pack("<I", len(out)) + out)


def backup_slot(slot, backups_root) -> str:
    """Copy the slot folder to backups_root/<slot>_<timestamp>; returns the backup path."""
    from datetime import datetime
    slot = os.fspath(slot)
    if not os.path.isdir(slot) or not os.listdir(slot):
        return None
    dst = os.path.join(os.fspath(backups_root),
                       f"{os.path.basename(slot)}_{datetime.now():%Y%m%d_%H%M%S}")
    shutil.copytree(slot, dst)
    return dst


def replace_slot(src_dir, slot):
    """Replace the contents of slot with the files in src_dir."""
    slot = os.fspath(slot)
    os.makedirs(slot, exist_ok=True)
    for f in os.listdir(slot):
        p = os.path.join(slot, f)
        if os.path.isfile(p):
            os.remove(p)
    for f in os.listdir(src_dir):
        shutil.copyfile(os.path.join(src_dir, f), os.path.join(slot, f))


def stage(x360_files: dict, pc_dir: str, out_dir: str, convert=RUNTIME_CONVERT):
    """x360_files: logical name -> raw 360 object file bytes."""
    os.makedirs(out_dir, exist_ok=True)
    report = []
    lower = {k.lower(): k for k in x360_files}
    for pc_name in sorted(os.listdir(pc_dir)):
        src = os.path.join(pc_dir, pc_name)
        if not os.path.isfile(src):
            continue
        pc_raw = open(src, "rb").read()
        pc_sf = parse_pc(pc_raw)
        logical = None
        for name in list(convert) + ["Profile"]:
            if encode_name(name) == pc_name:
                logical = name
        dst = os.path.join(out_dir, pc_name)
        if logical and logical.lower() in lower:
            x_sf = parse_360(x360_files[lower[logical.lower()]])
            if logical == "Profile":
                payload = merge_profile(x_sf.payload, pc_sf.payload)
                how = "profile-merged"
            else:
                payload = x_sf.payload
                how = "360-payload (runtime swap)"
            sf = SaveFile(payload=payload, marker=pc_sf.marker)
            open(dst, "wb").write(build_pc(sf))
        else:
            shutil.copyfile(src, dst)
            how = "copied from PC"
        report.append((pc_name, logical or logical_name(pc_name), how))
    return report
