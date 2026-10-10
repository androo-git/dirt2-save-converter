// Frida agent for DiRT 2 (PC, dirt2_game.exe) save conversion.
//
// The PC game's save stream Read(buf, n) (VA 0xC07710) is hooked. While a
// "convert" object's Load() is on the stack, every scalar read (2/4/8 bytes)
// is byte-reversed, so the PC loader correctly parses big-endian Xbox 360 data.
// The game then holds the 360 progress in memory and writes a native PC save
// the next time it saves.
//
// rpc.exports.init({mode: 'recon'|'convert', convert: [names...]})

'use strict';

const IMAGE_BASE = 0x400000;
const mod = Process.getModuleByName('dirt2_game.exe');
const va = (x) => mod.base.add(x - IMAGE_BASE);
const rva = (p) => '0x' + (p.sub(mod.base).toUInt32() + IMAGE_BASE).toString(16);

const STREAM_READ = 0xC07710;
const STREAM_WRITE = 0xBF9570;

// Bytes expected at a few hook sites. All addresses in this file are specific
// to one dirt2_game.exe build; if these don't match, nothing is hooked.
const SIGNATURES = [
  [0xC07710, '83ec085355568bf1'],   // save stream Read
  [0xBF9570, '83ec0853558be98b'],   // save stream Write
  [0x44F800, '5155568b74241057'],   // voiceCounters Load
  [0x6E7B00, '558bec83e4c081ec'],   // RaceHistory Load body
  [0x737140, '568b7424088b068b'],   // VehicleSetupSavedData Load
];

function checkBuild() {
  const bad = [];
  for (const [addr, hex] of SIGNATURES) {
    let got;
    try {
      if (addr - IMAGE_BASE + hex.length / 2 > mod.size) throw new Error('outside module');
      const b = new Uint8Array(va(addr).readByteArray(hex.length / 2));
      got = Array.from(b, (x) => x.toString(16).padStart(2, '0')).join('');
    } catch (e) {
      got = 'unreadable';
    }
    if (got !== hex) bad.push(`0x${addr.toString(16)}: expected ${hex} got ${got}`);
  }
  return bad;
}

// [name, Save VA, Load VA]  (from vtables of classes deriving the save-object base)
const OBJECTS = [
  ['voiceCounters',          0x44F7A0, 0x44F800],
  ['obj_careerdamage',       0x564250, 0x5642C0],
  ['obj_12ff70c',            0x564140, 0x564190],
  ['rvInteriorManager',      0x566E70, 0x566EB0],
  ['VehicleSettingsManager', 0x6CEB90, 0x6CEC00],
  ['RaceHistory',            0x71C770, 0x71C780],
  ['VideoPlayedManager',     0x726D30, 0x726D80],
  ['VehicleSetupSavedData',  0x727250, 0x737140],
  ['Unlocks',                0x73B520, 0x73B630],
  ['FriendshipManager',      0x73E0F0, 0x73E050],
  ['rewards_save',           0x73EF60, 0x751A90],
  ['career',                 0x743FC0, 0x75CF40],
  ['obj_7a06e0',             0x7A07D0, 0x7A0900],
  ['obj_7a0a90',             0x7A0B80, 0x7A0C60],
  ['obj_7a0e60',             0x7A1030, 0x7A10E0],
  ['dlc_unlock',             0x7B9030, 0x7B9080],
  ['missions',               0x7CA330, 0x7CA490],
  ['net_news',               0x817220, 0x817230],
  ['NetSafetyRating',        0x821980, 0x8219B0],
  ['NetRaceEvents',          0x830210, 0x863E20],
  ['NetSavedData',           0x888330, 0x888350],
  ['eventSpeech',            0x9CC200, 0x9CC300],
  ['SystemFile',             0xAF5480, 0xAF5600],
  ['obj_b0b710',             0xAE6190, 0xAE61A0],
  ['GhostLap',               0xB06510, 0xB28470],
  ['ActionMap',              0xAF47E0, 0xB421A0],
  ['obj_c26a40',             0xBE7F20, 0xBE7F30],
  ['obj_c9ad60',             0xC93DA0, 0xC97630],
];

let MODE = 'recon';
let CONVERT = new Set();
const ctx = {};          // threadId -> stack of {name, kind}
let lastFile = null;

function top(tid) {
  const s = ctx[tid];
  return s && s.length ? s[s.length - 1] : null;
}

function bswapInPlace(p, n) {
  const b = new Uint8Array(p.readByteArray(n));
  b.reverse();
  p.writeByteArray(b.buffer);
}

function swapWords(p, n) {
  for (let o = 0; o + 4 <= n; o += 4) bswapInPlace(p.add(o), 4);
}

// VehicleSetupSavedData record (0x3C): u32 bitfield (six 3-bit fields),
// char name[0x14], 9 x u32.  360 allocates bitfields from the MSB.
function convSetupRecord(p) {
  const raw = new Uint8Array(p.readByteArray(4));
  const v = ((raw[0] << 24) | (raw[1] << 16) | (raw[2] << 8) | raw[3]) >>> 0;
  let out = 0;
  for (let i = 0; i < 6; i++) out |= ((v >>> (29 - 3 * i)) & 7) << (3 * i);
  p.writeU32(out >>> 0);
  for (let o = 0x18; o < 0x3C; o += 4) bswapInPlace(p.add(o), 4);
}

// 8-byte reads that are really two u32 (RaceHistory map record field, read at 0x70A9D4)
const PAIR8_RET = new Set(['0x70a9d6']);

// POD record layouts (offsets of f64 fields) for blob reads; everything else is u32.
// An empty list = known all-u32 record (converted silently).
const BLOB_F64 = {
  'RaceHistory:40': [24],
  'RaceHistory:1016': [8, 16],
  'RaceHistory:12': [],
  'RaceHistory:48': [],
  'RaceHistory:60': [],
  'RaceHistory:68': [],
  'career:12': [],
  'rewards_save:16': [],
};

function swapLayout(p, n, f64s) {
  let o = 0;
  while (o + 4 <= n) {
    if (f64s.indexOf(o) !== -1) { bswapInPlace(p.add(o), 8); o += 8; }
    else { bswapInPlace(p.add(o), 4); o += 4; }
  }
}

function convertRead(name, p, n, ra) {
  if (n === 1) return 'u8';
  if (n === 8 && PAIR8_RET.has(ra)) { swapWords(p, 8); return 'pair'; }
  if (n === 2 || n === 4 || n === 8) { bswapInPlace(p, n); return 'swap'; }
  const lay = BLOB_F64[name + ':' + n];
  if (lay) { swapLayout(p, n, lay); return 'layout'; }
  if (name === 'VehicleSetupSavedData' && n === 0x3C) { convSetupRecord(p); return 'setup'; }
  if (name === 'VehicleSetupSavedData' && n === 0xF00) {
    for (let i = 0; i < 64; i++) convSetupRecord(p.add(i * 0x3C));
    return 'setup[64]';
  }
  if (n % 4 === 0) { swapWords(p, n); return 'BLOB-words'; }
  return 'BLOB-raw';
}

const stats = {};       // "name|kind|n" -> count
const seqs = {};        // name -> array of sizes (first 4000)
function note(name, kind, n, how) {
  const k = name + '|' + kind + '|' + n + '|' + how;
  stats[k] = (stats[k] || 0) + 1;
  const sk = name + '|' + kind;
  if (!seqs[sk]) seqs[sk] = [];
  if (seqs[sk].length < 20000) seqs[sk].push(n);
}

function hookObjects() {
  for (const [name, save, load] of OBJECTS) {
    for (const [kind, addr] of [['save', save], ['load', load]]) {
      try {
        Interceptor.attach(va(addr), {
          onEnter() {
            const t = this.threadId;
            (ctx[t] = ctx[t] || []).push({ name, kind });
            this.t = t;
            send({ ev: 'enter', name, kind, file: lastFile });
          },
          onLeave(ret) {
            const s = ctx[this.t];
            if (s) s.pop();
            send({ ev: 'leave', name, kind, ret: ret.toInt32() });
          },
        });
      } catch (e) {
        send({ ev: 'error', msg: `hook ${name}.${kind} @${addr.toString(16)}: ${e}` });
      }
    }
  }
}

function hookStream() {
  Interceptor.attach(va(STREAM_READ), {
    onEnter(args) {
      this.p = args[0];
      this.n = args[1].toInt32();
      this.top = top(this.threadId);
      if (!this.top || this.n === 8) this.caller = rva(this.returnAddress);
    },
    onLeave(ret) {
      const name = this.top ? this.top.name : ('?' + this.caller);
      let how = 'raw';
      if (ret.toInt32() === 0 && MODE === 'convert' && this.top && CONVERT.has(this.top.name)) {
        how = convertRead(this.top.name, this.p, this.n, this.caller);
        if (how.startsWith('BLOB')) send({ ev: 'blob', name, n: this.n, how });
      }
      note(name, 'read', this.n, how);
    },
  });
  Interceptor.attach(va(STREAM_WRITE), {
    onEnter(args) {
      const t = top(this.threadId);
      note(t ? t.name : ('?' + rva(this.returnAddress)), 'write', args[1].toInt32(), '-');
    },
  });
}

function hookFiles() {
  const k32 = Process.getModuleByName('kernel32.dll');
  for (const fn of ['CreateFileW', 'CreateFileA']) {
    const p = k32.findExportByName(fn);
    if (!p) continue;
    Interceptor.attach(p, {
      onEnter(args) {
        const s = fn.endsWith('W') ? args[0].readUtf16String() : args[0].readAnsiString();
        if (s && s.toLowerCase().indexOf('savegame') !== -1) {
          lastFile = s.split(/[\\/]/).pop();   // file name only, no user paths in logs
          send({ ev: 'open', file: lastFile, write: (args[1].toUInt32() & 0x40000000) !== 0 });
        }
      },
    });
  }
}

rpc.exports = {
  init(cfg) {
    const bad = checkBuild();
    if (bad.length && !cfg.force) {
      return { ok: false, mismatches: bad, path: mod.path, size: mod.size };
    }
    MODE = cfg.mode;
    CONVERT = new Set(cfg.convert || []);
    hookObjects();
    hookStream();
    hookFiles();
    send({ ev: 'ready', mode: MODE, convert: [...CONVERT] });
    return { ok: true, mismatches: bad, path: mod.path, size: mod.size };
  },
  dump() {
    return { stats, seqs };
  },
};
