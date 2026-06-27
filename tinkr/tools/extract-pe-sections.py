#!/usr/bin/env python3
"""Extract loadable bytes from a PE (.exe/.dll) as a flat blob.

PE has two layout conventions that differ from each other: the on-disk
layout (file alignment, default 512 bytes) and the in-memory layout
(section alignment, default 4096 bytes). PC-relative instructions in
.text reference the in-memory layout, so we extract section contents
from disk but lay them out in the blob according to their RVA so the
gaps between sections (zero fill) match what the OS loader would
produce.

We extract .text + read-only data sections (.rdata / .rodata). We
skip .pdata, .xdata, .reloc, .idata, debug sections, etc. — none
of those matter for a SheLLVM-flattened PIC blob that doesn't unwind
through SEH or rely on PE imports.

Usage: extract-pe-sections.py <pe-file> <output-file>
"""
import struct
import sys

LOADABLE_SECTIONS = {
    b".text",
    b".rdata",
    b".rodata",
    b".data.rel.ro",
}


def main():
    if len(sys.argv) != 3:
        sys.exit(f"usage: {sys.argv[0]} <pe-file> <output-file>")

    path, out_path = sys.argv[1], sys.argv[2]
    with open(path, "rb") as f:
        data = f.read()

    if data[:2] != b"MZ":
        sys.exit(f"{path}: missing MZ — not a PE")
    pe_off = struct.unpack_from("<I", data, 60)[0]
    if data[pe_off : pe_off + 4] != b"PE\x00\x00":
        sys.exit(f"{path}: missing PE signature at offset 0x{pe_off:x}")

    # COFF file header (20 bytes) follows the 4-byte PE signature.
    coff_off = pe_off + 4
    nsections = struct.unpack_from("<H", data, coff_off + 2)[0]
    opt_hdr_size = struct.unpack_from("<H", data, coff_off + 16)[0]

    # Section table follows the optional header.
    sec_table = coff_off + 20 + opt_hdr_size

    # Section header layout (40 bytes):
    #   Name[8] VirtualSize(4) VirtualAddress(4) SizeOfRawData(4)
    #   PointerToRawData(4) PointerToRelocations(4) PointerToLinenumbers(4)
    #   NumberOfRelocations(2) NumberOfLinenumbers(2) Characteristics(4)
    sections = []
    for i in range(nsections):
        off = sec_table + i * 40
        name = data[off : off + 8].rstrip(b"\x00")
        virt_addr = struct.unpack_from("<I", data, off + 12)[0]
        raw_size = struct.unpack_from("<I", data, off + 16)[0]
        raw_ptr = struct.unpack_from("<I", data, off + 20)[0]
        if name in LOADABLE_SECTIONS and raw_size > 0:
            sections.append((virt_addr, raw_ptr, raw_size, name.decode()))

    if not sections:
        sys.exit(f"{path}: no loadable sections found")

    sections.sort()
    base_rva = sections[0][0]
    blob_size = max(va + sz for va, _, sz, _ in sections) - base_rva

    blob = bytearray(blob_size)
    for va, raw_ptr, raw_size, _ in sections:
        offset = va - base_rva
        blob[offset : offset + raw_size] = data[raw_ptr : raw_ptr + raw_size]

    with open(out_path, "wb") as f:
        f.write(blob)

    sec_desc = ", ".join(f"{n}@RVA{va:#x}({sz}B)" for va, _, sz, n in sections)
    print(
        f"wrote {out_path} ({blob_size} bytes; sections: {sec_desc})",
        file=sys.stderr,
    )


if __name__ == "__main__":
    main()
