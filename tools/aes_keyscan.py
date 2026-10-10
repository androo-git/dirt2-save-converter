"""Brute-force: find an AES key inside the exe such that AES_ECB_enc(key, 0^16) == K.
Hypothesis: the save 'XOR key' is really the AES-ECB encryption of an all-zero block."""
import os, sys
from multiprocessing import Pool
from Crypto.Cipher import AES

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _common import game_exe  # noqa: E402

EXE = sys.argv[1] if len(sys.argv) > 1 else game_exe()
K = bytes.fromhex('1FBF07A5E2966A380C837EF7D004E8D2')
Z = bytes(16)
data = None


def init():
    global data
    data = open(EXE, 'rb').read()


def work(rng):
    a, b = rng
    hits = []
    for i in range(a, b):
        for ks in (16, 24, 32):
            raw = data[i:i + ks]
            if len(raw) < ks or len(set(raw)) < 6:
                continue
            sw = b''.join(raw[j:j + 4][::-1] for j in range(0, ks, 4))
            for tag, key in (('raw', raw), ('wswap', sw)):
                c = AES.new(key, AES.MODE_ECB)
                if c.encrypt(Z) == K:
                    hits.append((i, ks, 'enc-' + tag))
                if c.decrypt(Z) == K:
                    hits.append((i, ks, 'dec-' + tag))
    return hits


if __name__ == '__main__':
    n = len(open(EXE, 'rb').read())
    step = 200000
    with Pool(initializer=init) as p:
        for hits in p.imap_unordered(work, [(a, min(a + step, n)) for a in range(0, n, step)]):
            for h in hits:
                print('HIT', hex(h[0]), h[1], h[2], flush=True)
    print('done')
