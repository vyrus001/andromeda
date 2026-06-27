/* Linker script for SheLLVM-style PIC blobs.
 *
 * Concatenates .text and .rodata at VMA 0 into a single output section
 * named .blob so a single `llvm-objcopy -O binary --only-section=.blob`
 * extracts the whole loadable region. Relocations into .rodata (e.g.
 * x86_64's .rodata.cst16 for vector materialization of constants) are
 * resolved by the link, so the blob is self-contained.
 *
 * No entry symbol is exported; the blob's entry point is byte 0 of the
 * output, which is where SheLLVM places the (single, internalized)
 * entry function after `flatten`.
 */

ENTRY(0)

SECTIONS {
    . = 0;
    .blob : {
        *(.text)
        *(.text.*)
        . = ALIGN(8);
        *(.rodata)
        *(.rodata.*)
        *(.data.rel.ro)
        *(.data.rel.ro.*)
    }

    /DISCARD/ : {
        *(.eh_frame*)
        *(.note*)
        *(.comment)
        *(.ARM.*)
        *(.rela.*)
        *(.rel.*)
        *(.got)
        *(.got.plt)
        *(.plt)
        *(.dynamic)
        *(.dynsym)
        *(.dynstr)
        *(.hash)
        *(.gnu.hash)
    }
}
