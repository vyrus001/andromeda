#include "tailor/profile.h"

#include <inttypes.h>
#include <stdio.h>
#include <string.h>

static void json_string(FILE *stream, const char *s) {
    fputc('"', stream);
    for (; s && *s; s++) {
        unsigned char c = (unsigned char)*s;
        switch (c) {
            case '"':
                fputs("\\\"", stream);
                break;
            case '\\':
                fputs("\\\\", stream);
                break;
            case '\b':
                fputs("\\b", stream);
                break;
            case '\f':
                fputs("\\f", stream);
                break;
            case '\n':
                fputs("\\n", stream);
                break;
            case '\r':
                fputs("\\r", stream);
                break;
            case '\t':
                fputs("\\t", stream);
                break;
            default:
                if (c < 0x20) {
                    fprintf(stream, "\\u%04x", c);
                } else {
                    fputc(c, stream);
                }
        }
    }
    fputc('"', stream);
}

static void tsv_string(FILE *stream, const char *s) {
    for (; s && *s; s++) {
        if (*s == '\t' || *s == '\n' || *s == '\r') {
            fputc(' ', stream);
        } else {
            fputc(*s, stream);
        }
    }
}

int tailor_profile_write_json(FILE *stream,
                              const tailor_profile *profile,
                              unsigned write_flags) {
    if (!stream || !profile) {
        tailor_profile_set_error("invalid json writer arguments");
        return -1;
    }
    int names = (write_flags & TAILOR_PROFILE_WRITE_NAMES) != 0;
    int addresses = (write_flags & TAILOR_PROFILE_WRITE_ADDRESSES) != 0;

    fputs("{\n", stream);
    fputs("  \"format\": \"tailor.symbol-profile.v1\",\n", stream);
    fputs("  \"hash\": \"fnv1a64-case-sensitive\",\n", stream);
    fputs("  \"offset_base\": \"loaded-module-image-base\",\n", stream);
    fprintf(stream, "  \"entry_count\": %zu,\n", profile->len);
    fputs("  \"entries\": [\n", stream);
    for (size_t i = 0; i < profile->len; i++) {
        const tailor_symbol *sym = &profile->items[i];
        fputs("    {", stream);
        fprintf(stream,
                "\"module_hash\":\"0x%016" PRIx64 "\","
                "\"function_hash\":\"0x%016" PRIx64 "\","
                "\"offset\":\"0x%016" PRIx64 "\"",
                sym->module_hash,
                sym->symbol_hash,
                sym->offset);
        if (addresses) {
            fprintf(stream,
                    ",\"module_base\":\"0x%016" PRIxPTR "\","
                    "\"address\":\"0x%016" PRIxPTR "\"",
                    sym->module_base,
                    sym->address);
        }
        if (names) {
            fputs(",\"module\":", stream);
            json_string(stream, sym->module_name);
            fputs(",\"path\":", stream);
            json_string(stream, sym->module_path);
            fputs(",\"name\":", stream);
            json_string(stream, sym->symbol_name);
        }
        fputc('}', stream);
        if (i + 1 < profile->len) {
            fputc(',', stream);
        }
        fputc('\n', stream);
    }
    fputs("  ]\n", stream);
    fputs("}\n", stream);
    return ferror(stream) ? -1 : 0;
}

int tailor_profile_write_tsv(FILE *stream,
                             const tailor_profile *profile,
                             unsigned write_flags) {
    if (!stream || !profile) {
        tailor_profile_set_error("invalid tsv writer arguments");
        return -1;
    }
    int names = (write_flags & TAILOR_PROFILE_WRITE_NAMES) != 0;
    int addresses = (write_flags & TAILOR_PROFILE_WRITE_ADDRESSES) != 0;

    fputs("module_hash\tfunction_hash\toffset", stream);
    if (addresses) {
        fputs("\tmodule_base\taddress", stream);
    }
    if (names) {
        fputs("\tmodule\tpath\tname", stream);
    }
    fputc('\n', stream);

    for (size_t i = 0; i < profile->len; i++) {
        const tailor_symbol *sym = &profile->items[i];
        fprintf(stream,
                "0x%016" PRIx64 "\t0x%016" PRIx64 "\t0x%016" PRIx64,
                sym->module_hash,
                sym->symbol_hash,
                sym->offset);
        if (addresses) {
            fprintf(stream,
                    "\t0x%016" PRIxPTR "\t0x%016" PRIxPTR,
                    sym->module_base,
                    sym->address);
        }
        if (names) {
            fputc('\t', stream);
            tsv_string(stream, sym->module_name);
            fputc('\t', stream);
            tsv_string(stream, sym->module_path);
            fputc('\t', stream);
            tsv_string(stream, sym->symbol_name);
        }
        fputc('\n', stream);
    }
    return ferror(stream) ? -1 : 0;
}

