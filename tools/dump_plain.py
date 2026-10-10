"""Write the decrypted plaintext of every object to <work>/plain/{x360,pc}/<logical>.bin

usage: python tools/dump_plain.py [360 package or extracted folder] [PC save folder]
(defaults: DIRT2_X360_SAVE / <work>/x360_extracted, and DIRT2_PC_REF_SAVE / the live slot)"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _common import PC_REF, PLAIN, X360_EXTRACTED, config  # noqa: E402
from dirt2conv import savefile  # noqa: E402
from dirt2conv.names import decode_name  # noqa: E402
from dirt2conv.x360 import load_x360  # noqa: E402

src = sys.argv[1] if len(sys.argv) > 1 else (config.x360_save() or X360_EXTRACTED)
pc = sys.argv[2] if len(sys.argv) > 2 else PC_REF

for sub in ("x360", "pc"):
    os.makedirs(os.path.join(PLAIN, sub), exist_ok=True)

for name, raw in sorted(load_x360(src).items()):
    sf = savefile.parse_360(raw)
    open(os.path.join(PLAIN, "x360", name + ".bin"), "wb").write(sf.payload)
for name in sorted(os.listdir(pc)):
    p = os.path.join(pc, name)
    if not os.path.isfile(p):
        continue
    sf = savefile.parse_pc(open(p, "rb").read())
    open(os.path.join(PLAIN, "pc", decode_name(name) + ".bin"), "wb").write(sf.payload)
    print(f"{decode_name(name):28s} marker={sf.marker:08X} chunks={len(sf.chunk_sizes)}")
print("written to", PLAIN)
