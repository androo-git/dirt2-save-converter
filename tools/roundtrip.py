"""Byte-exact container round-trip checks (decrypt -> re-encrypt == original).

usage: python tools/roundtrip.py [360 package or extracted folder] [PC save folder]"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _common import PC_REF, X360_EXTRACTED, config  # noqa: E402
from dirt2conv import savefile  # noqa: E402
from dirt2conv.names import encode_name, decode_name  # noqa: E402
from dirt2conv.x360 import load_x360  # noqa: E402

X360 = sys.argv[1] if len(sys.argv) > 1 else (config.x360_save() or X360_EXTRACTED)
PC = sys.argv[2] if len(sys.argv) > 2 else PC_REF


def check_360_roundtrip():
    ok = bad = 0
    for name, raw in sorted(load_x360(X360).items()):
        if savefile.build_360(savefile.parse_360(raw)) == raw:
            ok += 1
        else:
            bad += 1
            print(f"360 ROUNDTRIP FAIL {name}")
    print(f"360 roundtrip: {ok} ok, {bad} bad")


def check_pc_roundtrip():
    ok = bad = 0
    for name in sorted(os.listdir(PC)):
        raw = open(os.path.join(PC, name), "rb").read()
        if savefile.build_pc(savefile.parse_pc(raw)) == raw:
            ok += 1
        else:
            bad += 1
            print(f"PC ROUNDTRIP FAIL {name}")
    print(f"PC roundtrip: {ok} ok, {bad} bad")


def check_names():
    ok = bad = 0
    for name in sorted(os.listdir(PC)):
        if encode_name(decode_name(name)) != name:
            bad += 1
            print(f"NAME FAIL {name}")
        else:
            ok += 1
    print(f"name cipher: {ok} ok, {bad} bad")


if __name__ == "__main__":
    check_names()
    check_360_roundtrip()
    check_pc_roundtrip()
