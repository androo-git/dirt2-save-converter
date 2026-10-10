import struct
from dataclasses import dataclass, field
from typing import List, Optional

BLOCK_SIZE = 0x1000

MAGIC_CON = b"CON "
MAGIC_PIRS = b"PIRS"
MAGIC_LIVE = b"LIVE"

CONTENT_TYPE_NAMES = {
    0x0000001: "Saved Game",
    0x0000002: "Marketplace Content",
    0x0000003: "Publisher",
    0x0001000: "Xbox 360 Title",
    0x0002000: "IPTV Pause Buffer",
    0x0004000: "Installed Game",
    0x0005000: "Xbox Original Game",
    0x0007000: "Game on Demand",
    0x0009000: "Avatar Item",
    0x0010000: "Profile",
    0x0020000: "Gamer Picture",
    0x0030000: "Theme",
    0x0040000: "Cache File",
    0x0050000: "Storage Download",
    0x0060000: "Xbox Saved Game",
    0x0070000: "Xbox Download",
    0x0080000: "Game Demo",
    0x0090000: "Video",
    0x00A0000: "Game Title",
    0x00B0000: "Installer",
    0x00C0000: "Game Trailer",
    0x00D0000: "Arcade Title",
    0x00E0000: "XNA",
    0x00F0000: "License Store",
    0x0100000: "Movie",
    0x0200000: "TV",
    0x0300000: "Music Video",
    0x0400000: "Game Video",
    0x0500000: "Podcast Video",
    0x0600000: "Viral Video",
    0x2000000: "Community Game",
}


class StfsError(Exception):
    pass


def _u16be(b, o):
    return (b[o] << 8) | b[o + 1]


def _u24be(b, o):
    return (b[o] << 16) | (b[o + 1] << 8) | b[o + 2]


def _u32be(b, o):
    return struct.unpack_from(">I", b, o)[0]


def _u32le(b, o):
    return struct.unpack_from("<I", b, o)[0]


def _u24le(b, o):
    return b[o] | (b[o + 1] << 8) | (b[o + 2] << 16)


@dataclass
class FileEntry:
    name: str
    is_directory: bool
    is_contiguous: bool
    block_count: int
    start_block: int
    path_index: int
    size: int
    update_time: int
    access_time: int
    index: int

    def path(self) -> str:
        return "/" + self.name if not self.is_directory else "/" + self.name


@dataclass
class StfsHeader:
    magic: bytes
    header_size: int
    metadata_version: int
    content_type: int
    content_size: int
    media_id: int
    version: int
    base_version: int
    title_id: int
    platform: int
    save_game_id: int
    console_id: bytes
    profile_id: bytes
    block_separation: int
    file_table_block_count: int
    file_table_block: int
    data_file_count: int
    descriptor_type: int
    display_name: str
    display_description: str
    publisher_name: str
    title_name: str
    extra: dict = field(default_factory=dict)

    @property
    def content_type_name(self) -> str:
        return CONTENT_TYPE_NAMES.get(self.content_type, f"0x{self.content_type:X}")

    @property
    def platform_name(self) -> str:
        return {2: "Xbox 360", 4: "PC"}.get(self.platform, f"0x{self.platform:X}")


class StfsPackage:
    def __init__(self, data: bytes):
        if len(data) < 0xD000:
            raise StfsError(f"file too small for STFS: {len(data)} bytes (need >= 0xD000)")
        self.data = data
        magic = data[0:4]
        if magic not in (MAGIC_CON, MAGIC_PIRS, MAGIC_LIVE):
            raise StfsError(f"not an STFS package (magic={magic!r})")
        self.header = self._parse_header()
        self.data_start = self._find_data_start()
        self.entries: List[FileEntry] = self._parse_file_table()

    def _parse_header(self) -> StfsHeader:
        d = self.data
        header_size = _u32be(d, 0x340)
        metadata_version = _u32be(d, 0x348)
        vd = 0x379

        def _utf16be(o, length):
            raw = d[o:o + length]
            text = raw.decode("utf-16-be", errors="ignore").split("\x00")[0]
            return text.strip()

        return StfsHeader(
            magic=d[0:4],
            header_size=header_size,
            metadata_version=metadata_version,
            content_type=_u32be(d, 0x344),
            content_size=struct.unpack_from(">Q", d, 0x34C)[0],
            media_id=_u32be(d, 0x354),
            version=_u32be(d, 0x358),
            base_version=_u32be(d, 0x35C),
            title_id=_u32be(d, 0x360),
            platform=d[0x364],
            save_game_id=_u32be(d, 0x368),
            console_id=d[0x36C:0x371],
            profile_id=d[0x371:0x379],
            block_separation=d[vd + 2],
            file_table_block_count=_u16be(d, vd + 3),
            file_table_block=_u24be(d, vd + 5),
            data_file_count=_u32be(d, 0x39D),
            descriptor_type=_u32be(d, 0x3A9),
            display_name=_utf16be(0x411, 0x80),
            display_description=_utf16be(0xD11, 0x80),
            publisher_name=_utf16be(0x1611, 0x80),
            title_name=_utf16be(0x1691, 0x80),
        )

    def _entry_is_valid(self, offset: int) -> bool:
        if offset + 64 > len(self.data):
            return False
        flags = self.data[offset + 0x28]
        name_len = flags & 0x3F
        if name_len < 1 or name_len > 40:
            return False
        name = self.data[offset:offset + name_len]
        return all(0x20 <= c < 0x7F for c in name)

    def _find_data_start(self) -> int:
        for candidate in (0xC000, 0xD000):
            if self._entry_is_valid(candidate):
                return candidate
        raise StfsError("could not locate STFS file table (tried 0xC000, 0xD000)")

    def _hash_gap_blocks(self, block: int) -> int:
        gap = 0
        step = 170
        while block >= step:
            gap += 1
            block //= 170
            step *= 170
        return gap

    def _data_offset(self, block: int) -> int:
        return (self.data_start + block * BLOCK_SIZE
                + self._hash_gap_blocks(block) * BLOCK_SIZE)

    def _parse_file_table(self) -> List[FileEntry]:
        table_size = self.header.file_table_block_count * BLOCK_SIZE
        if table_size <= 0:
            table_size = 0x1000
        table = self.data[self.data_start:self.data_start + table_size]
        entries: List[FileEntry] = []
        for i in range(len(table) // 64):
            cur = table[i * 64:(i + 1) * 64]
            flags = cur[0x28]
            name_len = flags & 0x3F
            if name_len == 0:
                break
            name = cur[0:name_len].decode("ascii", errors="replace").rstrip("\x00")
            entries.append(FileEntry(
                name=name,
                is_directory=bool(flags & 0x80),
                is_contiguous=bool(flags & 0x40),
                block_count=_u24le(cur, 0x29),
                start_block=_u24le(cur, 0x2F),
                path_index=_u16be(cur, 0x32),
                size=_u32be(cur, 0x34),
                update_time=_u32be(cur, 0x38),
                access_time=_u32be(cur, 0x3C),
                index=i,
            ))
        return entries

    def iter_files(self):
        return [e for e in self.entries if not e.is_directory]

    def read(self, entry: FileEntry) -> bytes:
        if entry.is_directory:
            raise StfsError(f"{entry.name} is a directory")
        out = bytearray()
        block = entry.start_block
        remaining = entry.size
        for _ in range(entry.block_count):
            offset = self._data_offset(block)
            chunk = self.data[offset:offset + BLOCK_SIZE]
            take = min(len(chunk), max(remaining, 0))
            out += chunk[:take]
            remaining -= take
            block += 1
            if remaining <= 0:
                break
        return bytes(out[:entry.size])

    def describe(self) -> str:
        h = self.header
        lines = [
            f"magic            : {h.magic.decode('ascii', 'replace')}",
            f"header size      : 0x{h.header_size:X}",
            f"metadata version : {h.metadata_version}",
            f"content type     : {h.content_type_name} (0x{h.content_type:X})",
            f"content size     : {h.content_size}",
            f"title id         : 0x{h.title_id:X}",
            f"save game id     : 0x{h.save_game_id:X}",
            f"platform         : {h.platform_name} ({h.platform})",
            f"block separation : {h.block_separation}",
            f"file table block : {h.file_table_block} (count {h.file_table_block_count})",
            f"data start       : 0x{self.data_start:X}",
            f"display name     : {h.display_name!r}",
            f"title name       : {h.title_name!r}",
            "",
            "files:",
        ]
        for e in self.entries:
            kind = "DIR " if e.is_directory else "FILE"
            lines.append(
                f"  [{kind}] {e.name:<40} {e.size:>10} bytes "
                f"start={e.start_block} blocks={e.block_count} path={e.path_index}")
        return "\n".join(lines)
