/* Run a Windows x86_64 (win64-ABI) PIC blob from a Linux x86_64 host.
 *
 * Our PE blobs are SheLLVM-flattened position-independent code that
 * calls "Win32 APIs" exclusively through the seeds struct — no PE
 * imports, no actual Windows DLLs needed. So we don't need Wine or
 * the PE loader. What we DO need is to:
 *
 *  1. Provide win64-ABI-callable replacements for the kernel32
 *     functions the blob uses. We mark them with
 *     __attribute__((ms_abi)) so clang emits a win64 entry sequence
 *     (args in RCX/RDX/R8/R9 + 32-byte shadow space, win64
 *     callee-saved set).
 *
 *  2. Invoke the blob's entry point with the win64 ABI: declare the
 *     function-pointer type with ms_abi.
 *
 * Each wrapper translates win64 args to the equivalent Linux libc
 * call. Only the APIs our test blobs touch need to be wrapped —
 * unwrapped fields stay NULL and segfault on use (loud failure mode
 * for "the blob used something we haven't ported yet").
 *
 * Build inside the container:
 *   clang -O2 -I . -o tools/loader_pe_on_linux tools/loader_pe_on_linux.c
 *
 * Run:
 *   ./tools/loader_pe_on_linux blob.bin
 */
#define _GNU_SOURCE
#include <fcntl.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
#include <sys/stat.h>
#include <unistd.h>

#include "seeds.h"

#define MS_ABI __attribute__((ms_abi))

/* GetStdHandle: STD_INPUT_HANDLE=-10, STD_OUTPUT_HANDLE=-11, STD_ERROR_HANDLE=-12.
   Map those to POSIX fd 0/1/2 (cast as void*). */
static void * MS_ABI my_GetStdHandle(unsigned int nStdHandle) {
    switch ((int)nStdHandle) {
        case -10: return (void *)(long)0;
        case -11: return (void *)(long)1;
        case -12: return (void *)(long)2;
        default:  return (void *)(long)-1;  /* INVALID_HANDLE_VALUE */
    }
}

/* WriteFile: return BOOL (nonzero on success), set bytesWritten. */
static int MS_ABI my_WriteFile(void *hFile,
                               const void *lpBuffer,
                               unsigned int nBytes,
                               unsigned int *lpBytesWritten,
                               void *lpOverlapped) {
    (void)lpOverlapped;
    long n = write((int)(long)hFile, lpBuffer, nBytes);
    if (n < 0) {
        if (lpBytesWritten) *lpBytesWritten = 0;
        return 0;
    }
    if (lpBytesWritten) *lpBytesWritten = (unsigned int)n;
    return 1;
}

/* ReadFile: same shape. */
static int MS_ABI my_ReadFile(void *hFile,
                              void *lpBuffer,
                              unsigned int nBytes,
                              unsigned int *lpBytesRead,
                              void *lpOverlapped) {
    (void)lpOverlapped;
    long n = read((int)(long)hFile, lpBuffer, nBytes);
    if (n < 0) {
        if (lpBytesRead) *lpBytesRead = 0;
        return 0;
    }
    if (lpBytesRead) *lpBytesRead = (unsigned int)n;
    return 1;
}

static int MS_ABI my_CloseHandle(void *hObject) {
    int fd = (int)(long)hObject;
    if (fd <= 2) return 1;          /* don't close stdio fds */
    return close(fd) == 0 ? 1 : 0;
}

static void MS_ABI my_ExitProcess(unsigned int code) {
    exit((int)code);
}

int main(int argc, char **argv) {
    const char *path = argc > 1 ? argv[1] : "blob.bin";

    int fd = open(path, O_RDONLY);
    if (fd < 0) { perror("open"); return 1; }
    struct stat st;
    if (fstat(fd, &st) < 0) { perror("fstat"); return 1; }
    size_t sz = (size_t)st.st_size;

    void *mem = mmap(NULL, sz, PROT_READ | PROT_WRITE | PROT_EXEC,
                     MAP_PRIVATE | MAP_ANONYMOUS, -1, 0);
    if (mem == MAP_FAILED) { perror("mmap"); return 1; }
    if (read(fd, mem, sz) != (ssize_t)sz) { perror("read"); return 1; }
    close(fd);

    /* Cast away the ABI mismatch — seeds.h's kernel32 fields are
       plain function pointers (sysv64 when compiled in this TU),
       but at runtime the blob will call them with win64. Our wrappers
       above are win64 — the cast strips the ms_abi attribute from the
       type but the function itself remains win64 at runtime. */
    struct windows_kernel32 kernel32 = {
        .GetStdHandle = (void *(*)(unsigned int))my_GetStdHandle,
        .WriteFile    = (int  (*)(void *, const void *, unsigned int, unsigned int *, void *))my_WriteFile,
        .ReadFile     = (int  (*)(void *, void *, unsigned int, unsigned int *, void *))my_ReadFile,
        .CloseHandle  = (int  (*)(void *))my_CloseHandle,
        .ExitProcess  = (void (*)(unsigned int))my_ExitProcess,
        /* VirtualAlloc not wrapped; if the blob calls it we crash. */
    };
    struct seeds seeds = { .kernel32 = &kernel32 };

    int (* MS_ABI entry)(struct seeds *, void *, size_t) =
        (int (* MS_ABI)(struct seeds *, void *, size_t))mem;
    int rc = entry(&seeds, NULL, 0);
    fprintf(stderr, "[loader_pe_on_linux] entry returned %d\n", rc);
    return rc;
}
