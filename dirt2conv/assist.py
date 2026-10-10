"""Game-assisted conversion: attach to the running PC game with Frida and
byte-swap the Xbox 360 objects while the game loads them.

The PC game does all the parsing; we only fix byte order at the moment each
value is read. After the game saves, the slot contains a native PC save and
no hook is needed any more.
"""
import hashlib
import json
import time
from datetime import datetime
from pathlib import Path

from . import config

AGENT = Path(__file__).with_name("frida_agent.js")
PROCESS_NAME = "dirt2_game.exe"

# Build the hook addresses were taken from (Rohan Kar's archive.org copy).
KNOWN_BUILDS = {
    "49B1E00EA1D4BD02E633CEED63390B5CAE07601333F673C4EFD8D2F0EB54FE48":
        "dirt2_game.exe, 23,090,480 bytes",
}

# Agent object names (Load functions) whose data comes from the 360 save.
CONVERT_OBJECTS = [
    "voiceCounters", "rvInteriorManager", "VehicleSettingsManager", "RaceHistory",
    "VideoPlayedManager", "VehicleSetupSavedData", "Unlocks", "FriendshipManager",
    "rewards_save", "career", "obj_7a06e0", "obj_7a0a90", "obj_7a0e60",
    "dlc_unlock", "missions", "eventSpeech", "obj_careerdamage", "obj_12ff70c",
]


def sha256(path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest().upper()


def run(mode="convert", force=False, log_dir=None, timeout=None):
    try:
        import frida
    except ImportError:
        raise SystemExit("frida is required for this step:  pip install frida")

    log_dir = Path(log_dir or (config.work_dir() / "logs"))
    log_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_path = log_dir / f"{mode}_{stamp}.jsonl"
    stats_path = log_dir / f"{mode}_{stamp}_stats.json"

    dev = frida.get_local_device()
    print(f"Waiting for {PROCESS_NAME} ... start DiRT 2 now.")
    t0 = time.time()
    pid = None
    while pid is None:
        for p in dev.enumerate_processes():
            if p.name.lower() == PROCESS_NAME:
                pid = p.pid
        if pid is None:
            if timeout and time.time() - t0 > timeout:
                raise SystemExit("timed out waiting for the game")
            time.sleep(0.2)

    session = dev.attach(pid)
    script = session.create_script(AGENT.read_text(encoding="utf-8"))
    log = open(log_path, "w", encoding="utf-8")
    loads, failures = [], []

    def on_message(msg, _data):
        if msg["type"] != "send":
            print("agent:", msg.get("description", msg))
            log.write(json.dumps(msg) + "\n")
            return
        p = msg["payload"]
        log.write(json.dumps(p) + "\n")
        log.flush()
        ev = p.get("ev")
        if ev == "leave" and p["kind"] == "load":
            loads.append(p["name"])
            if p["ret"] != 0:
                failures.append(p["name"])
            print(f"  loaded {p['name']:24} {'ok' if p['ret'] == 0 else 'ERROR %d' % p['ret']}")
        elif ev == "leave" and p["kind"] == "save":
            print(f"  saved  {p['name']}")
        elif ev in ("error", "blob"):
            print("  ", p)

    detached = {"v": False}
    script.on("message", on_message)
    session.on("detached", lambda *a: detached.update(v=True))
    script.load()

    res = script.exports_sync.init({"mode": mode, "force": force,
                                    "convert": CONVERT_OBJECTS if mode == "convert" else []})
    exe = res.get("path")
    if exe:
        try:
            digest = sha256(exe)
            print(f"Game build: {KNOWN_BUILDS.get(digest, 'UNKNOWN build')} (sha256 {digest[:16]}...)")
        except OSError:
            pass
    if not res.get("ok"):
        session.detach()
        msg = "\n  ".join(res.get("mismatches", []))
        raise SystemExit("This dirt2_game.exe is a different build from the one this tool was made "
                         f"for, so the hook addresses don't match:\n  {msg}\n"
                         "Nothing was hooked. (Use --force only if you know what you're doing.)")

    print(f"Attached ({mode} mode). Load your profile, then make the game save "
          "(finish an event or save the profile), then quit the game.")

    def dump():
        try:
            json.dump(script.exports_sync.dump(), open(stats_path, "w"), indent=1)
        except Exception:
            pass

    try:
        last = 0
        while not detached["v"]:
            time.sleep(0.5)
            if time.time() - last > 3:
                dump()
                last = time.time()
    except KeyboardInterrupt:
        dump()
        session.detach()
    log.close()
    print(f"Game closed. Log: {log_path}")
    if mode == "convert" and not loads:
        print("WARNING: the game never loaded the save while attached. Was the slot staged, "
              "and did the profile load? Run `prepare` again and retry.")
    if failures:
        print("WARNING: these objects reported load errors:", ", ".join(failures))
    return loads, failures
