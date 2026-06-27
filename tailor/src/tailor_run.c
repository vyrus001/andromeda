#define _DARWIN_C_SOURCE
#define _GNU_SOURCE

#include "tailor/profile.h"
#include "tailor/tinkr_context.h"

#include <errno.h>
#include <fcntl.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
#include <sys/stat.h>
#include <unistd.h>

#if defined(__APPLE__)
#include <libkern/OSCacheControl.h>
#endif

typedef struct module_builder {
    struct tinkr_context_module *items;
    size_t len;
    size_t cap;
} module_builder;

typedef struct function_builder {
    struct tinkr_context_function *items;
    size_t len;
    size_t cap;
} function_builder;

static void usage(FILE *stream) {
    fputs(
        "usage: tailor-run <blob.bin> [options]\n"
        "\n"
        "Options:\n"
        "  --system-only     Build context from system libraries only\n"
        "  --raw-symbols     Disable platform symbol normalization\n"
        "  --verbose         Print context sizes before executing\n"
        "  --help            Show this help\n",
        stream);
}

static int reserve_modules(module_builder *b, size_t need) {
    if (need <= b->cap) {
        return 0;
    }
    size_t next = b->cap ? b->cap * 2 : 64;
    while (next < need) {
        next *= 2;
    }
    void *p = realloc(b->items, next * sizeof(b->items[0]));
    if (!p) {
        return -1;
    }
    b->items = (struct tinkr_context_module *)p;
    b->cap = next;
    return 0;
}

static int reserve_functions(function_builder *b, size_t need) {
    if (need <= b->cap) {
        return 0;
    }
    size_t next = b->cap ? b->cap * 2 : 256;
    while (next < need) {
        next *= 2;
    }
    void *p = realloc(b->items, next * sizeof(b->items[0]));
    if (!p) {
        return -1;
    }
    b->items = (struct tinkr_context_function *)p;
    b->cap = next;
    return 0;
}

static int module_index_for(module_builder *modules, uint64_t module_hash, uintptr_t module_base) {
    for (size_t i = 0; i < modules->len; i++) {
        if (modules->items[i].module_hash == module_hash &&
            modules->items[i].module_base == (tinkr_u64)module_base) {
            return (int)i;
        }
    }
    if (reserve_modules(modules, modules->len + 1) < 0) {
        return -1;
    }
    modules->items[modules->len].module_hash = module_hash;
    modules->items[modules->len].module_base = (tinkr_u64)module_base;
    return (int)modules->len++;
}

static int build_context_from_profile(const tailor_profile *profile,
                                      module_builder *modules,
                                      function_builder *functions,
                                      struct tinkr_context *ctx) {
    memset(ctx, 0, sizeof(*ctx));
    ctx->version = TINKR_CONTEXT_ABI_VERSION;

    for (size_t i = 0; i < profile->len; i++) {
        const tailor_symbol *sym = &profile->items[i];
        int module_index = module_index_for(modules, sym->module_hash, sym->module_base);
        if (module_index < 0 || reserve_functions(functions, functions->len + 1) < 0) {
            fprintf(stderr, "tailor-run: out of memory while building context\n");
            return -1;
        }

        struct tinkr_context_function *fn = &functions->items[functions->len++];
        fn->module_hash = sym->module_hash;
        fn->function_hash = sym->symbol_hash;
        fn->offset = sym->offset;
        fn->module_index = (tinkr_u32)module_index;
        fn->flags = TINKR_CONTEXT_FUNCTION_EXPORT;
    }

    ctx->module_count = (tinkr_u32)modules->len;
    ctx->function_count = (tinkr_u32)functions->len;
    ctx->modules_ptr = (tinkr_u64)(uintptr_t)modules->items;
    ctx->functions_ptr = (tinkr_u64)(uintptr_t)functions->items;
    return 0;
}

static void *read_blob(const char *path, size_t *out_size) {
    int fd = open(path, O_RDONLY);
    if (fd < 0) {
        fprintf(stderr, "tailor-run: %s: %s\n", path, strerror(errno));
        return NULL;
    }

    struct stat st;
    if (fstat(fd, &st) < 0) {
        fprintf(stderr, "tailor-run: fstat(%s): %s\n", path, strerror(errno));
        close(fd);
        return NULL;
    }
    if (st.st_size <= 0) {
        fprintf(stderr, "tailor-run: %s is empty\n", path);
        close(fd);
        return NULL;
    }

    size_t size = (size_t)st.st_size;
    void *mem = mmap(NULL, size, PROT_READ | PROT_WRITE, MAP_PRIVATE | MAP_ANON, -1, 0);
    if (mem == MAP_FAILED) {
        fprintf(stderr, "tailor-run: mmap: %s\n", strerror(errno));
        close(fd);
        return NULL;
    }

    size_t done = 0;
    while (done < size) {
        ssize_t n = read(fd, (char *)mem + done, size - done);
        if (n <= 0) {
            fprintf(stderr, "tailor-run: read(%s): %s\n", path, n < 0 ? strerror(errno) : "short read");
            munmap(mem, size);
            close(fd);
            return NULL;
        }
        done += (size_t)n;
    }
    close(fd);

    if (mprotect(mem, size, PROT_READ | PROT_EXEC) < 0) {
        fprintf(stderr, "tailor-run: mprotect: %s\n", strerror(errno));
        munmap(mem, size);
        return NULL;
    }
#if defined(__APPLE__)
    sys_icache_invalidate(mem, size);
#elif defined(__GNUC__)
    __builtin___clear_cache((char *)mem, (char *)mem + size);
#endif
    *out_size = size;
    return mem;
}

int main(int argc, char **argv) {
    if (argc < 2) {
        usage(stderr);
        return 2;
    }

    const char *blob_path = NULL;
    unsigned collect_flags = 0;
    int verbose = 0;
    for (int i = 1; i < argc; i++) {
        if (strcmp(argv[i], "--help") == 0) {
            usage(stdout);
            return 0;
        } else if (strcmp(argv[i], "--system-only") == 0) {
            collect_flags |= TAILOR_PROFILE_SYSTEM_ONLY;
        } else if (strcmp(argv[i], "--raw-symbols") == 0) {
            collect_flags |= TAILOR_PROFILE_RAW_SYMBOL_NAMES;
        } else if (strcmp(argv[i], "--verbose") == 0) {
            verbose = 1;
        } else if (!blob_path) {
            blob_path = argv[i];
        } else {
            fprintf(stderr, "tailor-run: unexpected argument: %s\n", argv[i]);
            usage(stderr);
            return 2;
        }
    }
    if (!blob_path) {
        usage(stderr);
        return 2;
    }

    tailor_profile profile;
    tailor_profile_init(&profile);
    if (tailor_profile_collect(&profile, collect_flags) < 0) {
        fprintf(stderr, "tailor-run: %s\n", tailor_profile_last_error());
        return 1;
    }

    module_builder modules = {0};
    function_builder functions = {0};
    struct tinkr_context ctx;
    if (build_context_from_profile(&profile, &modules, &functions, &ctx) < 0) {
        tailor_profile_free(&profile);
        free(modules.items);
        free(functions.items);
        return 1;
    }
    if (verbose) {
        fprintf(stderr,
                "[tailor-run] context: %u modules, %u functions\n",
                ctx.module_count,
                ctx.function_count);
    }

    size_t blob_size = 0;
    void *blob = read_blob(blob_path, &blob_size);
    if (!blob) {
        tailor_profile_free(&profile);
        free(modules.items);
        free(functions.items);
        return 1;
    }

    int (*entry)(void *, void *, size_t) = (int (*)(void *, void *, size_t))blob;
    int rc = entry(NULL, &ctx, sizeof(ctx));
    fprintf(stderr, "[tailor-run] entry returned %d\n", rc);

    munmap(blob, blob_size);
    tailor_profile_free(&profile);
    free(modules.items);
    free(functions.items);
    return rc;
}

