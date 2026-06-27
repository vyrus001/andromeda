#!/usr/bin/env python3
"""Extract loadable bytes from a linked Mach-O as a flat blob.

`llvm-objcopy -O binary` on Mach-O input doesn't produce raw bytes (it
writes a stripped Mach-O), and there's no `--dump-segment` option. So
we parse load commands ourselves.

Strategy: walk the named segment's section table, collect "loadable"
sections (code + read-only data — NOT __unwind_info, debug info, etc.),
and extract the file byte range spanning them. This preserves the
linker's intra-segment layout so PC-relative offsets between sections
(e.g. __text -> __literal16 on x86_64) still resolve correctly, while
excluding the Mach-O header (which sits before __text in the file) and
trailing metadata sections (which would just bloat the blob).

Usage: extract-macho-segment.py <macho-file> <segname> <output-file>
"""
import struct
import sys

MH_MAGIC_64 = 0xFEEDFACF
LC_SEGMENT_64 = 0x19

# Sections we keep: code + read-only data the blob's instructions
# actually reference at runtime. NOT __unwind_info (exception/unwind
# metadata), __eh_frame (DWARF unwind), __debug_* (debug info), or
# __stubs / __stub_helper (lazy-binding, doesn't apply to our static blobs).
LOADABLE_SECTIONS = {
    b"__text",
    b"__text_cold",
    b"__const",
    b"__cstring",
    # Pre-link literal-pool names emitted by llc:
    b"__literal4",
    b"__literal8",
    b"__literal16",
    # Post-link merged literal section that ld64.lld emits (catches the
    # x86_64 vector-constant case):
    b"__literals",
    b"__ustring",
}


def main():
    if len(sys.argv) != 4:
        sys.exit(f"usage: {sys.argv[0]} <macho-file> <segname> <output-file>")

    macho_path, seg_name, out_path = sys.argv[1], sys.argv[2], sys.argv[3]
    target = seg_name.encode("ascii")

    with open(macho_path, "rb") as f:
        data = f.read()

    if len(data) < 32:
        sys.exit(f"{macho_path}: too short to be a Mach-O")
    magic = struct.unpack_from("<I", data, 0)[0]
    if magic != MH_MAGIC_64:
        sys.exit(
            f"{macho_path}: expected 64-bit LE Mach-O (magic 0x{MH_MAGIC_64:08x}), "
            f"got 0x{magic:08x}"
        )

    # mach_header_64: magic(4) cputype(4) cpusubtype(4) filetype(4)
    #                 ncmds(4) sizeofcmds(4) flags(4) reserved(4)  = 32 bytes
    ncmds = struct.unpack_from("<I", data, 16)[0]

    lc_off = 32
    for _ in range(ncmds):
        cmd, cmdsize = struct.unpack_from("<II", data, lc_off)
        if cmd == LC_SEGMENT_64 and data[lc_off + 8 : lc_off + 24].rstrip(b"\x00") == target:
            # segment_command_64:
            #   cmd(4) cmdsize(4) segname(16) vmaddr(8) vmsize(8) fileoff(8)
            #   filesize(8) maxprot(4) initprot(4) nsects(4) flags(4)
            # sections (section_64, 80 bytes each) follow at +72.
            nsects = struct.unpack_from("<I", data, lc_off + 64)[0]
            sec_off = lc_off + 72

            ranges = []
            for _ in range(nsects):
                # section_64:
                #   sectname[16] segname[16] addr(8) size(8) offset(4) align(4)
                #   reloff(4) nreloc(4) flags(4) reserved1..3(4*3)
                sectname = data[sec_off : sec_off + 16].rstrip(b"\x00")
                size = struct.unpack_from("<Q", data, sec_off + 40)[0]
                fileoff = struct.unpack_from("<I", data, sec_off + 48)[0]
                if sectname in LOADABLE_SECTIONS and size > 0:
                    ranges.append((fileoff, size, sectname.decode()))
                sec_off += 80

            if not ranges:
                sys.exit(f"{macho_path}: no loadable sections in {seg_name}")

            ranges.sort()
            start = ranges[0][0]
            end = max(fo + sz for fo, sz, _ in ranges)

            with open(out_path, "wb") as out:
                out.write(data[start:end])

            sections_desc = ", ".join(f"{n}({sz})" for _, sz, n in ranges)
            print(
                f"wrote {out_path} ({end - start} bytes from {seg_name}; "
                f"sections: {sections_desc})",
                file=sys.stderr,
            )
            return
        lc_off += cmdsize

    sys.exit(f"{macho_path}: no {seg_name} segment found")


if __name__ == "__main__":
    main()
