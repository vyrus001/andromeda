#include "tailor/profile.h"

#if defined(__APPLE__) && defined(__MACH__)

#include <mach-o/dyld.h>
#include <mach-o/loader.h>
#include <mach-o/nlist.h>

#include <stdint.h>
#include <stdlib.h>
#include <string.h>

typedef struct section_info {
    char segname[17];
    char sectname[17];
    uint32_t flags;
} section_info;

typedef struct code_range {
    uintptr_t start;
    uintptr_t end;
} code_range;

static uint64_t read_uleb128(const uint8_t **cursor, const uint8_t *end) {
    uint64_t value = 0;
    unsigned shift = 0;
    while (*cursor < end) {
        uint8_t byte = **cursor;
        (*cursor)++;
        value |= ((uint64_t)(byte & 0x7f)) << shift;
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

static const char *basename_of(const char *path) {
    if (!path || !*path) {
        return "<unknown>";
    }
    const char *slash = strrchr(path, '/');
    return slash ? slash + 1 : path;
}

static int starts_with(const char *s, const char *prefix) {
    return s && prefix && strncmp(s, prefix, strlen(prefix)) == 0;
}

static int is_system_image(const char *path) {
    return starts_with(path, "/usr/lib/") ||
           starts_with(path, "/System/Library/") ||
           starts_with(path, "/System/iOSSupport/") ||
           strstr(path ? path : "", "/Cryptexes/OS/") != NULL;
}

static int is_function_section(const section_info *sections, uint8_t n_sect) {
    if (!sections || n_sect == 0) {
        return 0;
    }
    const section_info *sec = &sections[n_sect - 1];
    if ((sec->flags & S_ATTR_PURE_INSTRUCTIONS) ||
        (sec->flags & S_ATTR_SOME_INSTRUCTIONS)) {
        return 1;
    }
    return strcmp(sec->sectname, "__text") == 0 ||
           strcmp(sec->sectname, "__stubs") == 0;
}

static int is_code_address(const code_range *ranges, size_t range_count, uintptr_t address) {
    for (size_t i = 0; i < range_count; i++) {
        if (address >= ranges[i].start && address < ranges[i].end) {
            return 1;
        }
    }
    return 0;
}

static const char *normalized_name(const char *name, unsigned flags) {
    if (!name) {
        return "";
    }
    if ((flags & TAILOR_PROFILE_RAW_SYMBOL_NAMES) == 0 && name[0] == '_' && name[1] != '\0') {
        return name + 1;
    }
    return name;
}

static void walk_export_trie(tailor_profile *profile,
                             const char *path,
                             const char *module_name,
                             uintptr_t module_base,
                             const uint8_t *trie,
                             const uint8_t *node,
                             const uint8_t *end,
                             char *name_buf,
                             size_t name_len,
                             size_t name_cap,
                             const code_range *ranges,
                             size_t range_count,
                             unsigned flags,
                             int *rc) {
    if (*rc < 0 || node >= end || name_len >= name_cap) {
        return;
    }
    const uint8_t *p = node;
    uint64_t terminal_size = read_uleb128(&p, end);
    const uint8_t *children = p + terminal_size;
    if (terminal_size > 0 && children <= end) {
        const uint8_t *term = p;
        uint64_t export_flags = read_uleb128(&term, children);
        if ((export_flags & 0x08u) == 0) {
            uint64_t address = read_uleb128(&term, children);
            uintptr_t absolute = module_base + (uintptr_t)address;
            if (is_code_address(ranges, range_count, absolute)) {
                name_buf[name_len] = '\0';
                *rc = tailor_profile_add(profile,
                                         path,
                                         module_name,
                                         normalized_name(name_buf, flags),
                                         module_base,
                                         absolute);
                if (*rc < 0) {
                    return;
                }
            }
        }
    }
    if (children >= end) {
        return;
    }
    uint8_t child_count = *children++;
    for (uint8_t i = 0; i < child_count; i++) {
        size_t edge_len = 0;
        while (children < end && *children && name_len + edge_len + 1 < name_cap) {
            name_buf[name_len + edge_len] = (char)*children++;
            edge_len++;
        }
        while (children < end && *children) {
            children++;
        }
        if (children >= end) {
            return;
        }
        children++;
        uint64_t child_off = read_uleb128(&children, end);
        if (child_off < (uint64_t)(end - trie)) {
            walk_export_trie(profile,
                             path,
                             module_name,
                             module_base,
                             trie,
                             trie + child_off,
                             end,
                             name_buf,
                             name_len + edge_len,
                             name_cap,
                             ranges,
                             range_count,
                             flags,
                             rc);
        }
    }
}

static int collect_image(tailor_profile *profile,
                         const struct mach_header *header,
                         intptr_t slide,
                         const char *path,
                         unsigned flags) {
    if (!header || header->magic != MH_MAGIC_64) {
        return 0;
    }
    if ((flags & TAILOR_PROFILE_SYSTEM_ONLY) && !is_system_image(path)) {
        return 0;
    }

    const struct mach_header_64 *mh = (const struct mach_header_64 *)header;
    const struct load_command *cmd = (const struct load_command *)(mh + 1);
    const struct symtab_command *symtab = NULL;
    const struct dysymtab_command *dysymtab = NULL;
    const struct segment_command_64 *linkedit = NULL;
    uint32_t export_off = 0;
    uint32_t export_size = 0;
    uint64_t base_vmaddr = UINT64_MAX;
    uint64_t text_vmaddr = UINT64_MAX;
    uint32_t section_count = 0;
    code_range ranges[256];
    size_t range_count = 0;

    for (uint32_t i = 0; i < mh->ncmds; i++) {
        if (cmd->cmd == LC_SEGMENT_64) {
            const struct segment_command_64 *seg = (const struct segment_command_64 *)cmd;
            const struct section_64 *sec = (const struct section_64 *)(seg + 1);
            if (seg->vmaddr < base_vmaddr) {
                base_vmaddr = seg->vmaddr;
            }
            if (strcmp(seg->segname, "__TEXT") == 0) {
                text_vmaddr = seg->vmaddr;
            }
            if (strcmp(seg->segname, "__LINKEDIT") == 0) {
                linkedit = seg;
            }
            for (uint32_t j = 0; j < seg->nsects && range_count < sizeof(ranges) / sizeof(ranges[0]); j++) {
                if ((sec[j].flags & S_ATTR_PURE_INSTRUCTIONS) ||
                    (sec[j].flags & S_ATTR_SOME_INSTRUCTIONS) ||
                    strcmp(sec[j].sectname, "__text") == 0 ||
                    strcmp(sec[j].sectname, "__stubs") == 0) {
                    ranges[range_count].start = (uintptr_t)((int64_t)sec[j].addr + slide);
                    ranges[range_count].end = ranges[range_count].start + (uintptr_t)sec[j].size;
                    range_count++;
                }
            }
            section_count += seg->nsects;
        } else if (cmd->cmd == LC_SYMTAB) {
            symtab = (const struct symtab_command *)cmd;
        } else if (cmd->cmd == LC_DYSYMTAB) {
            dysymtab = (const struct dysymtab_command *)cmd;
        } else if (cmd->cmd == LC_DYLD_INFO || cmd->cmd == LC_DYLD_INFO_ONLY) {
            const struct dyld_info_command *dyld_info = (const struct dyld_info_command *)cmd;
            export_off = dyld_info->export_off;
            export_size = dyld_info->export_size;
        } else if (cmd->cmd == LC_DYLD_EXPORTS_TRIE) {
            const struct linkedit_data_command *exports = (const struct linkedit_data_command *)cmd;
            export_off = exports->dataoff;
            export_size = exports->datasize;
        }
        cmd = (const struct load_command *)((const char *)cmd + cmd->cmdsize);
    }

    if (!linkedit) {
        return 0;
    }
    if (text_vmaddr != UINT64_MAX) {
        base_vmaddr = text_vmaddr;
    }
    if (base_vmaddr == UINT64_MAX) {
        return 0;
    }

    uintptr_t linkedit_base = (uintptr_t)((int64_t)linkedit->vmaddr + slide - (int64_t)linkedit->fileoff);
    uintptr_t module_base = (uintptr_t)((int64_t)base_vmaddr + slide);
    const char *module_name = basename_of(path);
    int rc = 0;

    if (export_off && export_size) {
        const uint8_t *trie = (const uint8_t *)(linkedit_base + export_off);
        char name_buf[512];
        walk_export_trie(profile,
                         path,
                         module_name,
                         module_base,
                         trie,
                         trie,
                         trie + export_size,
                         name_buf,
                         0,
                         sizeof(name_buf),
                         ranges,
                         range_count,
                         flags,
                         &rc);
        if (rc < 0) {
            return rc;
        }
    }

    if (!symtab || section_count == 0) {
        return 0;
    }

    section_info *sections = (section_info *)calloc(section_count, sizeof(*sections));
    if (!sections) {
        tailor_profile_set_error("out of memory");
        return -1;
    }

    cmd = (const struct load_command *)(mh + 1);
    uint32_t section_index = 0;
    for (uint32_t i = 0; i < mh->ncmds; i++) {
        if (cmd->cmd == LC_SEGMENT_64) {
            const struct segment_command_64 *seg = (const struct segment_command_64 *)cmd;
            const struct section_64 *sec = (const struct section_64 *)(seg + 1);
            for (uint32_t j = 0; j < seg->nsects && section_index < section_count; j++) {
                memcpy(sections[section_index].segname, sec[j].segname, 16);
                memcpy(sections[section_index].sectname, sec[j].sectname, 16);
                sections[section_index].segname[16] = '\0';
                sections[section_index].sectname[16] = '\0';
                sections[section_index].flags = sec[j].flags;
                section_index++;
            }
        }
        cmd = (const struct load_command *)((const char *)cmd + cmd->cmdsize);
    }

    const struct nlist_64 *symbols = (const struct nlist_64 *)(linkedit_base + symtab->symoff);
    const char *strings = (const char *)(linkedit_base + symtab->stroff);
    uint32_t start = 0;
    uint32_t count = symtab->nsyms;
    if (dysymtab && dysymtab->nextdefsym > 0 && dysymtab->iextdefsym < symtab->nsyms) {
        start = dysymtab->iextdefsym;
        count = dysymtab->nextdefsym;
        if (start + count > symtab->nsyms) {
            count = symtab->nsyms - start;
        }
    }

    for (uint32_t i = start; i < start + count; i++) {
        const struct nlist_64 *nl = &symbols[i];
        if ((nl->n_type & N_STAB) != 0) {
            continue;
        }
        if ((nl->n_type & N_EXT) == 0 || (nl->n_type & N_TYPE) != N_SECT) {
            continue;
        }
        if (!is_function_section(sections, nl->n_sect)) {
            continue;
        }
        if (nl->n_un.n_strx == 0 || nl->n_value == 0) {
            continue;
        }
        const char *raw = strings + nl->n_un.n_strx;
        const char *name = normalized_name(raw, flags);
        uintptr_t address = (uintptr_t)((int64_t)nl->n_value + slide);
        if (!is_code_address(ranges, range_count, address)) {
            continue;
        }
        rc = tailor_profile_add(profile, path, module_name, name, module_base, address);
        if (rc < 0) {
            break;
        }
    }

    free(sections);
    return rc;
}

int tailor_profile_collect(tailor_profile *profile, unsigned flags) {
    if (!profile) {
        tailor_profile_set_error("profile is null");
        return -1;
    }
    for (uint32_t i = 0; i < _dyld_image_count(); i++) {
        const struct mach_header *header = _dyld_get_image_header(i);
        intptr_t slide = _dyld_get_image_vmaddr_slide(i);
        const char *path = _dyld_get_image_name(i);
        int rc = collect_image(profile, header, slide, path, flags);
        if (rc < 0) {
            return rc;
        }
    }
    tailor_profile_sort(profile);
    return 0;
}

#endif
