# How the DiRT 2 Xbox 360 → PC save converter was made

This is a write-up of the reverse-engineering process, including the dead ends. It also
works as a reference for the save format.

Everything here was worked out from three things: an Xbox 360 save, a save made by the PC
game, and the PC executable (`dirt2_game.exe`, 23,090,480 bytes, SHA-256
`49B1E00EA1D4BD02E633CEED63390B5CAE07601333F673C4EFD8D2F0EB54FE48`). All virtual addresses
(VAs) below are for that build, with image base `0x400000`.

---

## 1. Getting the data off the 360: the STFS package

An Xbox 360 save is an **STFS "CON " package** (Xbox's container format, also used for DLC and
profiles). DiRT 2's title id is `0x434D0819`. On a USB device it sits in a hidden folder at
`Content\<profile id>\434D0819\00000001\<file>` (or under `Xbox360\Content\` on older
dashboards; `00000001` = content type "Saved
Game").

`dirt2conv/stfs.py` is a small STFS reader: it parses the header (title id, display name,
file table location), walks the file table at `0xC000` or `0xD000`, and reads each file's
4 KiB blocks, skipping the hash-table blocks STFS puts between them.

Inside is one directory, `Autosave`, with **21 objects**: `SystemFile`, `Profile`,
`RaceHistory`, `Unlocks`, `missions`, `career manager sdu name`, `rewards_save`, and so on.
The PC game writes the same 21 objects as separate files in
`Documents\My Games\DiRT2\savegame\Autosave0\`.

## 2. File names on PC

The PC file names look random (`NXDSMWW`, `PGRRLTKJNZI`, `AGGRIC CZVKEKG WOM MIWC`, ...).
They are the logical names run through a **Vigenère cipher**:

- key `[24, 6, 15, 13, 4, 11, 18, 16, 25, 8, 10]` (period 11)
- letters are shifted and upper-cased
- spaces and underscores are copied through but still use up a key position

So `Profile` → `NXDSMWW` and `RaceHistory` → `PGRRLTKJNZI`. All 21 names decode exactly
(`dirt2conv/names.py`).

## 3. The per-object container

Each object has a small header and then its data.

**Xbox 360** (big-endian), 12-byte header:
```
0x00 u32 checksum   = sum of BE u32 words of everything from 0x0C on (mod 2^32)
0x04 u32 version    = 0x26E
0x08 u32 length     = file size - 12
0x0C    chunk stream
```
**PC** (little-endian), 28-byte header:
```
0x00 u32 0x18
0x04 u32 checksum   = sum of LE u32 words of everything from 0x1C on
0x08 u32 version    = 0x26F
0x0C u32 length     = file size - 28
0x10 u32 "marker"   (varies; looks like an uninitialised stack value, 0 for SystemFile)
0x14 u32 0x7FFFFFFF
0x18 u32 0
0x1C    chunk stream
```
The **chunk stream** is a repeated `[u32 size = 0x400][0x400 bytes of ciphertext]`. The size
word uses the platform's byte order.

Rebuilding a container from its parsed parts gives a byte-identical file on both platforms
(`tools/roundtrip.py`).

## 4. The encryption, and the first dead end

The first attempt XOR'd the data with a repeating 16-byte key:
```
1F BF 07 A5 E2 96 6A 38 0C 83 7E F7 D0 04 E8 D2
```
That "worked" in the sense that runs of zeros came out as zeros. Everything else still looked
random (about 7.9 bits/byte of entropy, no readable strings), and transplanting any object
into a PC save crashed the game. For a while the conclusion was that the payload was some
unknown packed binary format.

Two observations broke it open:

1. **Counting identical 16-byte blocks.** Ciphertext blocks repeated at 16-byte-aligned
   positions, both within a file and across *different* files. Data that's just XOR'd
   doesn't do that. A block cipher in **ECB mode** does. So the "XOR key" was simply the
   encryption of an all-zero block, `E(0^16)`, which is the most common plaintext block.
2. **The chunk headers.** The old decoder XOR'd straight through the `u32 0x400` size words,
   which pushed everything after the first chunk 4 bytes out of phase. That explained a
   puzzling "1026-byte block every 0x404 bytes" pattern.

**Finding the key.**
- The exe contains AES `Te`/`Td` lookup tables, so AES was the obvious candidate.
- Trying every 16/24/32-byte window of the exe as a raw AES key found nothing
  (`tools/aes_keyscan.py`).
- Following references to the tables led to the classic **rijndael-api-fst** code, at VAs
  `0x11570E0` (key setup), `0x1163B00` (blockDecrypt) and `0x1163BC0` (blockEncrypt). Its
  `makeKey()` takes the key as an **ASCII hex string**, not raw bytes.
- Testing every 32/48/64-character hex string in the exe found it at file offset `0xF57DC8`:

```
AES-256-ECB key: BF238E52208261B11FB50901E78E45AC4660153565F09295305484E1F05166EC
AES_enc(key, 0^16) = 1FBF07A5E2966A380C837EF7D004E8D2   <- the old "XOR key"
```

The same key is used on both platforms. Decrypting each chunk gives clean, readable
plaintext (`dirt2conv/savefile.py`, `dirt2conv/aes.py`).

## 5. What the plaintext looks like

- **Native byte order.** 360 values are big-endian and PC values little-endian. For example,
  `RaceHistory` starts `00 00 05 39` on the 360 and `39 05 00 00` on PC (the value is 1337).
  That's why transplanting crashed: a big-endian count read as little-endian becomes huge.
- **`Profile`** is a `u32 length` followed by **XML** (`<PlayerProfile>…`). It converts
  easily: fix the length and keep the text. A few account-specific tags are kept from the PC
  profile (`GamerID`, `savegame_user_id`, `profile_id`).
- **`SystemFile`** is the slot header (display strings, timestamps), laid out differently on
  each platform. The PC one is kept, and the game rewrites it.
- The **rest** is raw serialisation: `u8`/`u16`/`u32`/`float`/`double`/`u64` values and plain
  structs, written one after another. There are no type tags.
- Beyond the last value written, the 0x400-byte chunks are padded with **uninitialised
  memory** (stack pointers, old path strings). It's ignored on load.

## 6. Reading the serialisers out of the exe

Every save object derives from one base class: its constructor calls `0x454600(name, manager)`,
and every derived vtable has `0x454660` in slot 3. The tool `tools/saveobjs.py` uses those
signatures to list all the classes:

- vtable slot 0 = `Save(stream)`, slot 1 = `Load(stream)`
- stream vtable `+4` = `Write(ptr, size)`, `+8` = `Read(ptr, size)`
- the save stream's Read is `0xC07710`, its Write is `0xBF9570` (they encrypt/decrypt
  0x400-byte chunks via `0xBF9480` / `0xBF9680`)

Reading the Save functions gives the exact field order and sizes. Some examples:

| Object | Layout |
|---|---|
| `dlc_unlock` | 4 × u8 |
| `voiceCounters` | 100 × u8, u32, u32 |
| `VideoPlayedManager` | u32 n, n × u8 |
| `rvInteriorManager` | 56 × u32 |
| `VehicleSetupSavedData` | record, u32, 64 × record. A record (0x3C bytes) is a u32 **bitfield** of six 3-bit fields, `char[0x14]`, and 9 × u32 |
| `RaceHistory` | magic 1337, 57 × 4 u32, 15 × 4 u32, 4 × u64, lists and maps, then pools of polymorphic records |

Two problems made a purely offline converter impractical:

1. **Many loops have no count in the file.** Their counts come from the game's own data
   tables (how many missions, events, unlock groups), and `RaceHistory` has pools of
   polymorphic objects whose layout depends on their runtime type.
2. **Some structs are written as raw memory blobs.** To swap their bytes you need to know
   which parts are floats, doubles, bytes or bitfields.

The bitfields also show the 360 compiler allocating from the **most significant bit** while
the PC compiler starts at the least significant: the default value `0x00012492` on PC is
`0x49248000` on the 360.

## 7. Letting the game do it: Frida-assisted loading

The PC game already knows every layout, so the plan became: let it parse the 360 data, and
fix byte order at the moment each value is read.

`dirt2conv/frida_agent.js` hooks into the running game:

- **Hook the stream `Read(ptr, n)` at `0xC07710`.** When it returns, the buffer holds bytes
  straight from the file.
- **Hook every object's `Load()`** to know which object is being read, so only objects that
  came from the 360 get converted.
- **Rewrite the buffer** before the game sees it:
  - 1 byte: unchanged
  - 2, 4 or 8 bytes: byte-reversed
  - 8-byte reads that are really two u32 (call site returning to `0x70A9D6`): each half
    swapped separately
  - known struct blobs: swapped field by field (see the table below)
  - any other blob: swapped as u32 words, and logged
- **Hook `CreateFileW`** to log which save file (file name only) is open.
- **Check the build first.** The bytes at five hook sites must match the known build,
  otherwise nothing is hooked.

The game then loads the 360 career correctly, and its next save writes a completely normal
PC save. No hook is needed after that.

### Recon run

Before converting anything, a log-only run (`assist --mode recon`) on a genuine PC save
recorded the size of every read and write per object. That confirmed which `Load()` belongs
to which file, and exposed every blob size that needed a layout:

| Blob | Layout (rest is u32) |
|---|---|
| `RaceHistory`, 40 bytes | f64 at +24 |
| `RaceHistory`, 1016 bytes | f64 at +8 and +16; floats in the tail |
| `RaceHistory`, 12/48/60/68 bytes | all u32 |
| `career`, 12 bytes; `rewards_save`, 16 bytes | all u32 |
| `VehicleSetupSavedData`, 0x3C bytes and 64 × 0x3C | bitfield (mirror the six 3-bit fields), `char[0x14]` left alone, 9 × u32 |

Doubles were found by looking for 8-byte-aligned word pairs with a plausible IEEE exponent,
in both the PC and the 360 data. The pair-of-u32 case was settled by the values: as a
big-endian u64 it would have been 2^32 + 1; as two u32 it's (1, 1).

### Object → file mapping (confirmed at runtime)

| File (logical) | Loader(s) |
|---|---|
| `Unlocks` | `obj_7a0a90`, `obj_7a0e60`, 10 × `obj_7a06e0`, then `Unlocks` (`0x73B630`) |
| `career manager sdu name` | career manager `0x75CF40` |
| `rewards_save` | Rewards `0x751A90` |
| `RaceHistory` | `0x71C780` → `0x6E7B00` |
| `inputData` | ActionMap `0xB421A0` (kept from PC) |
| `net_news_cache`, `ne_net_prize_code_manager`, `Net*` | network objects (kept from PC) |

## 8. Result

The first full conversion loaded every 360 object without errors. After one in-game save the
slot checked out as native PC data:

- the `RaceHistory` header reads 1337 little-endian
- the profile shows the 360 driver
- the slot summary shows the 360 XP total

Career progress, unlocks, history and car setups all carried over.

## Tools used

Python 3 (stdlib only for the converter); [Frida](https://frida.re) for the runtime hook;
[Capstone](https://www.capstone-engine.org/) for disassembly in the analysis scripts;
pycryptodome for fast AES during key hunting.

Analysis scripts in `tools/`:

| Script | Purpose |
|---|---|
| `crypto_scan.py` | find crypto constants in the exe |
| `aes_keyscan.py` | brute-force raw AES keys in the exe |
| `aes_xrefs.py`, `x86.py`, `condense.py` | static analysis helpers: disassemble, find callers and immediate references |
| `saveobjs.py` | enumerate save-object classes and their Save/Load functions |
| `dump_plain.py` | decrypt every object of a 360 and a PC save to `work/plain/` |
| `side.py` | side-by-side BE/LE word view of an object |
| `walk.py` | walk a decrypted object using a recon read trace |
| `roundtrip.py` | byte-exact container round-trip test |

These read the exe location from `DIRT2_GAME_DIR` in `.env`.

## Open questions

- Other regions' title ids and exe builds are untested. The hook addresses only fit the
  build above.
- A fully offline converter could be generated from the read trace of a convert run (it
  records exactly how the PC loader consumed the 360 data), but it would only be valid for
  that particular save.
