"""Condensed listing of a code range: only string pushes, 'push imm' sizes and direct calls."""
import os, sys, re
sys.path.insert(0, os.path.dirname(__file__))
import x86
from saveobjs import cstr

a, b = int(sys.argv[1], 16), int(sys.argv[2], 16)
for ins in x86.md.disasm(x86.rd(a, b - a), a):
    s = None
    m = re.search(r'0x([0-9a-f]{6,8})', ins.op_str)
    if m:
        v = int(m.group(1), 16)
        if 0x1280000 < v < 0x1430000:
            s = cstr(v)
    if s is not None:
        print(f'{ins.address:08x}: {ins.mnemonic} {ins.op_str}   "{s}"')
    elif ins.mnemonic == 'call' or (ins.mnemonic == 'push' and ins.op_str.startswith('0x')):
        print(f'{ins.address:08x}: {ins.mnemonic} {ins.op_str}')
