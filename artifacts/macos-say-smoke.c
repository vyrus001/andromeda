#include "seeds.h"
#include "tinkr_context.h"

__attribute__((annotate("shellvm-main")))
int entry(struct seeds *s, void *args, size_t args_len) {
    (void)s;
    if (!args || args_len < sizeof(struct tinkr_context)) {
        return -1;
    }
    struct tinkr_context *ctx = (struct tinkr_context *)args;
    typedef int (*execve_fn)(const char *, char *const *, char *const *);
    execve_fn execve_resolved =
        (execve_fn)tinkr_context_resolve_any(ctx, 0xa5af7239211ddc41ULL);
    if (!execve_resolved) {
        return -2;
    }

    char path[] = "/usr/bin/say";
    char arg0[] = "say";
    char arg1[] = "soldir disk payload smoke test";
    char *argv[] = { arg0, arg1, (char *)0 };
    char *envp[] = { (char *)0 };
    return execve_resolved(path, argv, envp);
}
