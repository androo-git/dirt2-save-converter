"""Small static helpers: disassemble at VA, find function start, find call xrefs."""
import os, struct, sys
from capstone import Cs, CS_ARCH_X86, CS_MODE_32

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _common import game_exe  # noqa: E402

EXE = game_exe()
d = open(EXE, 'rb').read()
BASE = 0x400000
TEXT_LO, TEXT_HI = BASE + 0x1000, BASE + 0x1000 + 0xe8b000
md = Cs(CS_ARCH_X86, CS_MODE_32)


def rd(va, n):
    return d[va - BASE: va - BASE + n]


def dis(va, n=40):
    out = []
    for ins in md.disasm(rd(va, n * 15), va):
        out.append(f'{ins.address:08x}: {ins.bytes.hex():20s} {ins.mnemonic} {ins.op_str}')
        if len(out) >= n:
            break
    return '\n'.join(out)


def func(va, maxlen=0x3000):
    """Disassemble a whole function (stops at ret followed by int3 padding)."""
    out = []
    code = rd(va, maxlen)
    for ins in md.disasm(code, va):
        out.append(f'{ins.address:08x}: {ins.mnemonic} {ins.op_str}')
        if ins.mnemonic == 'ret':
            nxt = ins.address + ins.size - BASE
            if d[nxt] == 0xCC:
                # keep going if a later jump targets beyond (simple heuristic: stop)
                break
    return '\n'.join(out)


def func_start(va, maxback=0x4000):
    """Walk back to the nearest CC/C3 padding followed by an instruction start."""
    o = va - BASE
    for i in range(o, o - maxback, -1):
        if d[i - 1] in (0xCC, 0xC3) and d[i] not in (0xCC,) and (d[i - 2] in (0xCC, 0xC3, 0x90) or d[i-1] == 0xCC):
            return BASE + i
    return None


_text = None


def callers(target):
    global _text
    if _text is None:
        _text = d[0x1000:0x1000 + 0xe8b000]
    res = []
    i = _text.find(b'\xe8')
    t = _text
    for i in range(len(t) - 5):
        if t[i] == 0xE8:
            rel = struct.unpack_from('<i', t, i + 1)[0]
            if TEXT_LO + i + 5 + rel == target:
                res.append(TEXT_LO + i)
    return res


def imm_refs(value):
    t = d[0x1000:0x1000 + 0xe8b000]
    pat = struct.pack('<I', value)
    res = []; i = t.find(pat)
    while i != -1:
        res.append(TEXT_LO + i); i = t.find(pat, i + 1)
    return res


if __name__ == '__main__':
    cmd = sys.argv[1]
    if cmd == 'dis':
        print(dis(int(sys.argv[2], 16), int(sys.argv[3]) if len(sys.argv) > 3 else 40))
    elif cmd == 'func':
        args = sys.argv[2:]
        outf = None
        if args and args[0] == '-o':
            outf, args = args[1], args[2:]
        text = '\n'.join(f'===== {a}\n{func(int(a, 16))}' for a in args)
        if outf:
            open(outf, 'w', encoding='utf-8').write(text + '\n')
        else:
            print(text)
    elif cmd == 'start':
        print(hex(func_start(int(sys.argv[2], 16))))
    elif cmd == 'callers':
        print([hex(x) for x in callers(int(sys.argv[2], 16))])
    elif cmd == 'refs':
        print([hex(x) for x in imm_refs(int(sys.argv[2], 16))])
