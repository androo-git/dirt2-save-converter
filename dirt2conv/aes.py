"""Minimal pure-Python AES (ECB only) so the package stays stdlib-only.

Uses pycryptodome when available for speed, otherwise falls back to a
straightforward table-free implementation (save files are small)."""

try:  # pragma: no cover - optional fast path
    from Crypto.Cipher import AES as _AES
except ImportError:  # pragma: no cover
    _AES = None


def _xtime(a):
    a <<= 1
    return (a ^ 0x11B) & 0xFF if a & 0x100 else a


def _build_sbox():
    sbox = [0] * 256
    p = q = 1
    while True:
        # p *= 3
        p = p ^ _xtime(p)
        # q /= 3
        q ^= q << 1
        q ^= q << 2
        q ^= q << 4
        q &= 0xFF
        if q & 0x80:
            q ^= 0x09
        x = q ^ ((q << 1) | (q >> 7)) ^ ((q << 2) | (q >> 6)) ^ \
            ((q << 3) | (q >> 5)) ^ ((q << 4) | (q >> 4))
        sbox[p] = (x ^ 0x63) & 0xFF
        if p == 1:
            break
    sbox[0] = 0x63
    inv = [0] * 256
    for i, v in enumerate(sbox):
        inv[v] = i
    return sbox, inv


SBOX, INV_SBOX = _build_sbox()


def _mul(a, b):
    r = 0
    while b:
        if b & 1:
            r ^= a
        a = _xtime(a)
        b >>= 1
    return r


def _expand_key(key):
    nk = len(key) // 4
    nr = nk + 6
    w = [list(key[4 * i:4 * i + 4]) for i in range(nk)]
    rcon = 1
    for i in range(nk, 4 * (nr + 1)):
        t = list(w[i - 1])
        if i % nk == 0:
            t = t[1:] + t[:1]
            t = [SBOX[b] for b in t]
            t[0] ^= rcon
            rcon = _xtime(rcon)
        elif nk > 6 and i % nk == 4:
            t = [SBOX[b] for b in t]
        w.append([a ^ b for a, b in zip(w[i - nk], t)])
    return [sum(w[4 * r:4 * r + 4], []) for r in range(nr + 1)]


class _PyAES:
    def __init__(self, key):
        if len(key) not in (16, 24, 32):
            raise ValueError("bad AES key length")
        self.rk = _expand_key(key)
        self.nr = len(self.rk) - 1

    @staticmethod
    def _add(s, k):
        return [a ^ b for a, b in zip(s, k)]

    def encrypt_block(self, blk):
        s = self._add(list(blk), self.rk[0])
        for r in range(1, self.nr + 1):
            s = [SBOX[b] for b in s]
            s = [s[(i + 4 * (i % 4)) % 16] for i in range(16)]  # ShiftRows
            if r != self.nr:
                n = []
                for c in range(4):
                    a = s[4 * c:4 * c + 4]
                    n += [_mul(a[0], 2) ^ _mul(a[1], 3) ^ a[2] ^ a[3],
                          a[0] ^ _mul(a[1], 2) ^ _mul(a[2], 3) ^ a[3],
                          a[0] ^ a[1] ^ _mul(a[2], 2) ^ _mul(a[3], 3),
                          _mul(a[0], 3) ^ a[1] ^ a[2] ^ _mul(a[3], 2)]
                s = n
            s = self._add(s, self.rk[r])
        return bytes(s)

    def decrypt_block(self, blk):
        s = self._add(list(blk), self.rk[self.nr])
        for r in range(self.nr - 1, -1, -1):
            s = [s[(i - 4 * (i % 4)) % 16] for i in range(16)]  # InvShiftRows
            s = [INV_SBOX[b] for b in s]
            s = self._add(s, self.rk[r])
            if r != 0:
                n = []
                for c in range(4):
                    a = s[4 * c:4 * c + 4]
                    n += [_mul(a[0], 14) ^ _mul(a[1], 11) ^ _mul(a[2], 13) ^ _mul(a[3], 9),
                          _mul(a[0], 9) ^ _mul(a[1], 14) ^ _mul(a[2], 11) ^ _mul(a[3], 13),
                          _mul(a[0], 13) ^ _mul(a[1], 9) ^ _mul(a[2], 14) ^ _mul(a[3], 11),
                          _mul(a[0], 11) ^ _mul(a[1], 13) ^ _mul(a[2], 9) ^ _mul(a[3], 14)]
                s = n
        return bytes(s)


class AesEcb:
    def __init__(self, key: bytes):
        self._fast = _AES.new(key, _AES.MODE_ECB) if _AES else None
        self._slow = None if self._fast else _PyAES(key)

    def encrypt(self, data: bytes) -> bytes:
        if len(data) % 16:
            raise ValueError("ECB data must be a multiple of 16 bytes")
        if self._fast:
            return self._fast.encrypt(data)
        return b"".join(self._slow.encrypt_block(data[i:i + 16]) for i in range(0, len(data), 16))

    def decrypt(self, data: bytes) -> bytes:
        if len(data) % 16:
            raise ValueError("ECB data must be a multiple of 16 bytes")
        if self._fast:
            return self._fast.decrypt(data)
        return b"".join(self._slow.decrypt_block(data[i:i + 16]) for i in range(0, len(data), 16))
