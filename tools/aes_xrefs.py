"""Find code referencing the AES tables and disassemble the referencing functions."""
import os, struct, sys
from capstone import Cs, CS_ARCH_X86, CS_MODE_32

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _common import game_exe  # noqa: E402

EXE = game_exe()
d = open(EXE, 'rb').read()
BASE = 0x400000
TEXT_RAW, TEXT_VA, TEXT_SZ = 0x1000, 0x1000, 0xe8b000

def va2off(va):
    return va - BASE  # raw == rva for all sections here except .tls/.rsrc

tables = {'Te_A': 0xfc52b0, 'Te_B': 0xfc9ca0, 'Td_A': 0xfc6ab0, 'Td_B': 0xfcb4a0}
text = d[TEXT_RAW:TEXT_RAW + TEXT_SZ]
refs = {}
for name, off in tables.items():
    lo, hi = BASE + off - 0x1000, BASE + off + 0x1400
    for i in range(len(text) - 4):
        v = struct.unpack_from('<I', text, i)[0]
        if lo <= v < hi:
            refs.setdefault(name, []).append((BASE + TEXT_VA + i, v))
for k, v in refs.items():
    print(k, len(v), [hex(a) for a, _ in v[:40]])
