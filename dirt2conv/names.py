"""Mapping between DiRT 2's internal save-object names and the file names the
PC build writes to disk.

The PC file name is the logical name run through a Vigenere-style cipher with
the 11-byte key below. Letters are shifted, non-letters (spaces/underscores) are
copied through but still consume a key position. Output is upper-case.
"""

KEY = (24, 6, 15, 13, 4, 11, 18, 16, 25, 8, 10)

# Every object DiRT 2 writes into a save slot.
KNOWN_OBJECTS = [
    "SystemFile", "Profile", "VehicleSettingsManager", "VehicleSetupSavedData",
    "eventSpeech", "voiceCounters", "Unlocks", "missions", "VideoPlayedManager",
    "inputData", "RaceHistory", "dlc_unlock", "rewards_save", "FriendshipManager",
    "rvInteriorManager", "net_news_cache", "ne_net_prize_code_manager",
    "NetRaceEvents", "NetSafetyRating", "NetSavedData", "career manager sdu name",
]


def logical_name(pc_name: str) -> str:
    """PC file name -> logical object name (original casing when known)."""
    dec = decode_name(pc_name)
    for n in KNOWN_OBJECTS:
        if n.upper() == dec:
            return n
    return dec


def encode_name(logical: str) -> str:
    out = []
    for i, ch in enumerate(logical):
        if ch.isalpha():
            out.append(chr((ord(ch.upper()) - 65 + KEY[i % 11]) % 26 + 65))
        else:
            out.append(ch)
    return "".join(out)


def decode_name(pc_name: str) -> str:
    out = []
    for i, ch in enumerate(pc_name):
        if ch.isalpha():
            out.append(chr((ord(ch.upper()) - 65 - KEY[i % 11]) % 26 + 65))
        else:
            out.append(ch)
    return "".join(out)
