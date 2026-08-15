import argparse
import re
import struct
import sys
from pathlib import Path

from capstone import Cs, CS_ARCH_ARM64, CS_MODE_ARM

ROOT = Path(__file__).resolve().parent.parent
LIB = ROOT / "dumps" / "20260810" / "protocol" / "libil2cpp.so"
DUMP = ROOT / "tools" / "il2cpp" / "v6.7.46" / "dump.cs"


def parse_elf_program_headers(data: bytes):
    """Return list of (vaddr, filesz, offset, flags) for PT_LOAD segments."""
    if data[:4] != b"\x7fELF":
        raise ValueError("not an ELF file")
    is64 = data[4] == 2
    little = data[5] == 1
    endian = "<" if little else ">"
    if not is64:
        raise ValueError("only ELF64 supported")
    e_phoff = struct.unpack_from(endian + "Q", data, 0x20)[0]
    e_phentsize = struct.unpack_from(endian + "H", data, 0x36)[0]
    e_phnum = struct.unpack_from(endian + "H", data, 0x38)[0]
    segs = []
    for i in range(e_phnum):
        off = e_phoff + i * e_phentsize
        p_type, p_flags = struct.unpack_from(endian + "II", data, off)
        if p_type != 1:  # PT_LOAD
            continue
        p_offset, p_vaddr, p_paddr, p_filesz, p_memsz, p_align = struct.unpack_from(
            endian + "QQQQQQ", data, off + 0x08
        )
        segs.append((p_vaddr, p_offset, p_filesz, p_flags))
    return segs


def rva_to_offset(segs, rva: int) -> int:
    for vaddr, offset, filesz, _ in segs:
        if vaddr <= rva < vaddr + filesz:
            return offset + (rva - vaddr)
    raise ValueError(f"RVA 0x{rva:x} not in any PT_LOAD segment")


def find_methods(needle: str):
    """Parse dump.cs and return matching (class_name, method_name, rva, offset)."""
    current_class = None
    current_ns = None
    pending = None
    results = []
    with open(DUMP, encoding="utf-8", errors="replace") as f:
        for line in f:
            m = re.search(r"// Namespace: (\S+)", line)
            if m:
                current_ns = m.group(1)
                continue
            m = re.search(r"public (?:sealed |abstract )?(?:class|struct) (\S+)", line)
            if m:
                current_class = m.group(1)
                continue
            m = re.match(r"\s*// RVA: (0x[0-9A-Fa-f]+) Offset: (0x[0-9A-Fa-f]+) VA: (0x[0-9A-Fa-f]+)", line)
            if m:
                pending = (int(m.group(1), 16), int(m.group(2), 16))
                continue
            m = re.match(r"\s*(?:public |private |internal |protected )?(?:static |virtual |override |new )*[\w<>,\.\s\*\[\]]+\s+(\w+)\s*\(", line)
            if m and pending:
                method_name = m.group(1)
                full = f"{current_ns}.{current_class}.{method_name}" if current_ns else f"{current_class}.{method_name}"
                if needle.lower() in full.lower() or needle.lower() in method_name.lower():
                    rva, offset = pending
                    results.append((full, method_name, rva, offset))
                pending = None
    return results


def disasm(data: bytes, offset: int, count: int, show_bytes=True, base_addr=None):
    md = Cs(CS_ARCH_ARM64, CS_MODE_ARM)
    md.detail = True
    code = data[offset : offset + count * 16]
    lines = []
    for ins in md.disasm(code, base_addr if base_addr is not None else offset):
        if len(lines) >= count:
            break
        b = " ".join(f"{x:02x}" for x in ins.bytes)
        if show_bytes:
            lines.append(f"0x{ins.address:08x}: {b:<40} {ins.mnemonic:<8} {ins.op_str}")
        else:
            lines.append(f"0x{ins.address:08x}: {ins.mnemonic:<8} {ins.op_str}")
    return lines


def main():
    ap = argparse.ArgumentParser(description="Disassemble ARM64 methods from the dumped IL2CPP lib.")
    ap.add_argument("--name", help="substring of class.method to search in dump.cs")
    ap.add_argument("--address", help="RVA address, e.g. 0x1C48E68")
    ap.add_argument("--count", type=int, default=120)
    ap.add_argument("--raw", action="store_true", help="do not resolve imports, raw disassembly")
    args = ap.parse_args()

    data = LIB.read_bytes()
    segs = parse_elf_program_headers(data)

    targets = []
    if args.address:
        rva = int(args.address, 16)
        targets.append((f"RVA 0x{rva:x}", rva, rva_to_offset(segs, rva)))
    if args.name:
        for full, method, rva, offset in find_methods(args.name):
            targets.append((full, rva, offset))
    if not targets:
        print("no targets; use --name or --address", file=sys.stderr)
        sys.exit(1)

    for label, rva, offset in targets:
        print(f"\n===== {label}  RVA=0x{rva:x}  offset=0x{offset:x} =====")
        for line in disasm(data, offset, args.count, base_addr=rva):
            print(line)


if __name__ == "__main__":
    main()
