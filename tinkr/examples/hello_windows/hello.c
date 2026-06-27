#include "seeds.h"

__attribute__((annotate("shellvm-main")))
int entry(struct seeds *s, void *args, size_t args_len) {
    (void)args;
    (void)args_len;

    /* STD_OUTPUT_HANDLE = (DWORD)-11. */
    void *hOut = s->kernel32->GetStdHandle((unsigned int)-11);

    const char msg[] = "hello from windows pic blob\n";
    unsigned int written = 0;
    s->kernel32->WriteFile(hOut, msg, sizeof(msg) - 1, &written, 0);

    return 0;
}
