/* macOS test loader for SheLLVM-style PIC blobs.
 *
 * Differs from tools/loader.c (Linux):
 *  - Apple Silicon enforces W^X at the page level: pages cannot be
 *    simultaneously writable AND executable, so we mmap RW, copy the
 *    blob in, then mprotect to RX before jumping.
 *  - Explicit instruction-cache flush after the mprotect (libkern's
 *    sys_icache_invalidate) since arm64's I-cache and D-cache aren't
 *    coherent on Apple Silicon by default.
 *  - Populates the macos_libsystem seed sub-struct with the real
 *    libSystem functions, so blobs using lowering: indirect_call work
 *    too (in addition to syscall-style blobs that ignore the seed).
 *
 * Build on the Mac host:
 *   clang -O2 -I . -o tools/loader_macos tools/loader_macos.c
 * Run:
 *   ./tools/loader_macos blob.bin
 */
#define _DARWIN_C_SOURCE
#include <dlfcn.h>
#include <fcntl.h>
#include <libkern/OSCacheControl.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
#include <sys/stat.h>
#include <unistd.h>

#include "seeds.h"

/* dlopen wrapper that prints a clear message + bails on failure.
   These libraries should always be loadable on a macOS host. */
static void *dl_open_or_die(const char *path) {
    void *h = dlopen(path, RTLD_NOW);
    if (!h) {
        fprintf(stderr, "[loader_macos] dlopen(%s) failed: %s\n", path, dlerror());
        exit(2);
    }
    return h;
}

static void *dl_sym_or_die(void *h, const char *sym) {
    dlerror();  /* clear */
    void *p = dlsym(h, sym);
    const char *err = dlerror();
    if (err) {
        fprintf(stderr, "[loader_macos] dlsym(%s) failed: %s\n", sym, err);
        exit(2);
    }
    return p;
}

int main(int argc, char **argv) {
    const char *path = (argc > 1) ? argv[1] : "blob.bin";

    int fd = open(path, O_RDONLY);
    if (fd < 0) { perror("open"); return 1; }
    struct stat st;
    if (fstat(fd, &st) < 0) { perror("fstat"); return 1; }
    size_t sz = (size_t)st.st_size;

    /* mmap RW (no PROT_EXEC yet — Apple Silicon forbids RWX). */
    void *mem = mmap(NULL, sz, PROT_READ | PROT_WRITE,
                     MAP_PRIVATE | MAP_ANON, -1, 0);
    if (mem == MAP_FAILED) { perror("mmap"); return 1; }

    if (read(fd, mem, sz) != (ssize_t)sz) { perror("read"); return 1; }
    close(fd);

    /* Flip to RX and invalidate I-cache so the freshly-written bytes
       become executable. */
    if (mprotect(mem, sz, PROT_READ | PROT_EXEC) < 0) {
        perror("mprotect"); return 1;
    }
    sys_icache_invalidate(mem, sz);

    struct macos_libsystem libsystem = {
        .write    = write,
        .read     = read,
        .exit     = exit,
        .mmap     = mmap,
        .mprotect = mprotect,
    };

    /* libobjc.A.dylib is always loaded on macOS, but dlopen it
       explicitly to get a handle for dlsym. */
    void *libobjc_h = dl_open_or_die("/usr/lib/libobjc.A.dylib");
    struct macos_libobjc libobjc = {
        .objc_getClass    = dl_sym_or_die(libobjc_h, "objc_getClass"),
        .sel_registerName = dl_sym_or_die(libobjc_h, "sel_registerName"),
        .objc_msgSend     = dl_sym_or_die(libobjc_h, "objc_msgSend"),
    };

    void *foundation_h = dl_open_or_die(
        "/System/Library/Frameworks/Foundation.framework/Foundation");
    struct macos_foundation foundation = {
        .NSLog = dl_sym_or_die(foundation_h, "NSLog"),
    };

    struct seeds seeds = {
        .libsystem  = &libsystem,
        .libobjc    = &libobjc,
        .foundation = &foundation,
    };

    int (*entry)(struct seeds *, void *, size_t) =
        (int (*)(struct seeds *, void *, size_t))mem;
    int rc = entry(&seeds, NULL, 0);
    fprintf(stderr, "[loader_macos] entry returned %d\n", rc);
    return rc;
}
