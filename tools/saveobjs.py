"""Enumerate save-object classes: ctor calls base 0x454600; derived vtable has slot3 == 0x454660.
Prints name string (if found nearby), vtable, and slot 0/1/2 functions."""
import os, sys, struct, re
sys.path.insert(0, os.path.dirname(__file__))
import x86

BASE_CTOR = 0x454600
SIG = 0x454660


def u32(va):
    return struct.unpack('<I', x86.rd(va, 4))[0]


def cstr(va):
    try:
        b = x86.rd(va, 64)
    except Exception:
        return None
    s = b.split(b'\0')[0]
    if len(s) >= 3 and all(32 <= c < 127 for c in s):
        return s.decode()
    return None


def scan(call_site):
    start = x86.func_start(call_site) or call_site - 0x200
    names, vts = [], []
    for ins in x86.md.disasm(x86.rd(start, call_site - start + 0x300), start):
        if ins.address > call_site + 0x300:
            break
        for m in re.finditer(r'0x([0-9a-f]{7,8})', ins.op_str):
            v = int(m.group(1), 16)
            if 0x1280000 < v < 0x1430000:
                s = cstr(v)
                if s and ins.mnemonic == 'push':
                    names.append(s)
                try:
                    if u32(v + 12) == SIG and v not in vts:
                        vts.append(v)
                except Exception:
                    pass
    return start, names, vts


if __name__ == '__main__':
    sites = [int(a, 16) for a in sys.argv[1:]] or x86.callers(BASE_CTOR)
    seen = set()
    for s in sites:
        start, names, vts = scan(s)
        for vt in vts:
            if vt in seen:
                continue
            seen.add(vt)
            print(f'ctor {start:08x}  vt {vt:08x}  save={u32(vt):08x} load={u32(vt+4):08x} s2={u32(vt+8):08x}  names={names[:4]}')
