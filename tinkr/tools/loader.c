#define _GNU_SOURCE
#include <dlfcn.h>
#include <fcntl.h>
#include <signal.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
#include <sys/socket.h>
#include <sys/stat.h>
#include <sys/time.h>
#include <sys/wait.h>
#include <time.h>
#include <unistd.h>

#include "seeds.h"

int main(int argc, char **argv) {
    const char *path = (argc > 1) ? argv[1] : "hello.bin";

    int fd = open(path, O_RDONLY);
    if (fd < 0) { perror("open"); return 1; }
    struct stat st;
    if (fstat(fd, &st) < 0) { perror("fstat"); return 1; }
    size_t sz = (size_t)st.st_size;

    void *mem = mmap(NULL, sz,
                     PROT_READ | PROT_WRITE | PROT_EXEC,
                     MAP_PRIVATE | MAP_ANONYMOUS, -1, 0);
    if (mem == MAP_FAILED) { perror("mmap"); return 1; }

    if (read(fd, mem, sz) != (ssize_t)sz) { perror("read"); return 1; }
    close(fd);

    /* Populate every linux_libc field the loader can plausibly provide.
       Fields the blob doesn't use stay set but unreferenced. The cast
       (int (*)(...))exit handles exit's void / _Noreturn return semantics. */
    struct linux_libc libc = {
        .write        = write,
        .read         = read,
        .open         = open,
        .close        = close,
        .dup2         = dup2,
        .lseek        = lseek,
        .fcntl        = fcntl,
        .stat         = stat,
        .fstat        = fstat,
        .unlink       = unlink,
        .mmap         = mmap,
        .munmap       = munmap,
        .mprotect     = mprotect,
        .fork         = fork,
        .execve       = execve,
        .waitpid      = waitpid,
        .getpid       = getpid,
        .kill         = kill,
        .socket       = socket,
        .bind         = bind,
        .listen       = listen,
        .accept       = accept,
        .connect      = connect,
        .send         = send,
        .recv         = recv,
        .dlopen       = dlopen,
        .dlsym        = dlsym,
        .dlclose      = dlclose,
        .exit         = exit,
        .sleep        = (unsigned int (*)(unsigned int))sleep,
        .time         = time,
        .gettimeofday = gettimeofday,
    };
    struct seeds seeds = { .libc = &libc };

    int (*entry)(struct seeds *, void *, size_t) =
        (int (*)(struct seeds *, void *, size_t))mem;
    int rc = entry(&seeds, NULL, 0);
    fprintf(stderr, "[loader] entry returned %d\n", rc);
    return rc;
}
