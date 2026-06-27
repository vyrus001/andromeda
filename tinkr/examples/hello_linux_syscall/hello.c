#include "seeds.h"

#if defined(__aarch64__)
static long sys_write(int fd, const void *buf, unsigned long n) {
    register long x0 __asm__("x0") = (long)fd;
    register long x1 __asm__("x1") = (long)buf;
    register long x2 __asm__("x2") = (long)n;
    register long x8 __asm__("x8") = 64; /* __NR_write on arm64 */
    __asm__ volatile ("svc #0"
                      : "+r"(x0)
                      : "r"(x1), "r"(x2), "r"(x8)
                      : "memory");
    return x0;
}
#elif defined(__x86_64__)
static long sys_write(int fd, const void *buf, unsigned long n) {
    long ret;
    __asm__ volatile ("syscall"
                      : "=a"(ret)
                      : "0"((long)1), /* __NR_write on x86_64 */
                        "D"((long)fd), "S"(buf), "d"(n)
                      : "rcx", "r11", "memory");
    return ret;
}
#elif defined(__arm__)
static long sys_write(int fd, const void *buf, unsigned long n) {
    register long r0 __asm__("r0") = (long)fd;
    register long r1 __asm__("r1") = (long)buf;
    register long r2 __asm__("r2") = (long)n;
    register long r7 __asm__("r7") = 4; /* __NR_write on arm EABI */
    __asm__ volatile ("svc #0"
                      : "+r"(r0)
                      : "r"(r1), "r"(r2), "r"(r7)
                      : "memory");
    return r0;
}
#elif defined(__i386__)
static long sys_write(int fd, const void *buf, unsigned long n) {
    long ret;
    __asm__ volatile ("int $0x80"
                      : "=a"(ret)
                      : "0"((long)4), /* __NR_write on i386 */
                        "b"(fd), "c"(buf), "d"(n)
                      : "memory");
    return ret;
}
#else
# error "unsupported architecture for syscall example"
#endif

__attribute__((annotate("shellvm-main")))
int entry(struct seeds *s, void *args, size_t args_len) {
    (void)s;
    (void)args;
    (void)args_len;
    const char msg[] = "hello from syscall blob\n";
    sys_write(1, msg, sizeof(msg) - 1);
    return 0;
}
