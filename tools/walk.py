"""Walk a decrypted payload using the read-size sequence captured by frida recon.
usage: python tools/walk.py <stats.json> <ctx> <payload.bin> [endian] [show_blob_sizes...]"""
import json, struct, sys


def walk(seq, data):
    off = 0
    for n in seq:
        yield off, n, data[off:off + n]
        off += n


if __name__ == '__main__':
    s = json.load(open(sys.argv[1]))
    seq = s['seqs'][sys.argv[2] + '|read']
    data = open(sys.argv[3], 'rb').read()
    e = sys.argv[4] if len(sys.argv) > 4 else '<'
    show = {int(x) for x in sys.argv[5:]}
    print('seq total', sum(seq), 'payload', len(data))
    for off, n, b in walk(seq, data):
        if n in show:
            words = ' '.join(f'{struct.unpack(e + "I", b[i:i+4])[0]:08x}' for i in range(0, n - n % 4, 4))
            print(f'{off:06x} [{n}] {words}')
