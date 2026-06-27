#ifndef TAILOR_PROFILE_H
#define TAILOR_PROFILE_H

#include <stddef.h>
#include <stdint.h>
#include <stdio.h>

#ifdef __cplusplus
extern "C" {
#endif

enum tailor_profile_flags {
    TAILOR_PROFILE_SYSTEM_ONLY = 1u << 0,
    TAILOR_PROFILE_RAW_SYMBOL_NAMES = 1u << 1,
};

enum tailor_profile_write_flags {
    TAILOR_PROFILE_WRITE_NAMES = 1u << 0,
    TAILOR_PROFILE_WRITE_ADDRESSES = 1u << 1,
};

typedef struct tailor_symbol {
    char *module_path;
    char *module_name;
    char *symbol_name;
    uint64_t module_hash;
    uint64_t symbol_hash;
    uint64_t offset;
    uintptr_t address;
    uintptr_t module_base;
} tailor_symbol;

typedef struct tailor_profile {
    tailor_symbol *items;
    size_t len;
    size_t cap;
} tailor_profile;

uint64_t tailor_hash_fnv1a64(const char *s);

void tailor_profile_init(tailor_profile *profile);
void tailor_profile_free(tailor_profile *profile);

int tailor_profile_collect(tailor_profile *profile, unsigned flags);
int tailor_profile_add(tailor_profile *profile,
                       const char *module_path,
                       const char *module_name,
                       const char *symbol_name,
                       uintptr_t module_base,
                       uintptr_t address);
void tailor_profile_sort(tailor_profile *profile);

int tailor_profile_write_json(FILE *stream,
                              const tailor_profile *profile,
                              unsigned write_flags);
int tailor_profile_write_tsv(FILE *stream,
                             const tailor_profile *profile,
                             unsigned write_flags);

const char *tailor_profile_last_error(void);
void tailor_profile_set_error(const char *fmt, ...);

#ifdef __cplusplus
}
#endif

#endif

