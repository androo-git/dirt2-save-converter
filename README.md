# DiRT 2 Save Converter (Xbox 360 → PC)

Move your **Colin McRae: DiRT 2** (2009) career from the Xbox 360 to the PC version: XP and level, money, unlocked cars, liveries and events, race history, car setups and everything else the game stores in its save.

> How the save format was cracked, and why the conversion works the way it does:
> [docs/HOW_IT_WAS_MADE.md](docs/HOW_IT_WAS_MADE.md)
> In the future this will be streamlined into an executable you can run automatically, hopefully with a GUI explaining each stage of the conversion process. For now, each stage is broken into separate commands so it is clear what the program does.

---

## Requirements

| What | Notes |
|---|---|
| **DiRT 2 for PC** | Recommended: **Rohan Kar's DiRT 2 copy on archive.org**. The tool was built and tested against that build (`dirt2_game.exe`, 23,090,480 bytes, SHA-256 `49B1E00E…EB54FE48`). The tool checks the exe before it does anything and refuses to run on a different build. |
| **DiRT 2 for Xbox 360**, plus the console that holds your save | |
| **A USB mass storage device** | A USB stick or drive that the Xbox 360 can use as storage. This is how the save gets from the console to the PC. |
| **A Windows PC with Python 3.9 or newer** | Get Python from [python.org](https://www.python.org/downloads/) and tick "Add python.exe to PATH" during install. |

**Regions:** the tool should work with a DiRT 2 save from any region - the NTSC and PAL copies are identical from my research. If your save isn't detected, see [Troubleshooting](#troubleshooting).

---

## How it works

DiRT 2 saves are a set of small objects (career, unlocks, race history, ...). Each one is AES-256 encrypted and serialised in the platform's native byte order: big-endian on the Xbox 360, little-endian on PC. The encryption, the container format and the file-name scrambling are handled offline by this tool. Rewriting every field in the opposite byte order offline would mean knowing the exact layout of every object. Many of those layouts depend on the game's own data tables.

So, this tool lets **the PC game do the parsing**. While the game loads the staged save, `assist` hooks the game's save-stream read function and byte-swaps each value at the moment it's read. The game ends up with your 360 career in memory, and its next save writes a normal PC save. Full details are in [docs/HOW_IT_WAS_MADE.md](docs/HOW_IT_WAS_MADE.md).

## Commands

| Command | Purpose |
|---|---|
| `find` | Search all drives for DiRT 2 Xbox 360 saves |
| `info [file]` | Show the 360 save package's contents |
| `prepare [file]` | Back up the PC slot and stage the 360 save into it |
| `assist` | Hook the game during load so it converts and re-saves (`--mode recon` only logs) |
| `verify` | Show what the PC slot contains and whether it's native PC data |
| `backup` / `restore` | Manage slot backups |
| `extract`, `dump` | Analysis helpers |

## Repository layout

```
dirt2conv/        the converter (python -m dirt2conv ...)
  stfs.py           Xbox 360 STFS/CON package reader
  savefile.py       save container: headers, checksums, AES-256 chunks
  aes.py            pure-Python AES (uses pycryptodome if present)
  names.py          PC file-name cipher
  stage.py          builds the hybrid slot, Profile XML merge, backups
  assist.py         Frida host;  frida_agent.js = the in-game hook
  verify.py         slot inspection
  config.py         settings from .env / environment / defaults
tools/            reverse-engineering scripts (need requirements-dev.txt)
docs/             write-up of how the format was reverse engineered
```

## License

[GNU General Public License v3.0](LICENSE) or later.

## Disclaimer

This project includes no game files. You need your own copies of the game. It is not affiliated with Codemasters. Back up your saves; use at your own risk.


## File transfer, installation and conversion process

### Part 1: Copy the save off the Xbox 360

1. Plug the USB storage device into the Xbox 360. If the console hasn't used it before, it will offer to **configure it as a storage device**. Accept. This formats the drive, so copy anything you want to keep off it first.
2. Boot the Xbox 360 and go to **Settings**, then **Storage** (on newer dashboards this is **Settings > System > Storage**).
3. Select the storage device that holds your DiRT 2 save. Depending on where you saved, it's one of:
   - **Hard Drive** (internal HDD)
   - **Memory Unit / flash memory**
   - **USB Storage Device**
   - **Cloud Saved Games**
4. Open **Games and Apps**, then **DiRT 2**, and select the saved game.
5. Press **Copy** and choose the **USB Storage Device** as the destination.
6. When the copy finishes, unplug the USB device and plug it into your PC.

On the USB device the save sits in a hidden folder, either
`Content\<your profile id>\434D0819\00000001\<save file>` (newer dashboards) or
`Xbox360\Content\<your profile id>\434D0819\00000001\<save file>`.
You don't have to find it yourself. The tool searches every drive for both layouts.

---

### Part 2: Install and convert it on the PC

### Backups and undo

> [!NOTE] ALWAYS BACKUP YOUR FILES!
> Please create a backup of your Dirt 2 save before continuing to installation. Outside of bugs with this code, I'm not responsible for your lost save files if you run a command you didn't intend to run.

`prepare` and `restore` will back up the save slot - you can find the backups in `work\backups\` inside this folder.

```powershell
python -m dirt2conv restore                      # list backups
python -m dirt2conv restore Autosave0_20260101_120000
python -m dirt2conv verify                       # show what's in the slot right now
```

Or if you wish to manually backup the save file - keep a copy of the original save somewhere safe:
`Documents\My Games\DiRT2\savegame\Autosave0`.

#### Installation - one-time setup

1. **Install DiRT 2 on the PC and run it once.** Create a profile, get to the main menu so the game autosaves, then quit. The converter needs this fresh PC save, because a few PC-only parts (controller bindings, online data) are kept from it.
2. **Run this tool.** Download or clone this repository, open a terminal (PowerShell) in the repo folder, and run:
   ```powershell
   pip install -r requirements.txt
   ```
   This installs [Frida](https://frida.re), which the converter uses to hook the game while it loads the save (see [How it works](#how-it-works)).
3. *(Optional)* If your save folder or setup is unusual, copy `.env.example` to `.env` and adjust it. On a normal Windows install the defaults work out of the box.

#### Convert

1. **Check the 360 save is found** (USB plugged in):
   ```powershell
   python -m dirt2conv find
   ```
2. **Prepare.** This backs up your current PC save slot and stages the 360 save into it:
   ```powershell
   python -m dirt2conv prepare
   ```
   If more than one save is found, or you copied the file somewhere else, pass the path:
   `python -m dirt2conv prepare "E:\Content\...\434D0819\00000001\<save file>"`.
3. **Assist.** Start the converter, *then* launch the game:
   ```powershell
   python -m dirt2conv assist
   ```
   - When it says `Waiting for dirt2_game.exe`, start DiRT 2 as you normally would.
   - Let your profile load. You should see your 360 driver name and progress.
   - **Make the game save.** Finishing an event is best (it saves career, history and rewards), or save the profile from the menu.
   - Quit the game.

   The tool then checks the slot and should report `format : native PC save`.
4. **Done.** From now on, launch DiRT 2 normally. No tool or hook is needed any more.



---

## What carries over

| From the Xbox 360 | Kept from the PC |
|---|---|
| Career progress, XP/level, money, unlocks, events and missions, race history and records, rewards, friendships/rivals, car settings and setups, trophies in the RV, videos watched, spotter/speech counters, driver name and nationality | Controller/key bindings (`inputData`), online/network data, the save-slot header (`SystemFile`, rebuilt by the game), and the PC account ids inside the profile |

---

## Troubleshooting

- **`No Xbox 360 DiRT 2 save found`**: the save folder is hidden. Turn on "Hidden items" in Explorer and check the USB device has a `Content` (or `Xbox360\Content`) folder. 
    - **Note: saves from other regions may use a different title id:** Find the folder under  `Content\<profile id>\` that holds your save, then either pass the file path to  `prepare`, or add the title id to `.env` with  `DIRT2_X360_TITLE_IDS=434D0819,XXXXXXXX`. Please open an issue with the id so it can be added.
- **`different build ... hook addresses don't match`**: your `dirt2_game.exe` isn't the
  build the tool was made for. The hook addresses only fit one build. Use the recommended
  copy, or open an issue with your exe's SHA-256.
- **The game started a new profile instead of loading the save**: make sure there's exactly
  one save slot folder (`Autosave0`) and you didn't delete or recreate it after `prepare`.
  Run `restore`, then `prepare` again.
- **`assist` says the slot still holds 360 data**: the game didn't save while the tool was
  attached. Run `assist` again and finish an event before quitting.
- **Antivirus complains about Frida**: Frida is a widely used instrumentation toolkit. The tool
  only attaches to `dirt2_game.exe`, and only while `assist` is running.

---

## Future Roadmap

- [ ] Test and confirm game works with unmodified retail copies of Dirt 2 for PC.
- [ ] Create a dirt2-save-converter.exe with a GUI to make the process more friendly.