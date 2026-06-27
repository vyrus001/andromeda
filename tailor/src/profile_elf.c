#if defined(__linux__)

#define _GNU_SOURCE
#include "tailor/profile.h"

#include <elf.h>
#include <link.h>

#include <stdint.h>
#include <string.h>

static const char *basename_of(const char *path) {
    if (!path || !*path) {
        return "<main>";
    }
    const char *slash = strrchr(path, '/');
    return slash ? slash + 1 : path;
}

static int starts_with(const char *s, const char *prefix) {
    return s && prefix && strncmp(s, prefix, strlen(prefix)) == 0;
}

static int is_system_image(const char *path) {
    return starts_with(path, "/lib/") ||
           starts_with(path, "/lib64/") ||
           starts_with(path, "/usr/lib/") ||
           starts_with(path, "/usr/lib64/") ||
           starts_with(path, "/usr/local/lib/");
}

static uintptr_t dyn_addr(uintptr_t base, ElfW(Addr) ptr) {
    if ((uintptr_t)ptr >= base && base != 0) {
        return (uintptr_t)ptr;
    }
    return base + (uintptr_t)ptr;
}

static size_t gnu_hash_symbol_count(const uint32_t *gnu_hash) {
    if (!gnu_hash) {
        return 0;
    }
    uint32_t nbuckets = gnu_hash[0];
    uint32_t symoffset = gnu_hash[1];
    uint32_t bloom_size = gnu_hash[2];
    const unsigned char *p = (const unsigned char *)(gnu_hash + 4);
    p += bloom_size * sizeof(ElfW(Addr));
    const uint32_t *buckets = (const uint32_t *)p;
    const uint32_t *chains = buckets + nbuckets;

    uint32_t max_idx = symoffset;
    for (uint32_t i = 0; i < nbuckets; i++) {
        uint32_t idx = buckets[i];
        if (idx == 0) {
            continue;
        }
        while (1) {
            uint32_t chain = chains[idx - symoffset];
            if (idx > max_idx) {
                max_idx = idx;
            }
            if (chain & 1u) {
                break;
            }
            idx++;
        }
    }
    return (size_t)max_idx + 1;
}

typedef struct collect_ctx {
    tailor_profile *profile;
    unsigned flags;
    int rc;
} collect_ctx;

static int collect_module(struct dl_phdr_info *info, size_t size, void *data) {
    (void)size;
    collect_ctx *ctx = (collect_ctx *)data;
    const char *path = (info->dlpi_name && info->dlpi_name[0]) ? info->dlpi_name : "";
    if ((ctx->flags & TAILOR_PROFILE_SYSTEM_ONLY) && !is_system_image(path)) {
        return 0;
    }

    uintptr_t base = (uintptr_t)info->dlpi_addr;
    const ElfW(Dyn) *dynamic = NULL;
    for (ElfW(Half) i = 0; i < info->dlpi_phnum; i++) {
        if (info->dlpi_phdr[i].p_type == PT_DYNAMIC) {
            dynamic = (const ElfW(Dyn) *)(base + info->dlpi_phdr[i].p_vaddr);
            break;
        }
    }
    if (!dynamic) {
        return 0;
    }

    const ElfW(Sym) *symtab = NULL;
    const char *strtab = NULL;
    const uint32_t *sysv_hash = NULL;
    const uint32_t *gnu_hash = NULL;
    size_t syment = sizeof(ElfW(Sym));

    for (const ElfW(Dyn) *dyn = dynamic; dyn->d_tag != DT_NULL; dyn++) {
        switch (dyn->d_tag) {
            case DT_SYMTAB:
                symtab = (const ElfW(Sym) *)dyn_addr(base, dyn->d_un.d_ptr);
                break;
            case DT_STRTAB:
                strtab = (const char *)dyn_addr(base, dyn->d_un.d_ptr);
                break;
            case DT_HASH:
                sysv_hash = (const uint32_t *)dyn_addr(base, dyn->d_un.d_ptr);
                break;
            case DT_GNU_HASH:
                gnu_hash = (const uint32_t *)dyn_addr(base, dyn->d_un.d_ptr);
                break;
            case DT_SYMENT:
                syment = (size_t)dyn->d_un.d_val;
                break;
            default:
                break;
        }
    }

    if (!symtab || !strtab || syment != sizeof(ElfW(Sym))) {
        return 0;
    }

    size_t nsyms = 0;
    if (sysv_hash) {
        nsyms = sysv_hash[1];
    } else if (gnu_hash) {
        nsyms = gnu_hash_symbol_count(gnu_hash);
    }
    if (nsyms == 0) {
        return 0;
    }

    const char *module_name = basename_of(path);
    const char *module_path = path[0] ? path : "<main>";
    for (size_t i = 0; i < nsyms; i++) {
        const ElfW(Sym) *sym = &symtab[i];
        unsigned type = ELF64_ST_TYPE(sym->st_info);
        unsigned bind = ELF64_ST_BIND(sym->st_info);
        if (sym->st_name == 0 || sym->st_value == 0 || sym->st_shndx == SHN_UNDEF) {
            continue;
        }
        if (type != STT_FUNC && type != STT_GNU_IFUNC) {
            continue;
        }
        if (bind != STB_GLOBAL && bind != STB_WEAK) {
            continue;
        }
        uintptr_t address = base + (uintptr_t)sym->st_value;
        ctx->rc = tailor_profile_add(ctx->profile,
                                     module_path,
                                     module_name,
                                     strtab + sym->st_name,
                                     base,
                                     address);
        if (ctx->rc < 0) {
            return 1;
        }
    }
    return 0;
}

int tailor_profile_collect(tailor_profile *profile, unsigned flags) {
    if (!profile) {
        tailor_profile_set_error("profile is null");
        return -1;
    }
    collect_ctx ctx = {profile, flags, 0};
    dl_iterate_phdr(collect_module, &ctx);
    if (ctx.rc < 0) {
        return ctx.rc;
    }
    tailor_profile_sort(profile);
    return 0;
}

#endif
