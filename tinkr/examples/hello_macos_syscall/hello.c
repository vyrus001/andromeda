#include "seeds.h"

#if defined(__aarch64__)
static long sys_write(int fd, const void *buf, unsigned long n) {
    register long x0  __asm__("x0")  = (long)fd;
    register long x1  __asm__("x1")  = (long)buf;
    register long x2  __asm__("x2")  = (long)n;
    register long x16 __asm__("x16") = 4;   /* SYS_write */
    __asm__ volatile (
        "svc #0x80\n\t"
        "b.cc 1f\n\t"
        "neg x0, x0\n"
        "1:"
        : "+r"(x0)
        : "r"(x1), "r"(x2), "r"(x16)
        : "cc", "memory"
    );
    return x0;
}
#elif defined(__x86_64__)
static long sys_write(int fd, const void *buf, unsigned long n) {
    long ret;
    __asm__ volatile (
        "syscall\n\t"
        "jnc 1f\n\t"
        "negq %%rax\n"
        "1:"
        : "=a"(ret)
        : "0"((long)0x2000004),
          "D"((long)fd), "S"(buf), "d"(n)
        : "rcx", "r11", "cc", "memory"
    );
    return ret;
}
#else
# error "unsupported macos arch"
#endif

__attribute__((annotate("shellvm-main")))
int entry(struct seeds *s, void *args, size_t args_len) {
    (void)s; (void)args; (void)args_len;
    const char msg[] = "hello from macos bsd-syscall\n";
    sys_write(1, msg, sizeof(msg) - 1);
    return 0;
}
