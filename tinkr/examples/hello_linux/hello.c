#include "seeds.h"

__attribute__((annotate("shellvm-main")))
int entry(struct seeds *s, void *args, size_t args_len) {
    (void)args;
    (void)args_len;
    const char msg[] = "hello from PIC blob\n";
    s->libc->write(1, msg, sizeof(msg) - 1);
    return 0;
}
