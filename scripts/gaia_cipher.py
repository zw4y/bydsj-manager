"""Port of com.gaia.publisher.l white-box cipher (decryption only).

Used to decrypt assets/keyInfo and assets/clientKeyInfo from the Gaia SDK.
The table file (assets/dec_key) is parsed exactly as the Android code does.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ASSETS = ROOT / "dumps" / "20260810" / "gaia_sdk" / "assets"


class B:
    """16-byte state: int[16] + long[4]."""

    __slots__ = ("vals", "longs")

    def __init__(self) -> None:
        self.vals = [0] * 16
        self.longs = [0] * 4

    def copy_from(self, other: "B") -> None:
        self.vals = list(other.vals)
        self.longs = list(other.longs)


class C:
    """4-byte state: int[4] + long."""

    __slots__ = ("vals", "long")

    def __init__(self) -> None:
        self.vals = [0] * 4
        self.long = 0


class Tables:
    def __init__(self) -> None:
        # f3532a: [2][15][32][128]
        self.key0 = [[[None] * 32 for _ in range(15)] for _ in range(2)]
        # f3533b: [2][16][256] -> B
        self.sbox = [[[None] * 256 for _ in range(16)] for _ in range(2)]
        # f3534c / f3535d: [9][16][256] -> C
        self.c1 = [[[None] * 256 for _ in range(16)] for _ in range(9)]
        self.c2 = [[[None] * 256 for _ in range(16)] for _ in range(9)]
        # f3536e / f3537f: [9][12][8][128]
        self.k1 = [[[None] * 8 for _ in range(12)] for _ in range(9)]
        self.k2 = [[[None] * 8 for _ in range(12)] for _ in range(9)]


PERM_DEC = [0, 13, 10, 7, 4, 1, 14, 11, 8, 5, 2, 15, 12, 9, 6, 3]


def ints_from_bytes(data: bytes) -> list[int]:
    return list(data)


def bytes_from_ints(vals: list[int]) -> bytes:
    return bytes(v & 0xFF for v in vals)


def long_from_ints(vals: list[int]) -> int:
    return (
        (vals[0] & 0xFF)
        | ((vals[1] & 0xFF) << 8)
        | ((vals[2] & 0xFF) << 16)
        | ((vals[3] & 0xFF) << 24)
    )


def ints_from_long(value: int) -> list[int]:
    value &= 0xFFFFFFFF
    return [value & 0xFF, (value >> 8) & 0xFF, (value >> 16) & 0xFF, (value >> 24) & 0xFF]


def longs_from_ints(vals: list[int]) -> list[int]:
    return [long_from_ints(vals[i * 4 : i * 4 + 4]) for i in range(4)]


def long_from_bytes(data: bytes) -> int:
    return (
        data[0]
        | (data[1] << 8)
        | (data[2] << 16)
        | (data[3] << 24)
    ) & 0xFFFFFFFF


def load_tables(data: bytes) -> Tables:
    """Parse dec_key exactly like com.gaia.publisher.l.f.a."""
    t = Tables()
    pos = 0

    def take(n: int) -> bytes:
        nonlocal pos
        chunk = data[pos : pos + n]
        if len(chunk) != n:
            raise ValueError(f"dec_key too short at {pos}, need {n}, got {len(chunk)}")
        pos += n
        return chunk

    # f3532a: 2 * 15 * 32 entries of 128 bytes
    for i2 in range(2):
        for i3 in range(15):
            for i4 in range(32):
                t.key0[i2][i3][i4] = ints_from_bytes(take(128))

    # f3533b: 2 * 16 * 256 entries; each entry is one 16-byte blob used for
    # both int[16] and long[4] (same bytes reinterpreted).
    for i2 in range(2):
        for i3 in range(16):
            for i4 in range(256):
                b = B()
                blob = take(16)
                b.vals = ints_from_bytes(blob)
                b.longs = [long_from_bytes(blob[k * 4 : k * 4 + 4]) for k in range(4)]
                t.sbox[i2][i3][i4] = b

    # f3534c then f3535d: 9 * 16 * 256 entries; each is one 4-byte blob used
    # for both int[4] and long.
    for target in (t.c1, t.c2):
        for i2 in range(9):
            for i3 in range(16):
                for i4 in range(256):
                    c = C()
                    blob = take(4)
                    c.vals = ints_from_bytes(blob)
                    c.long = long_from_bytes(blob)
                    target[i2][i3][i4] = c

    # f3536e then f3537f: 9 * 12 * 8 entries of 128 bytes
    for target in (t.k1, t.k2):
        for i2 in range(9):
            for i3 in range(12):
                for i4 in range(8):
                    target[i2][i3][i4] = ints_from_bytes(take(128))

    if pos != len(data):
        raise ValueError(f"dec_key size mismatch: used {pos}, file has {len(data)}")
    return t


def nibble(key: list[int], index: int) -> int:
    value = key[index // 2]
    return value >> 4 if index % 2 == 0 else value


def copy_b(dst: B, src: B) -> None:
    dst.copy_from(src)


def mix_b(dst: B, a: B, b: B, key: list[int]) -> None:
    for i in range(16):
        ia = (a.vals[i] & 0xF0) ^ (b.vals[i] >> 4)
        ia2 = ((a.vals[i] << 4) ^ (b.vals[i] & 0x0F)) & 0xFF
        x = nibble(key[i * 2], ia)
        y = nibble(key[i * 2 + 1], ia2)
        dst.vals[i] = ((x << 4) ^ (y & 0x0F)) & 0xFF
    dst.longs = longs_from_ints(dst.vals)


def mix_c(dst: C, a: C, b: C, key: list[int]) -> None:
    for i in range(4):
        ia = (a.vals[i] & 0xF0) ^ (b.vals[i] >> 4)
        ia2 = ((a.vals[i] << 4) ^ (b.vals[i] & 0x0F)) & 0xFF
        x = nibble(key[i * 2], ia)
        y = nibble(key[i * 2 + 1], ia2)
        dst.vals[i] = ((x << 4) ^ (y & 0x0F)) & 0xFF
    dst.long = long_from_ints(dst.vals)


def b_to_c(state: B, cvar: list[C]) -> None:
    for i2 in range(4):
        i3 = i2 * 4
        jb = cvar[i3].long
        state.longs[i2] = jb
        arr = ints_from_long(jb)
        for k in range(4):
            state.vals[i3 + k] = arr[k]


def decrypt_block(data: bytes, t: Tables) -> list[int]:
    state = B()
    state.vals = list(data)
    state.longs = longs_from_ints(state.vals)

    arr = [B() for _ in range(16)]
    for i in range(16):
        arr[i].copy_from(t.sbox[0][i][state.vals[i]])

    # initial Feistel-style mixing (round 0)
    for i9 in range(8):
        i10 = i9 * 2
        mix_b(arr[i10], arr[i10], arr[i10 + 1], t.key0[0][i9])
    for i11 in range(4):
        i12 = i11 * 4
        mix_b(arr[i12], arr[i12], arr[i12 + 2], t.key0[0][i11 + 8])
    for i13 in range(2):
        i14 = i13 * 8
        mix_b(arr[i14], arr[i14], arr[i14 + 4], t.key0[0][i13 + 12])
    mix_b(arr[0], arr[0], arr[8], t.key0[0][14])
    copy_b(state, arr[0])

    cvar = [C() for _ in range(16)]
    for rnd in range(9):
        for i16 in range(0, 16, 4):
            for k in range(4):
                pos = i16 + k
                cv = t.c1[rnd][pos][state.vals[PERM_DEC[pos]]]
                cvar[pos].long = cv.long
                cvar[pos].vals = list(cv.vals)
            row = (i16 // 4) * 3
            mix_c(cvar[i16], cvar[i16], cvar[i16 + 1], t.k1[rnd][row])
            mix_c(cvar[i16 + 2], cvar[i16 + 2], cvar[i16 + 3], t.k1[rnd][row + 1])
            mix_c(cvar[i16], cvar[i16], cvar[i16 + 2], t.k1[rnd][row + 2])
        b_to_c(state, cvar)

        for i21 in range(0, 16, 4):
            for k in range(4):
                pos = i21 + k
                cv = t.c2[rnd][pos][state.vals[pos]]
                cvar[pos].long = cv.long
                cvar[pos].vals = list(cv.vals)
            row = (i21 // 4) * 3
            mix_c(cvar[i21], cvar[i21], cvar[i21 + 1], t.k2[rnd][row])
            mix_c(cvar[i21 + 2], cvar[i21 + 2], cvar[i21 + 3], t.k2[rnd][row + 1])
            mix_c(cvar[i21], cvar[i21], cvar[i21 + 2], t.k2[rnd][row + 2])
        b_to_c(state, cvar)

    arr5 = [B() for _ in range(16)]
    for i in range(16):
        arr5[i].copy_from(t.sbox[1][i][state.vals[PERM_DEC[i]]])
    for i27 in range(8):
        i28 = i27 * 2
        mix_b(arr5[i28], arr5[i28], arr5[i28 + 1], t.key0[1][i27])
    for i29 in range(4):
        i30 = i29 * 4
        mix_b(arr5[i30], arr5[i30], arr5[i30 + 2], t.key0[1][i29 + 8])
    for i31 in range(2):
        i32 = i31 * 8
        mix_b(arr5[i32], arr5[i32], arr5[i32 + 4], t.key0[1][i31 + 12])
    mix_b(arr5[0], arr5[0], arr5[8], t.key0[1][14])
    copy_b(state, arr5[0])
    return state.vals


def strip_pull_suffix(data: bytes) -> bytes:
    marker = b"unzip: invalid zip magic"
    idx = data.find(marker)
    return data if idx < 0 else data[:idx]


def decrypt_hex(text: str, t: Tables) -> str:
    raw = bytes.fromhex(text)
    if len(raw) % 16 != 0:
        raise ValueError(f"ciphertext length {len(raw)} is not a multiple of 16")
    out = bytearray()
    for off in range(0, len(raw), 16):
        vals = decrypt_block(raw[off : off + 16], t)
        out.extend(v ^ 16 for v in vals)
    s = out.decode("utf-8", errors="replace")
    null = s.find("\0")
    return s if null < 0 else s[:null]


def load_tables_default() -> Tables:
    data = strip_pull_suffix((ASSETS / "dec_key").read_bytes())
    return load_tables(data)


def decrypt_asset(name: str, t: Tables | None = None) -> str:
    if t is None:
        t = load_tables_default()
    data = strip_pull_suffix((ASSETS / name).read_bytes()).decode("ascii").strip()
    return decrypt_hex(data, t)


def main() -> None:
    t = load_tables_default()
    print("dec_key OK")
    for name in ("keyInfo", "clientKeyInfo"):
        try:
            print(f"--- {name} ---")
            print(decrypt_asset(name, t))
        except Exception as exc:  # noqa: BLE001
            print(f"{name}: ERROR {exc}")


if __name__ == "__main__":
    sys.exit(main())
