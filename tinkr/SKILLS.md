# tinkr skill catalog

Auto-generated from `skills/**/*.yaml`. Regenerate with
`tools/gen-skills-md.py`. The source-of-truth is the YAML files; this
file is for browsing.

**159 skills across 15 (platform, lib) groups.**

| Group | Lowering | Count |
| --- | --- | --- |
| `linux/libc` | indirect_call | 32 |
| `linux/syscall` | syscall | 7 |
| `macos/AppKit` | objc_msgsend | 5 |
| `macos/CoreFoundation` | indirect_call | 4 |
| `macos/Foundation` | indirect_call | 1 |
| `macos/Foundation` | objc_msgsend | 22 |
| `macos/Security` | indirect_call | 1 |
| `macos/bsd-syscall` | syscall | 8 |
| `macos/libSystem` | indirect_call | 27 |
| `macos/libobjc` | indirect_call | 3 |
| `macos/mach-trap` | syscall | 1 |
| `windows/advapi32` | indirect_call | 6 |
| `windows/kernel32` | indirect_call | 24 |
| `windows/ntdll` | indirect_call | 8 |
| `windows/ws2_32` | indirect_call | 10 |

## `linux/libc` — 32 indirect_call

| Function | Returns | Description |
| --- | --- | --- |
| [`accept`](skills/linux/libc/accept.yaml) | `int` | Accept a connection on a listening socket. Extracts the first pending |
| [`bind`](skills/linux/libc/bind.yaml) | `int` | Assign a local address to a socket. Typically used on a server socket |
| [`close`](skills/linux/libc/close.yaml) | `int` | Close a file descriptor. |
| [`connect`](skills/linux/libc/connect.yaml) | `int` | Initiate a connection on a socket. For connection-oriented sockets |
| [`dlclose`](skills/linux/libc/dlclose.yaml) | `int` | Decrement the reference count on a dynamically loaded shared object |
| [`dlopen`](skills/linux/libc/dlopen.yaml) | `void *` | Load a shared object (.so) into the process address space and return an |
| [`dlsym`](skills/linux/libc/dlsym.yaml) | `void *` | Resolve a symbol by name within a shared object handle returned by |
| [`dup2`](skills/linux/libc/dup2.yaml) | `int` | Make `newfd` refer to the same open file description as `oldfd`, |
| [`execve`](skills/linux/libc/execve.yaml) | `int` | Replace the current process image with a new program. On success |
| [`exit`](skills/linux/libc/exit.yaml) | `void` | Terminate the calling process via libc. Performs full C-runtime |
| [`fcntl`](skills/linux/libc/fcntl.yaml) | `int` | Perform one of a family of operations on a file descriptor: duplicate |
| [`fork`](skills/linux/libc/fork.yaml) | `int` | Create a new process by duplicating the calling process. The child is |
| [`fstat`](skills/linux/libc/fstat.yaml) | `int` | Retrieve file metadata for an open file descriptor. Fills a `struct stat` |
| [`getpid`](skills/linux/libc/getpid.yaml) | `int` | Return the process ID of the calling process. Always succeeds; the |
| [`gettimeofday`](skills/linux/libc/gettimeofday.yaml) | `int` | Get the current wall-clock time as seconds + microseconds since the |
| [`kill`](skills/linux/libc/kill.yaml) | `int` | Send a signal to a process or process group. With sig=0, performs |
| [`listen`](skills/linux/libc/listen.yaml) | `int` | Mark a socket referred to by `sockfd` as a passive socket — that is, |
| [`lseek`](skills/linux/libc/lseek.yaml) | `long long` | Reposition the read/write file offset of an open file descriptor. |
| [`mmap`](skills/linux/libc/mmap.yaml) | `void *` | Map files or anonymous memory into the process address space via libc. |
| [`mprotect`](skills/linux/libc/mprotect.yaml) | `int` | Change the access protections of a range of pages in the calling |
| [`munmap`](skills/linux/libc/munmap.yaml) | `int` | Unmap a region of memory previously established with mmap. After a |
| [`open`](skills/linux/libc/open.yaml) | `int` | Open a file. Returns a file descriptor on success. |
| [`read`](skills/linux/libc/read.yaml) | `long` | Read up to `count` bytes from file descriptor `fd` into `buf` via libc. |
| [`recv`](skills/linux/libc/recv.yaml) | `long` | Receive data from a connected socket. Equivalent to read(2) on a |
| [`send`](skills/linux/libc/send.yaml) | `long` | Send data on a connected socket. Equivalent to write(2) on the socket |
| [`sleep`](skills/linux/libc/sleep.yaml) | `unsigned int` | Suspend execution of the calling thread for at least `seconds` seconds. |
| [`socket`](skills/linux/libc/socket.yaml) | `int` | Create an endpoint for communication. Returns a file descriptor |
| [`stat`](skills/linux/libc/stat.yaml) | `int` | Retrieve file metadata for the file at `pathname`, following symbolic |
| [`time`](skills/linux/libc/time.yaml) | `long long` | Return the current calendar time as seconds since the Unix epoch |
| [`unlink`](skills/linux/libc/unlink.yaml) | `int` | Delete a name from the filesystem. If that name was the last link to |
| [`waitpid`](skills/linux/libc/waitpid.yaml) | `int` | Wait for state changes in a child process. Blocks (unless WNOHANG is |
| [`write`](skills/linux/libc/write.yaml) | `ssize_t` | Write up to `count` bytes from `buf` to file descriptor `fd` via libc. |

## `linux/syscall` — 7 syscall

| Function | Returns | Description |
| --- | --- | --- |
| [`close`](skills/linux/syscall/close.yaml) | `long` | Linux close(2) via direct syscall. Releases the file descriptor `fd` |
| [`exit`](skills/linux/syscall/exit.yaml) | `long` | Terminate the calling thread immediately via direct syscall, bypassing |
| [`mmap`](skills/linux/syscall/mmap.yaml) | `void *` | Map files or anonymous memory into the process address space via direct |
| [`mprotect`](skills/linux/syscall/mprotect.yaml) | `long` | Change protection on a range of pages in the calling process's virtual |
| [`openat`](skills/linux/syscall/openat.yaml) | `long` | Open a file relative to a directory file descriptor via direct Linux |
| [`read`](skills/linux/syscall/read.yaml) | `long` | Linux read(2) via direct syscall, bypassing libc. Reads up to `count` |
| [`write`](skills/linux/syscall/write.yaml) | `long` | Linux write(2) via direct syscall, bypassing libc. The blob carries no |

## `macos/AppKit` — 5 objc_msgsend

| Method | Returns | Description |
| --- | --- | --- |
| [`NSAlert.init`](skills/macos/AppKit/NSAlert_init.yaml) | `void *` | Initialize a freshly allocated NSAlert. Standard Objective-C designated |
| [`NSAlert.NSAlert_alloc`](skills/macos/AppKit/NSAlert_alloc.yaml) | `void *` | Allocate an uninitialized NSAlert instance. Equivalent to |
| [`NSAlert.runModal`](skills/macos/AppKit/NSAlert_runModal.yaml) | `long` | Display an application-modal alert and block until the user dismisses |
| [`NSAlert.setMessageText`](skills/macos/AppKit/NSAlert_setMessageText.yaml) | `void` | Set the primary message text of an NSAlert instance. Equivalent to |
| [`NSApplication.sharedApplication`](skills/macos/AppKit/NSApplication_sharedApplication.yaml) | `void *` | Return the NSApplication singleton, creating it on first invocation. |

## `macos/CoreFoundation` — 4 indirect_call

| Function | Returns | Description |
| --- | --- | --- |
| [`CFRelease`](skills/macos/CoreFoundation/CFRelease.yaml) | `void` | Decrement the reference count of a CoreFoundation object. When the |
| [`CFRetain`](skills/macos/CoreFoundation/CFRetain.yaml) | `const void *` | Increment the reference count of a Core Foundation object. Returns |
| [`CFShow`](skills/macos/CoreFoundation/CFShow.yaml) | `void` | Print the description of a Core Foundation object to stderr. Equivalent |
| [`CFStringCreateWithCString`](skills/macos/CoreFoundation/CFStringCreateWithCString.yaml) | `void *` | Create an immutable CFString from a null-terminated C string in the |

## `macos/Foundation` — 1 indirect_call

| Function | Returns | Description |
| --- | --- | --- |
| [`NSLog`](skills/macos/Foundation/NSLog.yaml) | `void` | Log a formatted message to stderr (and the unified logging system on |

## `macos/Foundation` — 22 objc_msgsend

| Method | Returns | Description |
| --- | --- | --- |
| [`NSAutoreleasePool.alloc`](skills/macos/Foundation/NSAutoreleasePool_alloc.yaml) | `void *` | Allocate an uninitialized NSAutoreleasePool instance. Equivalent to |
| [`NSAutoreleasePool.drain`](skills/macos/Foundation/NSAutoreleasePool_drain.yaml) | `void` | Drain an NSAutoreleasePool, sending release to every object that was |
| [`NSData.bytes`](skills/macos/Foundation/NSData_bytes.yaml) | `const void *` | Return a pointer to the receiver's underlying byte buffer. Equivalent |
| [`NSData.dataWithBytes`](skills/macos/Foundation/NSData_dataWithBytes.yaml) | `void *` | Construct an autoreleased NSData object holding a copy of `length` |
| [`NSData.length`](skills/macos/Foundation/NSData_length.yaml) | `unsigned long` | Return the number of bytes contained in the receiver NSData object. |
| [`NSDate.date`](skills/macos/Foundation/NSDate_date.yaml) | `void *` | Construct an autoreleased NSDate representing the current date and |
| [`NSDate.timeIntervalSince1970`](skills/macos/Foundation/NSDate_timeIntervalSince1970.yaml) | `double` | Return the number of seconds between the receiver NSDate and the UNIX |
| [`NSFileManager.defaultManager`](skills/macos/Foundation/NSFileManager_defaultManager.yaml) | `void *` | Return the shared NSFileManager singleton. Equivalent to: |
| [`NSFileManager.fileExistsAtPath`](skills/macos/Foundation/NSFileManager_fileExistsAtPath.yaml) | `signed char` | Test whether a file or directory exists at the given path. Equivalent |
| [`NSFileManager.removeItemAtPath_error`](skills/macos/Foundation/NSFileManager_removeItemAtPath_error.yaml) | `int` | Delete the file or directory at the given filesystem path. Equivalent to |
| [`NSMutableArray.addObject`](skills/macos/Foundation/NSMutableArray_addObject.yaml) | `void` | Append an object to the end of an NSMutableArray. Equivalent to: |
| [`NSMutableArray.array`](skills/macos/Foundation/NSMutableArray_array.yaml) | `void *` | Construct an empty, autoreleased NSMutableArray. Equivalent to |
| [`NSMutableArray.count`](skills/macos/Foundation/NSMutableArray_count.yaml) | `unsigned long` | Return the number of objects currently in the array. Equivalent to |
| [`NSProcessInfo.processInfo`](skills/macos/Foundation/NSProcessInfo_processInfo.yaml) | `void *` | Return the shared NSProcessInfo singleton for the current process. |
| [`NSString.alloc`](skills/macos/Foundation/NSString_alloc.yaml) | `void *` | Allocate an uninitialized NSString instance with retain count 1. |
| [`NSString.dataUsingEncoding`](skills/macos/Foundation/NSString_dataUsingEncoding.yaml) | `void *` | Encode an NSString's characters into an NSData blob using the given |
| [`NSString.initWithUTF8String`](skills/macos/Foundation/NSString_initWithUTF8String.yaml) | `void *` | Initialize a freshly-alloc'd NSString from a null-terminated UTF-8 C |
| [`NSString.length`](skills/macos/Foundation/NSString_length.yaml) | `unsigned long` | Return the number of UTF-16 code units in an NSString. Equivalent to: |
| [`NSString.stringWithUTF8String`](skills/macos/Foundation/NSString_stringWithUTF8String.yaml) | `void *` | Construct an autoreleased NSString from a null-terminated UTF-8 C |
| [`NSString.UTF8String`](skills/macos/Foundation/NSString_UTF8String.yaml) | `const char *` | Return a pointer to the NSString's contents as a null-terminated |
| [`NSURL.host`](skills/macos/Foundation/NSURL_host.yaml) | `void *` | Return the host component of an NSURL as an NSString, or nil if the |
| [`NSURL.URLWithString`](skills/macos/Foundation/NSURL_URLWithString.yaml) | `void *` | Construct an autoreleased NSURL from an NSString. Equivalent to |

## `macos/Security` — 1 indirect_call

| Function | Returns | Description |
| --- | --- | --- |
| [`SecRandomCopyBytes`](skills/macos/Security/SecRandomCopyBytes.yaml) | `int` | Fill a buffer with cryptographically secure random bytes via Apple's |

## `macos/bsd-syscall` — 8 syscall

| Function | Returns | Description |
| --- | --- | --- |
| [`close`](skills/macos/bsd-syscall/close.yaml) | `long` | Close a file descriptor via the BSD-class syscall directly, bypassing |
| [`exit`](skills/macos/bsd-syscall/exit.yaml) | `long` | Terminate the calling process with the given status via the BSD-class |
| [`lseek`](skills/macos/bsd-syscall/lseek.yaml) | `long long` | Reposition the read/write offset of an open file descriptor via the |
| [`mmap`](skills/macos/bsd-syscall/mmap.yaml) | `void *` | Map files or anonymous memory into the process address space via the |
| [`mprotect`](skills/macos/bsd-syscall/mprotect.yaml) | `long` | Change the protection on a region of the process's virtual address |
| [`open`](skills/macos/bsd-syscall/open.yaml) | `int` | Open or create a file via the BSD-class syscall directly, bypassing |
| [`read`](skills/macos/bsd-syscall/read.yaml) | `long` | Read up to `count` bytes from file descriptor `fd` into `buf` via the |
| [`write`](skills/macos/bsd-syscall/write.yaml) | `long` | Write up to `count` bytes from `buf` to file descriptor `fd` via the |

## `macos/libSystem` — 27 indirect_call

| Function | Returns | Description |
| --- | --- | --- |
| [`close`](skills/macos/libSystem/close.yaml) | `int` | Close a file descriptor via libSystem. |
| [`connect`](skills/macos/libSystem/connect.yaml) | `int` | Initiate a connection on a socket. For SOCK_STREAM sockets this |
| [`dlopen`](skills/macos/libSystem/dlopen.yaml) | `void *` | Load a dynamic library (Mach-O dylib or bundle) into the current |
| [`dlsym`](skills/macos/libSystem/dlsym.yaml) | `void *` | Look up the address of a symbol in a dynamic library handle obtained |
| [`dup2`](skills/macos/libSystem/dup2.yaml) | `int` | Duplicate `oldfd` onto `newfd` via libSystem. Useful for redirecting |
| [`execve`](skills/macos/libSystem/execve.yaml) | `int` | Replace the current process image with a new program. On success the |
| [`exit`](skills/macos/libSystem/exit.yaml) | `void` | Terminate the process cleanly, running atexit handlers and flushing |
| [`fcntl`](skills/macos/libSystem/fcntl.yaml) | `int` | Perform a control operation on an open file descriptor. fcntl is the |
| [`fork`](skills/macos/libSystem/fork.yaml) | `int` | Create a new process by duplicating the calling process. The child is |
| [`fstat`](skills/macos/libSystem/fstat.yaml) | `int` | Retrieve file metadata for an open file descriptor. Fills a `struct stat` |
| [`getpid`](skills/macos/libSystem/getpid.yaml) | `int` | Return the process ID of the calling process via libSystem. This call |
| [`gettimeofday`](skills/macos/libSystem/gettimeofday.yaml) | `int` | Get the current wall-clock time, expressed as seconds and microseconds |
| [`lseek`](skills/macos/libSystem/lseek.yaml) | `long long` | Reposition the read/write offset of an open file descriptor. Returns |
| [`mmap`](skills/macos/libSystem/mmap.yaml) | `void *` | Map files or anonymous memory into the process address space. |
| [`mprotect`](skills/macos/libSystem/mprotect.yaml) | `int` | Change protection on a region of mapped memory. |
| [`munmap`](skills/macos/libSystem/munmap.yaml) | `int` | Unmap a region of memory previously established with mmap. Removes |
| [`open`](skills/macos/libSystem/open.yaml) | `int` | Open a file via libSystem. Returns a file descriptor on success. |
| [`read`](skills/macos/libSystem/read.yaml) | `ssize_t` | Read up to `count` bytes from file descriptor `fd` into `buf` via libSystem. |
| [`recv`](skills/macos/libSystem/recv.yaml) | `long` | Receive data from a connected socket into `buf`, up to `len` bytes. |
| [`send`](skills/macos/libSystem/send.yaml) | `long` | Send data on a connected socket via libSystem. Equivalent to write(2) |
| [`sleep`](skills/macos/libSystem/sleep.yaml) | `unsigned int` | Suspend execution of the calling thread for at least `seconds` seconds. |
| [`socket`](skills/macos/libSystem/socket.yaml) | `int` | Create an endpoint for communication. Returns a file descriptor |
| [`stat`](skills/macos/libSystem/stat.yaml) | `int` | Retrieve file metadata for the file at `path`, following symbolic |
| [`time`](skills/macos/libSystem/time.yaml) | `long long` | Return the current calendar time as seconds since the Unix epoch |
| [`unlink`](skills/macos/libSystem/unlink.yaml) | `int` | Remove a directory entry. If the path refers to the last link to a |
| [`waitpid`](skills/macos/libSystem/waitpid.yaml) | `int` | Wait for state changes in a child process. Blocks (unless WNOHANG is |
| [`write`](skills/macos/libSystem/write.yaml) | `ssize_t` | Write up to `count` bytes from `buf` to file descriptor `fd`. libSystem |

## `macos/libobjc` — 3 indirect_call

| Function | Returns | Description |
| --- | --- | --- |
| [`objc_getClass`](skills/macos/libobjc/objc_getClass.yaml) | `void *` | Look up an Objective-C class object by its name. The returned pointer |
| [`objc_msgSend`](skills/macos/libobjc/objc_msgSend.yaml) | `void *` | Send an Objective-C message. Variadic in its raw form, but callers |
| [`sel_registerName`](skills/macos/libobjc/sel_registerName.yaml) | `void *` | Register or look up an Objective-C selector by its method name. The |

## `macos/mach-trap` — 1 syscall

| Function | Returns | Description |
| --- | --- | --- |
| [`task_self_trap`](skills/macos/mach-trap/task_self_trap.yaml) | `unsigned int` | Mach trap returning the task port (mach_port_name_t) for the current |

## `windows/advapi32` — 6 indirect_call

| Function | Returns | Description |
| --- | --- | --- |
| [`GetTokenInformation`](skills/windows/advapi32/GetTokenInformation.yaml) | `int` | Retrieve a specified type of information about an access token. The |
| [`OpenProcessToken`](skills/windows/advapi32/OpenProcessToken.yaml) | `int` | Open the access token associated with a process. The returned token |
| [`RegCloseKey`](skills/windows/advapi32/RegCloseKey.yaml) | `int` | Close a handle to an open registry key previously obtained from |
| [`RegOpenKeyExA`](skills/windows/advapi32/RegOpenKeyExA.yaml) | `int` | Open an existing registry key by ANSI name. Returns a handle in |
| [`RegQueryValueExA`](skills/windows/advapi32/RegQueryValueExA.yaml) | `int` | Retrieve the type and data of a named value under an open registry |
| [`RegSetValueExA`](skills/windows/advapi32/RegSetValueExA.yaml) | `int` | Set the data and type of a specified value under a registry key. The |

## `windows/kernel32` — 24 indirect_call

| Function | Returns | Description |
| --- | --- | --- |
| [`CloseHandle`](skills/windows/kernel32/CloseHandle.yaml) | `int` | Close an open object handle (file, pipe, mutex, event, process, |
| [`CreateFileW`](skills/windows/kernel32/CreateFileW.yaml) | `void *` | Create or open a file, pipe, console, etc. The "W" suffix takes a |
| [`CreateProcessW`](skills/windows/kernel32/CreateProcessW.yaml) | `int` | Create a new process and its primary thread. The "W" suffix takes |
| [`CreateThread`](skills/windows/kernel32/CreateThread.yaml) | `void *` | Create a new thread within the calling process. The thread begins |
| [`ExitProcess`](skills/windows/kernel32/ExitProcess.yaml) | `void` | Terminate the calling process and all its threads with the given exit |
| [`GetCurrentProcess`](skills/windows/kernel32/GetCurrentProcess.yaml) | `void *` | Return a pseudo-handle for the current process. The pseudo-handle is |
| [`GetCurrentThread`](skills/windows/kernel32/GetCurrentThread.yaml) | `void *` | Return a pseudo-handle for the calling thread. The pseudo-handle is a |
| [`GetLastError`](skills/windows/kernel32/GetLastError.yaml) | `unsigned int` | Retrieve the calling thread's last-error code. Most Win32 APIs that |
| [`GetProcAddress`](skills/windows/kernel32/GetProcAddress.yaml) | `void *` | Return the address of an exported function or variable in a loaded |
| [`GetProcessHeap`](skills/windows/kernel32/GetProcessHeap.yaml) | `void *` | Retrieve a handle to the default heap of the calling process. This |
| [`GetStdHandle`](skills/windows/kernel32/GetStdHandle.yaml) | `void *` | Return a handle to the requested standard device (stdin / stdout / |
| [`GetTickCount64`](skills/windows/kernel32/GetTickCount64.yaml) | `unsigned long long` | Return the number of milliseconds elapsed since the system was started, |
| [`HeapAlloc`](skills/windows/kernel32/HeapAlloc.yaml) | `void *` | Allocate a block of memory from a heap. The returned pointer is |
| [`HeapFree`](skills/windows/kernel32/HeapFree.yaml) | `int` | Free a memory block previously allocated by HeapAlloc or HeapReAlloc |
| [`LoadLibraryA`](skills/windows/kernel32/LoadLibraryA.yaml) | `void *` | Load the named DLL into the process, returning a module handle |
| [`ReadFile`](skills/windows/kernel32/ReadFile.yaml) | `int` | Read data from a file, pipe, or console handle. Synchronous when |
| [`SetFilePointer`](skills/windows/kernel32/SetFilePointer.yaml) | `unsigned int` | Move the file pointer of an open file handle. Returns the new low-order |
| [`Sleep`](skills/windows/kernel32/Sleep.yaml) | `void` | Suspend the current thread for at least the specified number of |
| [`TerminateProcess`](skills/windows/kernel32/TerminateProcess.yaml) | `int` | Terminate the specified process and all of its threads immediately. |
| [`VirtualAlloc`](skills/windows/kernel32/VirtualAlloc.yaml) | `void *` | Reserve and/or commit a region of pages in the calling process's |
| [`VirtualFree`](skills/windows/kernel32/VirtualFree.yaml) | `int` | Release, decommit, or release-and-decommit a region of pages in the |
| [`VirtualProtect`](skills/windows/kernel32/VirtualProtect.yaml) | `int` | Change the protection on a region of committed pages in the calling |
| [`WaitForSingleObject`](skills/windows/kernel32/WaitForSingleObject.yaml) | `unsigned int` | Wait until the specified object is in the signaled state or the timeout |
| [`WriteFile`](skills/windows/kernel32/WriteFile.yaml) | `int` | Write data to a file, pipe, or console handle. The synchronous form |

## `windows/ntdll` — 8 indirect_call

| Function | Returns | Description |
| --- | --- | --- |
| [`NtAllocateVirtualMemory`](skills/windows/ntdll/NtAllocateVirtualMemory.yaml) | `int` | Native API counterpart to VirtualAlloc. Allocates pages of memory in |
| [`NtClose`](skills/windows/ntdll/NtClose.yaml) | `int` | Native API counterpart to CloseHandle. Closes a kernel handle. |
| [`NtCreateFile`](skills/windows/ntdll/NtCreateFile.yaml) | `int` | Native API for creating or opening a file, directory, device, or |
| [`NtProtectVirtualMemory`](skills/windows/ntdll/NtProtectVirtualMemory.yaml) | `int` | Native API counterpart to VirtualProtect. Changes protection on a |
| [`NtReadFile`](skills/windows/ntdll/NtReadFile.yaml) | `int` | Native API counterpart to ReadFile. Reads data from an open file |
| [`NtTerminateProcess`](skills/windows/ntdll/NtTerminateProcess.yaml) | `int` | Native API to terminate a process. Lower-level counterpart to |
| [`NtWaitForSingleObject`](skills/windows/ntdll/NtWaitForSingleObject.yaml) | `int` | Native API wait primitive. Blocks the calling thread until the |
| [`NtWriteFile`](skills/windows/ntdll/NtWriteFile.yaml) | `int` | Native API counterpart to WriteFile. Writes data to an open file |

## `windows/ws2_32` — 10 indirect_call

| Function | Returns | Description |
| --- | --- | --- |
| [`accept`](skills/windows/ws2_32/accept.yaml) | `void *` | Accept an incoming connection on a listening socket. Returns a new |
| [`bind`](skills/windows/ws2_32/bind.yaml) | `int` | Associate a local address with a socket. Typically called on a server |
| [`closesocket`](skills/windows/ws2_32/closesocket.yaml) | `int` | Close a socket handle obtained from socket(), WSASocket(), accept(), |
| [`connect`](skills/windows/ws2_32/connect.yaml) | `int` | Establish a connection on a socket to the address specified by `name`. |
| [`listen`](skills/windows/ws2_32/listen.yaml) | `int` | Place a connection-mode socket into the listening state, ready to |
| [`recv`](skills/windows/ws2_32/recv.yaml) | `int` | Receive data from a connected socket (or a bound connectionless socket). |
| [`send`](skills/windows/ws2_32/send.yaml) | `int` | Send data on a connected socket. Blocks (by default) until the data is |
| [`socket`](skills/windows/ws2_32/socket.yaml) | `void *` | Create a Winsock socket descriptor. Returns a SOCKET handle bound to |
| [`WSACleanup`](skills/windows/ws2_32/WSACleanup.yaml) | `int` | Terminate use of the Winsock 2 DLL by the calling process. Each |
| [`WSAStartup`](skills/windows/ws2_32/WSAStartup.yaml) | `int` | Initiate use of the Winsock DLL by the calling process. Must be called |
