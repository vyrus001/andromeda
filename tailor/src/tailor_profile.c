#include "tailor/profile.h"

#include <errno.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

typedef struct string_set {
    char **items;
    size_t len;
    size_t cap;
} string_set;

static void usage(FILE *stream) {
    fputs(
        "usage: tailor-profile [options]\n"
        "\n"
        "Options:\n"
        "  --format json|tsv        Output format (default: json)\n"
        "  --system-only            Keep system libraries only\n"
        "  --all-modules            Include non-system images (default)\n"
        "  --module TEXT            Keep module path/name containing TEXT\n"
        "  --symbol TEXT            Keep symbol name containing TEXT\n"
        "  --symbols FILE           Keep exact symbol names listed in FILE\n"
        "  --addresses              Include observed absolute addresses\n"
        "  --no-names               Omit cleartext names from JSON/TSV\n"
        "  --raw-symbol-names       Disable platform symbol normalization\n"
        "  --help                   Show this help\n",
        stream);
}

static char *xstrdup_local(const char *s) {
    size_t n = strlen(s) + 1;
    char *copy = (char *)malloc(n);
    if (copy) {
        memcpy(copy, s, n);
    }
    return copy;
}

static void string_set_free(string_set *set) {
    if (!set) {
        return;
    }
    for (size_t i = 0; i < set->len; i++) {
        free(set->items[i]);
    }
    free(set->items);
    set->items = NULL;
    set->len = 0;
    set->cap = 0;
}

static int string_set_add(string_set *set, const char *s) {
    if (!s || !*s) {
        return 0;
    }
    if (set->len == set->cap) {
        size_t next = set->cap ? set->cap * 2 : 64;
        char **items = (char **)realloc(set->items, next * sizeof(*items));
        if (!items) {
            return -1;
        }
        set->items = items;
        set->cap = next;
    }
    set->items[set->len] = xstrdup_local(s);
    if (!set->items[set->len]) {
        return -1;
    }
    set->len++;
    return 0;
}

static int string_set_contains(const string_set *set, const char *s) {
    if (!set || set->len == 0) {
        return 1;
    }
    for (size_t i = 0; i < set->len; i++) {
        if (strcmp(set->items[i], s) == 0) {
            return 1;
        }
    }
    return 0;
}

static int read_symbols_file(const char *path, string_set *set) {
    FILE *f = fopen(path, "r");
    if (!f) {
        fprintf(stderr, "tailor-profile: %s: %s\n", path, strerror(errno));
        return -1;
    }
    char line[4096];
    while (fgets(line, sizeof(line), f)) {
        char *s = line;
        while (*s == ' ' || *s == '\t') {
            s++;
        }
        char *comment = strchr(s, '#');
        if (comment) {
            *comment = '\0';
        }
        size_t n = strlen(s);
        while (n > 0 && (s[n - 1] == '\n' || s[n - 1] == '\r' || s[n - 1] == ' ' || s[n - 1] == '\t')) {
            s[--n] = '\0';
        }
        if (n > 0 && string_set_add(set, s) < 0) {
            fclose(f);
            fprintf(stderr, "tailor-profile: out of memory\n");
            return -1;
        }
    }
    if (ferror(f)) {
        fprintf(stderr, "tailor-profile: %s: read error\n", path);
        fclose(f);
        return -1;
    }
    fclose(f);
    return 0;
}

static int contains_text(const char *haystack, const char *needle) {
    return !needle || !*needle || (haystack && strstr(haystack, needle) != NULL);
}

static void filter_profile(tailor_profile *profile,
                           const char *module_filter,
                           const char *symbol_filter,
                           const string_set *symbols) {
    size_t out = 0;
    for (size_t i = 0; i < profile->len; i++) {
        tailor_symbol *sym = &profile->items[i];
        int keep = contains_text(sym->module_path, module_filter) ||
                   contains_text(sym->module_name, module_filter);
        keep = keep &&
               contains_text(sym->symbol_name, symbol_filter) &&
               string_set_contains(symbols, sym->symbol_name);
        if (keep) {
            if (out != i) {
                profile->items[out] = profile->items[i];
                memset(&profile->items[i], 0, sizeof(profile->items[i]));
            }
            out++;
        } else {
            free(sym->module_path);
            free(sym->module_name);
            free(sym->symbol_name);
            memset(sym, 0, sizeof(*sym));
        }
    }
    profile->len = out;
}

int main(int argc, char **argv) {
    const char *format = "json";
    const char *module_filter = NULL;
    const char *symbol_filter = NULL;
    string_set exact_symbols = {0};
    unsigned collect_flags = 0;
    unsigned write_flags = TAILOR_PROFILE_WRITE_NAMES;

    for (int i = 1; i < argc; i++) {
        if (strcmp(argv[i], "--help") == 0) {
            usage(stdout);
            return 0;
        } else if (strcmp(argv[i], "--format") == 0 && i + 1 < argc) {
            format = argv[++i];
        } else if (strcmp(argv[i], "--system-only") == 0) {
            collect_flags |= TAILOR_PROFILE_SYSTEM_ONLY;
        } else if (strcmp(argv[i], "--all-modules") == 0) {
            collect_flags &= ~TAILOR_PROFILE_SYSTEM_ONLY;
        } else if (strcmp(argv[i], "--module") == 0 && i + 1 < argc) {
            module_filter = argv[++i];
        } else if (strcmp(argv[i], "--symbol") == 0 && i + 1 < argc) {
            symbol_filter = argv[++i];
        } else if (strcmp(argv[i], "--symbols") == 0 && i + 1 < argc) {
            if (read_symbols_file(argv[++i], &exact_symbols) < 0) {
                string_set_free(&exact_symbols);
                return 2;
            }
        } else if (strcmp(argv[i], "--addresses") == 0) {
            write_flags |= TAILOR_PROFILE_WRITE_ADDRESSES;
        } else if (strcmp(argv[i], "--no-names") == 0) {
            write_flags &= ~TAILOR_PROFILE_WRITE_NAMES;
        } else if (strcmp(argv[i], "--raw-symbol-names") == 0) {
            collect_flags |= TAILOR_PROFILE_RAW_SYMBOL_NAMES;
        } else {
            fprintf(stderr, "tailor-profile: unknown or incomplete option: %s\n", argv[i]);
            usage(stderr);
            string_set_free(&exact_symbols);
            return 2;
        }
    }

    if (strcmp(format, "json") != 0 && strcmp(format, "tsv") != 0) {
        fprintf(stderr, "tailor-profile: unsupported format: %s\n", format);
        string_set_free(&exact_symbols);
        return 2;
    }

    tailor_profile profile;
    tailor_profile_init(&profile);
    if (tailor_profile_collect(&profile, collect_flags) < 0) {
        fprintf(stderr, "tailor-profile: %s\n", tailor_profile_last_error());
        tailor_profile_free(&profile);
        string_set_free(&exact_symbols);
        return 1;
    }

    filter_profile(&profile, module_filter, symbol_filter, &exact_symbols);

    int rc;
    if (strcmp(format, "json") == 0) {
        rc = tailor_profile_write_json(stdout, &profile, write_flags);
    } else {
        rc = tailor_profile_write_tsv(stdout, &profile, write_flags);
    }
    if (rc < 0) {
        fprintf(stderr, "tailor-profile: %s\n", tailor_profile_last_error());
    }

    tailor_profile_free(&profile);
    string_set_free(&exact_symbols);
    return rc < 0 ? 1 : 0;
}
