#include "seeds.h"
#include "tinkr_context.h"

__attribute__((annotate("shellvm-main")))
int entry(struct seeds *s, void *args, size_t args_len) {
    (void)s;
    if (!args || args_len < sizeof(struct tinkr_context)) {
        return -1;
    }

    struct tinkr_context *ctx = (struct tinkr_context *)args;
    typedef long (*write_fn)(int, const void *, size_t);
    write_fn write_resolved =
        (write_fn)tinkr_context_resolve_any(ctx, 0xb93a12b0d06caefcULL);
    if (!write_resolved) {
        return -2;
    }

    const char msg[] = "context hi\n";
    long n = write_resolved(1, msg, sizeof(msg) - 1);
    return n == (long)(sizeof(msg) - 1) ? 0 : 1;
}

