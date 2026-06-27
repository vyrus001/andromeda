#ifndef TAILOR_BYTECODE_H
#define TAILOR_BYTECODE_H

/* Fixed-width ABI types without depending on target SDK headers. */
typedef unsigned char tailor_u8;
typedef unsigned short tailor_u16;
typedef unsigned int tailor_u32;
typedef unsigned long long tailor_u64;
typedef signed int tailor_i32;

#define TAILOR_BYTECODE_ABI_VERSION 1u

#define TAILOR_IMAGE_FORMAT_AUTO 0u
#define TAILOR_IMAGE_FORMAT_ELF 1u
#define TAILOR_IMAGE_FORMAT_MACHO 2u
#define TAILOR_IMAGE_FORMAT_PE 3u

#define TAILOR_ENTRY_FLAG_EXPORT 1u
#define TAILOR_ENTRY_FLAG_SYMBOL_TABLE 2u
#define TAILOR_ENTRY_FLAG_OVERFLOW 0x80000000u

struct tailor_image_view {
    tailor_u64 image_base;
    tailor_u64 image_size;
    tailor_u64 path_ptr;
    tailor_u32 path_len;
    tailor_u32 format;
};

struct tailor_manifest_entry {
    tailor_u64 module_hash;
    tailor_u64 function_hash;
    tailor_u64 offset;
    tailor_u64 address;
    tailor_u32 module_index;
    tailor_u32 flags;
};

struct tailor_bytecode_args {
    tailor_u32 version;
    tailor_u32 flags;
    tailor_u32 image_count;
    tailor_u32 entry_capacity;
    tailor_u64 images_ptr;
    tailor_u64 entries_ptr;
    tailor_u64 entry_count_ptr;
};

#endif

