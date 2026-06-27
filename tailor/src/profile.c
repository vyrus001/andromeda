#include "tailor/profile.h"

#include <stdarg.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static char g_last_error[512];

uint64_t tailor_hash_fnv1a64(const char *s) {
    uint64_t h = UINT64_C(14695981039346656037);
    while (s && *s) {
        h ^= (unsigned char)*s++;
        h *= UINT64_C(1099511628211);
    }
    return h;
}

void tailor_profile_init(tailor_profile *profile) {
    if (!profile) {
        return;
    }
    profile->items = NULL;
    profile->len = 0;
    profile->cap = 0;
}

void tailor_profile_free(tailor_profile *profile) {
    if (!profile) {
        return;
    }
    for (size_t i = 0; i < profile->len; i++) {
        free(profile->items[i].module_path);
        free(profile->items[i].module_name);
        free(profile->items[i].symbol_name);
    }
    free(profile->items);
    tailor_profile_init(profile);
}

static char *xstrdup(const char *s) {
    if (!s) {
        s = "";
    }
    size_t n = strlen(s) + 1;
    char *copy = (char *)malloc(n);
    if (!copy) {
        tailor_profile_set_error("out of memory");
        return NULL;
    }
    memcpy(copy, s, n);
    return copy;
}

int tailor_profile_add(tailor_profile *profile,
                       const char *module_path,
                       const char *module_name,
                       const char *symbol_name,
                       uintptr_t module_base,
                       uintptr_t address) {
    if (!profile || !symbol_name || !*symbol_name || address == 0) {
        return 0;
    }
    if (address < module_base) {
        return 0;
    }
    if (profile->len == profile->cap) {
        size_t next = profile->cap ? profile->cap * 2 : 256;
        tailor_symbol *items = (tailor_symbol *)realloc(profile->items, next * sizeof(*items));
        if (!items) {
            tailor_profile_set_error("out of memory");
            return -1;
        }
        profile->items = items;
        profile->cap = next;
    }

    tailor_symbol *sym = &profile->items[profile->len];
    memset(sym, 0, sizeof(*sym));
    sym->module_path = xstrdup(module_path);
    sym->module_name = xstrdup(module_name);
    sym->symbol_name = xstrdup(symbol_name);
    if (!sym->module_path || !sym->module_name || !sym->symbol_name) {
        free(sym->module_path);
        free(sym->module_name);
        free(sym->symbol_name);
        memset(sym, 0, sizeof(*sym));
        return -1;
    }
    sym->module_hash = tailor_hash_fnv1a64(sym->module_name);
    sym->symbol_hash = tailor_hash_fnv1a64(sym->symbol_name);
    sym->module_base = module_base;
    sym->address = address;
    sym->offset = (uint64_t)(address - module_base);
    profile->len++;
    return 0;
}

static int cmp_symbol(const void *a, const void *b) {
    const tailor_symbol *sa = (const tailor_symbol *)a;
    const tailor_symbol *sb = (const tailor_symbol *)b;
    int c = strcmp(sa->module_path, sb->module_path);
    if (c != 0) {
        return c;
    }
    c = strcmp(sa->symbol_name, sb->symbol_name);
    if (c != 0) {
        return c;
    }
    if (sa->offset < sb->offset) {
        return -1;
    }
    if (sa->offset > sb->offset) {
        return 1;
    }
    return 0;
}

void tailor_profile_sort(tailor_profile *profile) {
    if (!profile || profile->len < 2) {
        return;
    }
    qsort(profile->items, profile->len, sizeof(profile->items[0]), cmp_symbol);

    size_t out = 1;
    for (size_t i = 1; i < profile->len; i++) {
        tailor_symbol *prev = &profile->items[out - 1];
        tailor_symbol *cur = &profile->items[i];
        if (strcmp(prev->module_path, cur->module_path) == 0 &&
            strcmp(prev->symbol_name, cur->symbol_name) == 0 &&
            prev->offset == cur->offset) {
            free(cur->module_path);
            free(cur->module_name);
            free(cur->symbol_name);
            memset(cur, 0, sizeof(*cur));
            continue;
        }
        if (out != i) {
            profile->items[out] = profile->items[i];
            memset(&profile->items[i], 0, sizeof(profile->items[i]));
        }
        out++;
    }
    profile->len = out;
}

const char *tailor_profile_last_error(void) {
    return g_last_error[0] ? g_last_error : "no error";
}

void tailor_profile_set_error(const char *fmt, ...) {
    if (!fmt) {
        g_last_error[0] = '\0';
        return;
    }
    va_list ap;
    va_start(ap, fmt);
    vsnprintf(g_last_error, sizeof(g_last_error), fmt, ap);
    va_end(ap);
}
