"""Scan the game executable for well-known crypto constants."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _common import game_exe  # noqa: E402

EXE = sys.argv[1] if len(sys.argv) > 1 else game_exe()
data = open(EXE, 'rb').read()

sbox = bytes.fromhex('637c777bf26b6fc53001672bfed7ab76ca82c97dfa5947f0add4a2af9ca472c0')
inv_sbox = bytes.fromhex('52096ad53036a538bf40a39e81f3d7fb7ce339829b2fff87348e4344c4dee9cb')
sigs = {
    'AES S-box': sbox,
    'AES inv S-box': inv_sbox,
    'AES Te0 (LE)': bytes.fromhex('a56363c6847c7cf8'),
    'AES Te0 (BE)': bytes.fromhex('c66363a5f87c7c84'),
    'AES Td0 (LE)': bytes.fromhex('a7f45150'.replace(' ', '')),
    'AES Td0 (BE)': bytes.fromhex('5051f4a7'),
    'AES rcon': bytes.fromhex('01020408102040801b36'),
    'Blowfish P (LE)': bytes.fromhex('886a3f24d308a385'),
    'Blowfish P (BE)': bytes.fromhex('243f6a8885a308d3'),
    'TEA delta (LE)': bytes.fromhex('b979379e'),
    'TEA -delta (LE)': bytes.fromhex('4786c861'),
    'TEA sum32 (LE)': bytes.fromhex('2037efc6'),
    'Twofish q0': bytes.fromhex('a967b3e804fda3768'[:16]),
    'MD5 init (LE)': bytes.fromhex('0123456789abcdef'),
    'SHA1 K (LE)': bytes.fromhex('9979825a'),
    'CRC32 table (LE)': bytes.fromhex('0000000096300777'),
    'XOR key K': bytes.fromhex('1FBF07A5E2966A380C837EF7D004E8D2'),
    'K first half': bytes.fromhex('1FBF07A5E2966A38'),
}
for name, sig in sigs.items():
    hits = []
    i = data.find(sig)
    while i != -1 and len(hits) < 8:
        hits.append(hex(i)); i = data.find(sig, i + 1)
    print(f'{name:20s} {hits}')
