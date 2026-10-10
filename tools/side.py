"""Side-by-side view of a decrypted object: 360 (BE) vs PC (LE), as u32 words + ascii.
usage: python tools/side.py <logical> [start] [len]"""
import os, sys, struct
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _common import PLAIN  # noqa: E402

X = os.path.join(PLAIN, 'x360')
P = os.path.join(PLAIN, 'pc')


def load(name):
    xm = {f.upper(): f for f in os.listdir(X)}
    pm = {f.upper(): f for f in os.listdir(P)}
    k = (name + '.bin').upper()
    return open(os.path.join(X, xm[k]), 'rb').read(), open(os.path.join(P, pm[k]), 'rb').read()


def asc(b):
    return ''.join(chr(c) if 32 <= c < 127 else '.' for c in b)


if __name__ == '__main__':
    x, p = load(sys.argv[1])
    a = int(sys.argv[2], 0) if len(sys.argv) > 2 else 0
    n = int(sys.argv[3], 0) if len(sys.argv) > 3 else 512
    for o in range(a, min(a + n, max(len(x), len(p))), 16):
        xw = ' '.join(f'{struct.unpack_from(">I", x, o + i)[0]:08x}' if o + i + 4 <= len(x) else '        ' for i in range(0, 16, 4))
        pw = ' '.join(f'{struct.unpack_from("<I", p, o + i)[0]:08x}' if o + i + 4 <= len(p) else '        ' for i in range(0, 16, 4))
        print(f'{o:05x} | {xw} {asc(x[o:o+16]):16s} | {pw} {asc(p[o:o+16]):16s}')
