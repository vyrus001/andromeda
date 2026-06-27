#ifndef TINKR_CONTEXT_H
#define TINKR_CONTEXT_H

typedef unsigned int tinkr_u32;
typedef unsigned long long tinkr_u64;

#define TINKR_CONTEXT_ABI_VERSION 1u
#define TINKR_CONTEXT_FUNCTION_EXPORT 1u

struct tinkr_context_module {
    tinkr_u64 module_hash;
    tinkr_u64 module_base;
};

struct tinkr_context_function {
    tinkr_u64 module_hash;
    tinkr_u64 function_hash;
    tinkr_u64 offset;
    tinkr_u32 module_index;
    tinkr_u32 flags;
};

struct tinkr_context {
    tinkr_u32 version;
    tinkr_u32 flags;
    tinkr_u32 module_count;
    tinkr_u32 function_count;
    tinkr_u64 modules_ptr;
    tinkr_u64 functions_ptr;
};

static inline void *tinkr_context_resolve(struct tinkr_context *ctx,
                                          tinkr_u64 module_hash,
                                          tinkr_u64 function_hash) {
    if (!ctx || ctx->version != TINKR_CONTEXT_ABI_VERSION ||
        !ctx->modules_ptr || !ctx->functions_ptr) {
        return (void *)0;
    }

    struct tinkr_context_module *modules =
        (struct tinkr_context_module *)(tinkr_u64)ctx->modules_ptr;
    struct tinkr_context_function *functions =
        (struct tinkr_context_function *)(tinkr_u64)ctx->functions_ptr;

    for (tinkr_u32 i = 0; i < ctx->function_count; i++) {
        struct tinkr_context_function *fn = &functions[i];
        if (fn->function_hash != function_hash) {
            continue;
        }
        if (module_hash != 0 && fn->module_hash != module_hash) {
            continue;
        }

        tinkr_u64 base = 0;
        if (fn->module_index < ctx->module_count &&
            modules[fn->module_index].module_hash == fn->module_hash) {
            base = modules[fn->module_index].module_base;
        } else {
            for (tinkr_u32 j = 0; j < ctx->module_count; j++) {
                if (modules[j].module_hash == fn->module_hash) {
                    base = modules[j].module_base;
                    break;
                }
            }
        }
        if (base) {
            return (void *)(tinkr_u64)(base + fn->offset);
        }
    }
    return (void *)0;
}

static inline void *tinkr_context_resolve_any(struct tinkr_context *ctx,
                                              tinkr_u64 function_hash) {
    return tinkr_context_resolve(ctx, 0, function_hash);
}

#endif
