#include "seeds.h"
#include "tailor/bytecode.h"

#define TAILOR_FNV_OFFSET 14695981039346656037ull
#define TAILOR_FNV_PRIME 1099511628211ull

#if defined(__clang__) || defined(__GNUC__)
#define TAILOR_INLINE static inline __attribute__((always_inline))
#else
#define TAILOR_INLINE static inline
#endif

TAILOR_INLINE tailor_u64 hash_bytes(const char *s, tailor_u32 n) {
    tailor_u64 h = TAILOR_FNV_OFFSET;
    for (tailor_u32 i = 0; i < n; i++) {
        h ^= (tailor_u8)s[i];
        h *= TAILOR_FNV_PRIME;
    }
    return h;
}

TAILOR_INLINE tailor_u32 cstr_len(const char *s) {
    tailor_u32 n = 0;
    while (s && s[n]) {
        n++;
    }
    return n;
}

TAILOR_INLINE const char *basename_ptr(const char *s, tailor_u32 n, tailor_u32 *out_n) {
    tailor_u32 start = 0;
    for (tailor_u32 i = 0; i < n; i++) {
        if (s[i] == '/' || s[i] == '\\') {
            start = i + 1;
        }
    }
    *out_n = n - start;
    return s + start;
}

TAILOR_INLINE tailor_u64 hash_module_name(const struct tailor_image_view *image) {
    const char *path = (const char *)(tailor_u64)image->path_ptr;
    tailor_u32 path_len = image->path_len;
    if (!path) {
        return hash_bytes("<unknown>", 9);
    }
    if (path_len == 0) {
        path_len = cstr_len(path);
    }
    tailor_u32 base_len = 0;
    const char *base = basename_ptr(path, path_len, &base_len);
    return hash_bytes(base, base_len);
}

TAILOR_INLINE tailor_u64 hash_symbol_name(const char *name, tailor_u32 trim_macho_underscore) {
    tailor_u32 n = cstr_len(name);
    if (trim_macho_underscore && n > 1 && name[0] == '_') {
        return hash_bytes(name + 1, n - 1);
    }
    return hash_bytes(name, n);
}

struct emit_ctx {
    struct tailor_manifest_entry *entries;
    tailor_u32 capacity;
    tailor_u32 count;
    tailor_u32 overflow;
};

struct code_range {
    tailor_u64 start;
    tailor_u64 end;
};

TAILOR_INLINE void emit_entry(struct emit_ctx *ctx,
                              tailor_u32 module_index,
                              tailor_u64 module_hash,
                              tailor_u64 function_hash,
                              tailor_u64 module_base,
                              tailor_u64 address,
                              tailor_u32 flags) {
    if (address < module_base) {
        return;
    }
    if (ctx->count >= ctx->capacity) {
        ctx->overflow = 1;
        return;
    }
    struct tailor_manifest_entry *entry = &ctx->entries[ctx->count++];
    entry->module_hash = module_hash;
    entry->function_hash = function_hash;
    entry->offset = address - module_base;
    entry->address = address;
    entry->module_index = module_index;
    entry->flags = flags;
}

TAILOR_INLINE int is_code_address(const struct code_range *ranges, tailor_u32 range_count, tailor_u64 address) {
    for (tailor_u32 i = 0; i < range_count; i++) {
        if (address >= ranges[i].start && address < ranges[i].end) {
            return 1;
        }
    }
    return 0;
}

TAILOR_INLINE tailor_u16 rd16(const void *p) {
    const tailor_u8 *b = (const tailor_u8 *)p;
    return (tailor_u16)(b[0] | ((tailor_u16)b[1] << 8));
}

TAILOR_INLINE tailor_u32 rd32(const void *p) {
    const tailor_u8 *b = (const tailor_u8 *)p;
    return (tailor_u32)b[0] |
           ((tailor_u32)b[1] << 8) |
           ((tailor_u32)b[2] << 16) |
           ((tailor_u32)b[3] << 24);
}

TAILOR_INLINE tailor_u64 rd64(const void *p) {
    const tailor_u8 *b = (const tailor_u8 *)p;
    return (tailor_u64)rd32(b) | ((tailor_u64)rd32(b + 4) << 32);
}

TAILOR_INLINE tailor_u64 read_uleb(const tailor_u8 **cursor, const tailor_u8 *end) {
    tailor_u64 value = 0;
    unsigned shift = 0;
    while (*cursor < end) {
        tailor_u8 byte = **cursor;
        (*cursor)++;
        value |= ((tailor_u64)(byte & 0x7f)) << shift;
        if ((byte & 0x80) == 0) {
            break;
        }
        shift += 7;
        if (shift >= 64) {
            break;
        }
    }
    return value;
}

/* ──────────────────────────────────────────────────────────────────
 * PE export parser
 * ────────────────────────────────────────────────────────────────── */

TAILOR_INLINE void profile_pe(struct emit_ctx *ctx,
                              tailor_u32 module_index,
                              const struct tailor_image_view *image,
                              tailor_u64 module_hash) {
    const tailor_u8 *base = (const tailor_u8 *)(tailor_u64)image->image_base;
    if (!base || rd16(base) != 0x5a4d) {
        return;
    }
    tailor_u32 pe_off = rd32(base + 0x3c);
    const tailor_u8 *nt = base + pe_off;
    if (rd32(nt) != 0x00004550) {
        return;
    }
    tailor_u16 opt_size = rd16(nt + 20);
    const tailor_u8 *opt = nt + 24;
    tailor_u16 magic = rd16(opt);
    tailor_u32 data_dir = (magic == 0x20b) ? 112u : 96u;
    if (opt_size < data_dir + 8) {
        return;
    }
    tailor_u32 export_rva = rd32(opt + data_dir);
    tailor_u32 export_size = rd32(opt + data_dir + 4);
    if (!export_rva || export_size < 40) {
        return;
    }
    const tailor_u8 *exp = base + export_rva;
    tailor_u32 number_of_names = rd32(exp + 24);
    tailor_u32 functions_rva = rd32(exp + 28);
    tailor_u32 names_rva = rd32(exp + 32);
    tailor_u32 ordinals_rva = rd32(exp + 36);
    const tailor_u8 *functions = base + functions_rva;
    const tailor_u8 *names = base + names_rva;
    const tailor_u8 *ordinals = base + ordinals_rva;

    for (tailor_u32 i = 0; i < number_of_names; i++) {
        tailor_u32 name_rva = rd32(names + i * 4);
        tailor_u16 ordinal = rd16(ordinals + i * 2);
        tailor_u32 function_rva = rd32(functions + (tailor_u32)ordinal * 4);
        if (!name_rva || !function_rva) {
            continue;
        }
        if (function_rva >= export_rva && function_rva < export_rva + export_size) {
            continue;
        }
        const char *name = (const char *)(base + name_rva);
        emit_entry(ctx,
                   module_index,
                   module_hash,
                   hash_symbol_name(name, 0),
                   image->image_base,
                   image->image_base + function_rva,
                   TAILOR_ENTRY_FLAG_EXPORT);
    }
}

/* ──────────────────────────────────────────────────────────────────
 * ELF dynamic symbol parser
 * ────────────────────────────────────────────────────────────────── */

TAILOR_INLINE tailor_u64 elf_dyn_addr(tailor_u64 base, tailor_u64 ptr) {
    if (base != 0 && ptr >= base) {
        return ptr;
    }
    return base + ptr;
}

TAILOR_INLINE tailor_u32 elf_gnu_hash_count32(const tailor_u8 *hash) {
    tailor_u32 nbuckets = rd32(hash);
    tailor_u32 symoffset = rd32(hash + 4);
    tailor_u32 bloom_size = rd32(hash + 8);
    const tailor_u8 *p = hash + 16 + bloom_size * 4;
    const tailor_u8 *buckets = p;
    const tailor_u8 *chains = p + nbuckets * 4;
    tailor_u32 max_idx = symoffset;
    for (tailor_u32 i = 0; i < nbuckets; i++) {
        tailor_u32 idx = rd32(buckets + i * 4);
        if (!idx) {
            continue;
        }
        while (1) {
            tailor_u32 chain = rd32(chains + (idx - symoffset) * 4);
            if (idx > max_idx) {
                max_idx = idx;
            }
            if (chain & 1u) {
                break;
            }
            idx++;
        }
    }
    return max_idx + 1;
}

TAILOR_INLINE tailor_u32 elf_gnu_hash_count64(const tailor_u8 *hash) {
    tailor_u32 nbuckets = rd32(hash);
    tailor_u32 symoffset = rd32(hash + 4);
    tailor_u32 bloom_size = rd32(hash + 8);
    const tailor_u8 *p = hash + 16 + bloom_size * 8;
    const tailor_u8 *buckets = p;
    const tailor_u8 *chains = p + nbuckets * 4;
    tailor_u32 max_idx = symoffset;
    for (tailor_u32 i = 0; i < nbuckets; i++) {
        tailor_u32 idx = rd32(buckets + i * 4);
        if (!idx) {
            continue;
        }
        while (1) {
            tailor_u32 chain = rd32(chains + (idx - symoffset) * 4);
            if (idx > max_idx) {
                max_idx = idx;
            }
            if (chain & 1u) {
                break;
            }
            idx++;
        }
    }
    return max_idx + 1;
}

TAILOR_INLINE void profile_elf64(struct emit_ctx *ctx,
                                 tailor_u32 module_index,
                                 const struct tailor_image_view *image,
                                 tailor_u64 module_hash) {
    const tailor_u8 *base = (const tailor_u8 *)(tailor_u64)image->image_base;
    tailor_u16 phnum = rd16(base + 56);
    tailor_u64 phoff = rd64(base + 32);
    tailor_u16 phentsize = rd16(base + 54);
    tailor_u64 dynamic = 0;
    for (tailor_u16 i = 0; i < phnum; i++) {
        const tailor_u8 *ph = base + phoff + (tailor_u64)i * phentsize;
        if (rd32(ph) == 2) {
            dynamic = image->image_base + rd64(ph + 16);
            break;
        }
    }
    if (!dynamic) {
        return;
    }
    tailor_u64 symtab = 0, strtab = 0, sysv_hash = 0, gnu_hash = 0;
    for (const tailor_u8 *dyn = (const tailor_u8 *)(tailor_u64)dynamic;; dyn += 16) {
        tailor_u64 tag = rd64(dyn);
        tailor_u64 val = rd64(dyn + 8);
        if (tag == 0) {
            break;
        } else if (tag == 5) {
            strtab = elf_dyn_addr(image->image_base, val);
        } else if (tag == 6) {
            symtab = elf_dyn_addr(image->image_base, val);
        } else if (tag == 4) {
            sysv_hash = elf_dyn_addr(image->image_base, val);
        } else if (tag == 0x6ffffef5ull) {
            gnu_hash = elf_dyn_addr(image->image_base, val);
        }
    }
    if (!symtab || !strtab) {
        return;
    }
    tailor_u32 nsyms = 0;
    if (sysv_hash) {
        nsyms = rd32((const void *)(tailor_u64)(sysv_hash + 4));
    } else if (gnu_hash) {
        nsyms = elf_gnu_hash_count64((const tailor_u8 *)(tailor_u64)gnu_hash);
    }
    for (tailor_u32 i = 0; i < nsyms; i++) {
        const tailor_u8 *sym = (const tailor_u8 *)(tailor_u64)(symtab + (tailor_u64)i * 24);
        tailor_u32 name_off = rd32(sym);
        tailor_u8 info = sym[4];
        tailor_u16 shndx = rd16(sym + 6);
        tailor_u64 value = rd64(sym + 8);
        tailor_u32 type = info & 0xfu;
        tailor_u32 bind = info >> 4;
        if (!name_off || !value || shndx == 0 || (type != 2 && type != 10) || (bind != 1 && bind != 2)) {
            continue;
        }
        const char *name = (const char *)(tailor_u64)(strtab + name_off);
        emit_entry(ctx,
                   module_index,
                   module_hash,
                   hash_symbol_name(name, 0),
                   image->image_base,
                   image->image_base + value,
                   TAILOR_ENTRY_FLAG_EXPORT);
    }
}

TAILOR_INLINE void profile_elf32(struct emit_ctx *ctx,
                                 tailor_u32 module_index,
                                 const struct tailor_image_view *image,
                                 tailor_u64 module_hash) {
    const tailor_u8 *base = (const tailor_u8 *)(tailor_u64)image->image_base;
    tailor_u16 phnum = rd16(base + 44);
    tailor_u32 phoff = rd32(base + 28);
    tailor_u16 phentsize = rd16(base + 42);
    tailor_u64 dynamic = 0;
    for (tailor_u16 i = 0; i < phnum; i++) {
        const tailor_u8 *ph = base + phoff + (tailor_u32)i * phentsize;
        if (rd32(ph) == 2) {
            dynamic = image->image_base + rd32(ph + 8);
            break;
        }
    }
    if (!dynamic) {
        return;
    }
    tailor_u64 symtab = 0, strtab = 0, sysv_hash = 0, gnu_hash = 0;
    for (const tailor_u8 *dyn = (const tailor_u8 *)(tailor_u64)dynamic;; dyn += 8) {
        tailor_u32 tag = rd32(dyn);
        tailor_u32 val = rd32(dyn + 4);
        if (tag == 0) {
            break;
        } else if (tag == 5) {
            strtab = elf_dyn_addr(image->image_base, val);
        } else if (tag == 6) {
            symtab = elf_dyn_addr(image->image_base, val);
        } else if (tag == 4) {
            sysv_hash = elf_dyn_addr(image->image_base, val);
        } else if (tag == 0x6ffffef5u) {
            gnu_hash = elf_dyn_addr(image->image_base, val);
        }
    }
    if (!symtab || !strtab) {
        return;
    }
    tailor_u32 nsyms = 0;
    if (sysv_hash) {
        nsyms = rd32((const void *)(tailor_u64)(sysv_hash + 4));
    } else if (gnu_hash) {
        nsyms = elf_gnu_hash_count32((const tailor_u8 *)(tailor_u64)gnu_hash);
    }
    for (tailor_u32 i = 0; i < nsyms; i++) {
        const tailor_u8 *sym = (const tailor_u8 *)(tailor_u64)(symtab + (tailor_u32)i * 16);
        tailor_u32 name_off = rd32(sym);
        tailor_u32 value = rd32(sym + 4);
        tailor_u8 info = sym[12];
        tailor_u16 shndx = rd16(sym + 14);
        tailor_u32 type = info & 0xfu;
        tailor_u32 bind = info >> 4;
        if (!name_off || !value || shndx == 0 || (type != 2 && type != 10) || (bind != 1 && bind != 2)) {
            continue;
        }
        const char *name = (const char *)(tailor_u64)(strtab + name_off);
        emit_entry(ctx,
                   module_index,
                   module_hash,
                   hash_symbol_name(name, 0),
                   image->image_base,
                   image->image_base + value,
                   TAILOR_ENTRY_FLAG_EXPORT);
    }
}

TAILOR_INLINE void profile_elf(struct emit_ctx *ctx,
                               tailor_u32 module_index,
                               const struct tailor_image_view *image,
                               tailor_u64 module_hash) {
    const tailor_u8 *base = (const tailor_u8 *)(tailor_u64)image->image_base;
    if (!base || base[0] != 0x7f || base[1] != 'E' || base[2] != 'L' || base[3] != 'F') {
        return;
    }
    if (base[4] == 2) {
        profile_elf64(ctx, module_index, image, module_hash);
    } else if (base[4] == 1) {
        profile_elf32(ctx, module_index, image, module_hash);
    }
}

/* ──────────────────────────────────────────────────────────────────
 * Mach-O export trie parser
 * ────────────────────────────────────────────────────────────────── */

TAILOR_INLINE int macho_read_uleb_checked(const tailor_u8 **cursor,
                                          const tailor_u8 *end,
                                          tailor_u64 *out) {
    if (*cursor >= end) {
        return 0;
    }
    *out = read_uleb(cursor, end);
    return *cursor <= end;
}

TAILOR_INLINE void macho_walk_exports(struct emit_ctx *ctx,
                                      tailor_u32 module_index,
                                      tailor_u64 module_hash,
                                      tailor_u64 module_base,
                                      const tailor_u8 *trie,
                                      const tailor_u8 *end,
                                      char *name_buf,
                                      tailor_u32 name_cap,
                                      const struct code_range *ranges,
                                      tailor_u32 range_count) {
    struct macho_export_frame {
        const tailor_u8 *node;
        const tailor_u8 *cursor;
        tailor_u32 name_len;
        tailor_u16 child_index;
        tailor_u16 child_count;
        tailor_u8 ready;
    };
    struct macho_export_frame stack[256];
    tailor_u32 depth = 1;

    if (trie >= end || name_cap == 0) {
        return;
    }
    stack[0].node = trie;
    stack[0].cursor = 0;
    stack[0].name_len = 0;
    stack[0].child_index = 0;
    stack[0].child_count = 0;
    stack[0].ready = 0;

    while (depth > 0) {
        struct macho_export_frame *frame = &stack[depth - 1];
        if (!frame->ready) {
            if (frame->node >= end || frame->name_len >= name_cap) {
                depth--;
                continue;
            }

            const tailor_u8 *p = frame->node;
            tailor_u64 terminal_size = 0;
            if (!macho_read_uleb_checked(&p, end, &terminal_size)) {
                depth--;
                continue;
            }
            const tailor_u8 *children = p + terminal_size;
            if (terminal_size > 0 && children <= end) {
                tailor_u64 flags = 0, address = 0;
                const tailor_u8 *term = p;
                if (macho_read_uleb_checked(&term, children, &flags) &&
                    (flags & 0x08u) == 0 &&
                    macho_read_uleb_checked(&term, children, &address)) {
                    tailor_u64 absolute = module_base + address;
                    if (is_code_address(ranges, range_count, absolute)) {
                        name_buf[frame->name_len] = '\0';
                        emit_entry(ctx,
                                   module_index,
                                   module_hash,
                                   hash_symbol_name(name_buf, 1),
                                   module_base,
                                   absolute,
                                   TAILOR_ENTRY_FLAG_EXPORT);
                    }
                }
            }
            if (children >= end) {
                depth--;
                continue;
            }
            frame->cursor = children + 1;
            frame->child_count = *children;
            frame->child_index = 0;
            frame->ready = 1;
        }

        if (frame->child_index >= frame->child_count) {
            depth--;
            continue;
        }
        frame->child_index++;

        const tailor_u8 *cursor = frame->cursor;
        tailor_u32 edge_len = 0;
        tailor_u32 edge_fits = 1;
        while (cursor < end && *cursor) {
            if (frame->name_len + edge_len + 1 < name_cap) {
                name_buf[frame->name_len + edge_len] = (char)*cursor;
            } else {
                edge_fits = 0;
            }
            cursor++;
            edge_len++;
        }
        if (cursor >= end) {
            depth--;
            continue;
        }
        cursor++;
        tailor_u64 child_off = read_uleb(&cursor, end);
        frame->cursor = cursor;

        if (!edge_fits ||
            child_off >= (tailor_u64)(end - trie) ||
            depth >= (tailor_u32)(sizeof(stack) / sizeof(stack[0]))) {
            continue;
        }

        stack[depth].node = trie + child_off;
        stack[depth].cursor = 0;
        stack[depth].name_len = frame->name_len + edge_len;
        stack[depth].child_index = 0;
        stack[depth].child_count = 0;
        stack[depth].ready = 0;
        depth++;
    }
}

TAILOR_INLINE void profile_macho(struct emit_ctx *ctx,
                                 tailor_u32 module_index,
                                 const struct tailor_image_view *image,
                                 tailor_u64 module_hash) {
    const tailor_u8 *base = (const tailor_u8 *)(tailor_u64)image->image_base;
    if (!base || rd32(base) != 0xfeedfacf) {
        return;
    }
    tailor_u32 ncmds = rd32(base + 16);
    const tailor_u8 *cmd = base + 32;
    tailor_u64 linkedit_vmaddr = 0, linkedit_fileoff = 0, text_vmaddr = 0;
    tailor_u32 export_off = 0, export_size = 0;
    struct code_range ranges[128];
    tailor_u32 range_count = 0;
    for (tailor_u32 i = 0; i < ncmds; i++) {
        tailor_u32 cmd_type = rd32(cmd);
        tailor_u32 cmd_size = rd32(cmd + 4);
        if (cmd_type == 0x19) {
            const char *segname = (const char *)(cmd + 8);
            if (segname[0] == '_' && segname[1] == '_' &&
                segname[2] == 'T' && segname[3] == 'E' &&
                segname[4] == 'X' && segname[5] == 'T') {
                text_vmaddr = rd64(cmd + 24);
            }
            if (segname[0] == '_' && segname[1] == '_' &&
                segname[2] == 'L' && segname[3] == 'I' &&
                segname[4] == 'N' && segname[5] == 'K') {
                linkedit_vmaddr = rd64(cmd + 24);
                linkedit_fileoff = rd64(cmd + 40);
            }
            tailor_u32 nsects = rd32(cmd + 64);
            const tailor_u8 *sec = cmd + 72;
            for (tailor_u32 j = 0; j < nsects && range_count < 128; j++) {
                tailor_u64 sec_addr = rd64(sec + 32);
                tailor_u64 sec_size = rd64(sec + 40);
                tailor_u32 sec_flags = rd32(sec + 64);
                const char *sectname = (const char *)sec;
                if ((sec_flags & 0x80000000u) ||
                    (sec_flags & 0x00000400u) ||
                    (sectname[0] == '_' && sectname[1] == '_' &&
                     sectname[2] == 't' && sectname[3] == 'e' &&
                     sectname[4] == 'x' && sectname[5] == 't')) {
                    ranges[range_count].start = sec_addr;
                    ranges[range_count].end = sec_addr + sec_size;
                    range_count++;
                }
                sec += 80;
            }
        } else if (cmd_type == 0x22 || cmd_type == 0x80000022u) {
            export_off = rd32(cmd + 40);
            export_size = rd32(cmd + 44);
        } else if (cmd_type == 0x80000033u) {
            export_off = rd32(cmd + 8);
            export_size = rd32(cmd + 12);
        }
        if (cmd_size == 0) {
            return;
        }
        cmd += cmd_size;
    }
    if (!linkedit_vmaddr || !export_off || !export_size) {
        return;
    }
    tailor_u64 slide = text_vmaddr ? (image->image_base - text_vmaddr) : image->image_base;
    for (tailor_u32 i = 0; i < range_count; i++) {
        ranges[i].start += slide;
        ranges[i].end += slide;
    }
    const tailor_u8 *trie = (const tailor_u8 *)(tailor_u64)(slide + linkedit_vmaddr - linkedit_fileoff + export_off);
    char name_buf[512];
    macho_walk_exports(ctx,
                       module_index,
                       module_hash,
                       image->image_base,
                       trie,
                       trie + export_size,
                       name_buf,
                       (tailor_u32)sizeof(name_buf),
                       ranges,
                       range_count);
}

TAILOR_INLINE tailor_u32 detect_format(const struct tailor_image_view *image) {
    const tailor_u8 *base = (const tailor_u8 *)(tailor_u64)image->image_base;
    if (!base) {
        return TAILOR_IMAGE_FORMAT_AUTO;
    }
    if (base[0] == 0x7f && base[1] == 'E' && base[2] == 'L' && base[3] == 'F') {
        return TAILOR_IMAGE_FORMAT_ELF;
    }
    if (rd32(base) == 0xfeedfacf) {
        return TAILOR_IMAGE_FORMAT_MACHO;
    }
    if (rd16(base) == 0x5a4d) {
        return TAILOR_IMAGE_FORMAT_PE;
    }
    return TAILOR_IMAGE_FORMAT_AUTO;
}

__attribute__((annotate("shellvm-main")))
int entry(struct seeds *s, void *args, size_t args_len) {
    (void)s;
    if (!args || args_len < sizeof(struct tailor_bytecode_args)) {
        return -1;
    }
    struct tailor_bytecode_args *a = (struct tailor_bytecode_args *)args;
    if (a->version != TAILOR_BYTECODE_ABI_VERSION ||
        !a->images_ptr ||
        !a->entries_ptr ||
        !a->entry_count_ptr) {
        return -2;
    }

    const struct tailor_image_view *images =
        (const struct tailor_image_view *)(tailor_u64)a->images_ptr;
    struct emit_ctx ctx;
    ctx.entries = (struct tailor_manifest_entry *)(tailor_u64)a->entries_ptr;
    ctx.capacity = a->entry_capacity;
    ctx.count = 0;
    ctx.overflow = 0;

    for (tailor_u32 i = 0; i < a->image_count; i++) {
        const struct tailor_image_view *image = &images[i];
        tailor_u64 module_hash = hash_module_name(image);
#if defined(TAILOR_BYTECODE_ONLY_PE)
        profile_pe(&ctx, i, image, module_hash);
#elif defined(TAILOR_BYTECODE_ONLY_ELF)
        profile_elf(&ctx, i, image, module_hash);
#elif defined(TAILOR_BYTECODE_ONLY_MACHO)
        profile_macho(&ctx, i, image, module_hash);
#else
        tailor_u32 format = image->format ? image->format : detect_format(image);
        if (format == TAILOR_IMAGE_FORMAT_PE) {
            profile_pe(&ctx, i, image, module_hash);
        } else if (format == TAILOR_IMAGE_FORMAT_ELF) {
            profile_elf(&ctx, i, image, module_hash);
        } else if (format == TAILOR_IMAGE_FORMAT_MACHO) {
            profile_macho(&ctx, i, image, module_hash);
        }
#endif
    }

    *(tailor_u32 *)(tailor_u64)a->entry_count_ptr = ctx.count;
    return ctx.overflow ? 1 : 0;
}
