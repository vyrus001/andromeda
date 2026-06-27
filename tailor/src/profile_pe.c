#include "tailor/profile.h"

#if defined(_WIN32)

#include <stdint.h>
#include <stdlib.h>
#include <string.h>

typedef unsigned short WCHAR;
typedef struct LIST_ENTRY_T {
    struct LIST_ENTRY_T *Flink;
    struct LIST_ENTRY_T *Blink;
} LIST_ENTRY_T;

typedef struct UNICODE_STRING_T {
    unsigned short Length;
    unsigned short MaximumLength;
    WCHAR *Buffer;
} UNICODE_STRING_T;

typedef struct PEB_LDR_DATA_T {
    unsigned long Length;
    unsigned char Initialized;
    void *SsHandle;
    LIST_ENTRY_T InLoadOrderModuleList;
    LIST_ENTRY_T InMemoryOrderModuleList;
    LIST_ENTRY_T InInitializationOrderModuleList;
} PEB_LDR_DATA_T;

typedef struct LDR_DATA_TABLE_ENTRY_T {
    LIST_ENTRY_T InLoadOrderLinks;
    LIST_ENTRY_T InMemoryOrderLinks;
    LIST_ENTRY_T InInitializationOrderLinks;
    void *DllBase;
    void *EntryPoint;
    unsigned long SizeOfImage;
    UNICODE_STRING_T FullDllName;
    UNICODE_STRING_T BaseDllName;
} LDR_DATA_TABLE_ENTRY_T;

typedef struct PEB_T {
    unsigned char Reserved1[2];
    unsigned char BeingDebugged;
    unsigned char Reserved2[1];
    void *Reserved3[2];
    PEB_LDR_DATA_T *Ldr;
} PEB_T;

#if defined(_M_X64) || defined(__x86_64__)
static PEB_T *current_peb(void) {
    return (PEB_T *)__builtin_readgsqword(0x60);
}
#elif defined(_M_IX86) || defined(__i386__)
static PEB_T *current_peb(void) {
    return (PEB_T *)__builtin_readfsdword(0x30);
}
#else
static PEB_T *current_peb(void) {
    return 0;
}
#endif

static uint16_t rd16(const void *p) {
    const unsigned char *b = (const unsigned char *)p;
    return (uint16_t)(b[0] | ((uint16_t)b[1] << 8));
}

static uint32_t rd32(const void *p) {
    const unsigned char *b = (const unsigned char *)p;
    return (uint32_t)b[0] |
           ((uint32_t)b[1] << 8) |
           ((uint32_t)b[2] << 16) |
           ((uint32_t)b[3] << 24);
}

static void wide_to_ascii(const UNICODE_STRING_T *s, char *out, size_t cap) {
    size_t n = 0;
    if (!s || !s->Buffer || cap == 0) {
        if (cap) {
            out[0] = '\0';
        }
        return;
    }
    size_t chars = s->Length / sizeof(WCHAR);
    for (size_t i = 0; i < chars && n + 1 < cap; i++) {
        WCHAR wc = s->Buffer[i];
        out[n++] = (wc >= 0x20 && wc <= 0x7e) ? (char)wc : '?';
    }
    out[n] = '\0';
}

static int profile_pe_exports(tailor_profile *profile,
                              const char *module_path,
                              const char *module_name,
                              uintptr_t module_base) {
    const unsigned char *base = (const unsigned char *)module_base;
    if (!base || rd16(base) != 0x5a4d) {
        return 0;
    }
    uint32_t pe_off = rd32(base + 0x3c);
    const unsigned char *nt = base + pe_off;
    if (rd32(nt) != 0x00004550) {
        return 0;
    }
    uint16_t opt_size = rd16(nt + 20);
    const unsigned char *opt = nt + 24;
    uint16_t magic = rd16(opt);
    uint32_t data_dir = (magic == 0x20b) ? 112u : 96u;
    if (opt_size < data_dir + 8) {
        return 0;
    }
    uint32_t export_rva = rd32(opt + data_dir);
    uint32_t export_size = rd32(opt + data_dir + 4);
    if (!export_rva || export_size < 40) {
        return 0;
    }

    const unsigned char *exp = base + export_rva;
    uint32_t number_of_names = rd32(exp + 24);
    uint32_t functions_rva = rd32(exp + 28);
    uint32_t names_rva = rd32(exp + 32);
    uint32_t ordinals_rva = rd32(exp + 36);
    const unsigned char *functions = base + functions_rva;
    const unsigned char *names = base + names_rva;
    const unsigned char *ordinals = base + ordinals_rva;

    for (uint32_t i = 0; i < number_of_names; i++) {
        uint32_t name_rva = rd32(names + i * 4);
        uint16_t ordinal = rd16(ordinals + i * 2);
        uint32_t function_rva = rd32(functions + (uint32_t)ordinal * 4);
        if (!name_rva || !function_rva) {
            continue;
        }
        if (function_rva >= export_rva && function_rva < export_rva + export_size) {
            continue;
        }
        const char *name = (const char *)(base + name_rva);
        int rc = tailor_profile_add(profile,
                                    module_path,
                                    module_name,
                                    name,
                                    module_base,
                                    module_base + function_rva);
        if (rc < 0) {
            return rc;
        }
    }
    return 0;
}

int tailor_profile_collect(tailor_profile *profile, unsigned flags) {
    (void)flags;
    if (!profile) {
        tailor_profile_set_error("profile is null");
        return -1;
    }
    PEB_T *peb = current_peb();
    if (!peb || !peb->Ldr) {
        tailor_profile_set_error("unable to locate PEB loader data");
        return -1;
    }

    LIST_ENTRY_T *head = &peb->Ldr->InLoadOrderModuleList;
    for (LIST_ENTRY_T *node = head->Flink; node && node != head; node = node->Flink) {
        LDR_DATA_TABLE_ENTRY_T *entry = (LDR_DATA_TABLE_ENTRY_T *)node;
        char module_path[1024];
        char module_name[512];
        wide_to_ascii(&entry->FullDllName, module_path, sizeof(module_path));
        wide_to_ascii(&entry->BaseDllName, module_name, sizeof(module_name));
        if (!module_name[0]) {
            strcpy(module_name, "<unknown>");
        }
        if (!module_path[0]) {
            strcpy(module_path, module_name);
        }
        int rc = profile_pe_exports(profile,
                                    module_path,
                                    module_name,
                                    (uintptr_t)entry->DllBase);
        if (rc < 0) {
            return rc;
        }
    }
    tailor_profile_sort(profile);
    return 0;
}

#endif

