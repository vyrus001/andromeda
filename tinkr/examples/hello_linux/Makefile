.PHONY: all run clean

all: hello.bin loader

hello.bin: hello.c ../../seeds.h ../../scripts/build-shellcode.sh
	../../scripts/build-shellcode.sh hello.c hello.bin

loader: ../../tools/loader.c ../../seeds.h ../../tools/build-loader.sh
	../../tools/build-loader.sh loader

run: all
	./loader hello.bin

clean:
	rm -f hello.bin loader
