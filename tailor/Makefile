ifeq ($(origin CC),default)
  CC := clang
endif
ifeq ($(origin CXX),default)
  CXX := clang++
endif
LLVM_AR ?= $(shell command -v llvm-ar 2>/dev/null || xcrun -find ar 2>/dev/null || command -v ar)
LLVM_RANLIB ?= $(shell command -v llvm-ranlib 2>/dev/null || xcrun -find ranlib 2>/dev/null || command -v ranlib)
AR := $(LLVM_AR)
RANLIB := $(LLVM_RANLIB)
CFLAGS ?= -O2 -g
CPPFLAGS += -Iinclude
WARNFLAGS ?= -Wall -Wextra -Wpedantic
TARGET ?=
BUILD_DIR ?= build
BIN_DIR ?= bin
LIB_DIR ?= lib

UNAME_S := $(shell uname -s)
ifneq ($(findstring windows,$(TARGET)),)
  TARGET_OS := Windows
else ifneq ($(findstring mingw,$(TARGET)),)
  TARGET_OS := Windows
else ifneq ($(findstring win32,$(TARGET)),)
  TARGET_OS := Windows
else ifneq ($(findstring apple,$(TARGET)),)
  TARGET_OS := Darwin
else ifneq ($(findstring darwin,$(TARGET)),)
  TARGET_OS := Darwin
else ifneq ($(findstring linux,$(TARGET)),)
  TARGET_OS := Linux
else
  TARGET_OS := $(UNAME_S)
endif

ifneq ($(TARGET),)
  TARGET_FLAGS := --target=$(TARGET)
endif

COMMON_OBJ := $(BUILD_DIR)/profile.o $(BUILD_DIR)/profile_io.o
CLI_OBJ := $(BUILD_DIR)/tailor_profile.o
RUN_OBJ := $(BUILD_DIR)/tailor_run.o
AUTO_OBJ := $(BUILD_DIR)/autoprofile.o
BYTECODE_SRC := src/bytecode_entry.c

ifeq ($(TARGET_OS),Darwin)
  PLATFORM_OBJ := $(BUILD_DIR)/profile_macho.o
  SHARED_EXT := dylib
  SHARED_FLAGS := -dynamiclib
else ifeq ($(TARGET_OS),Linux)
  PLATFORM_OBJ := $(BUILD_DIR)/profile_elf.o
  SHARED_EXT := so
  SHARED_FLAGS := -shared
  LDFLAGS += -ldl
else ifeq ($(TARGET_OS),Windows)
  PLATFORM_OBJ := $(BUILD_DIR)/profile_pe.o
  SHARED_EXT := dll
  SHARED_FLAGS := -shared
else
  PLATFORM_OBJ := $(BUILD_DIR)/profile_unsupported.o
  SHARED_EXT := so
  SHARED_FLAGS := -shared
endif

LIB_OBJ := $(COMMON_OBJ) $(PLATFORM_OBJ)

.PHONY: all clean test bytecode

all: $(BIN_DIR)/tailor-profile $(BIN_DIR)/tailor-run $(LIB_DIR)/libtailor_profile.a $(LIB_DIR)/libtailor_autoprofile.$(SHARED_EXT)

$(BUILD_DIR) $(BIN_DIR) $(LIB_DIR):
	mkdir -p $@

$(BUILD_DIR)/%.o: src/%.c include/tailor/profile.h | $(BUILD_DIR)
	$(CC) $(TARGET_FLAGS) $(CPPFLAGS) $(CFLAGS) $(WARNFLAGS) -std=c11 -fPIC -c $< -o $@

$(LIB_DIR)/libtailor_profile.a: $(LIB_OBJ) | $(LIB_DIR)
	$(AR) rcs $@ $(LIB_OBJ)
	$(RANLIB) $@

$(BIN_DIR)/tailor-profile: $(CLI_OBJ) $(LIB_DIR)/libtailor_profile.a | $(BIN_DIR)
	$(CC) $(TARGET_FLAGS) $(CFLAGS) $(CLI_OBJ) $(LIB_DIR)/libtailor_profile.a $(LDFLAGS) -o $@

$(BIN_DIR)/tailor-run: $(RUN_OBJ) $(LIB_DIR)/libtailor_profile.a | $(BIN_DIR)
	$(CC) $(TARGET_FLAGS) $(CFLAGS) $(RUN_OBJ) $(LIB_DIR)/libtailor_profile.a $(LDFLAGS) -o $@

$(LIB_DIR)/libtailor_autoprofile.$(SHARED_EXT): $(AUTO_OBJ) $(LIB_OBJ) | $(LIB_DIR)
	$(CC) $(TARGET_FLAGS) $(CFLAGS) $(SHARED_FLAGS) $(AUTO_OBJ) $(LIB_OBJ) $(LDFLAGS) -o $@

bytecode: | $(BIN_DIR)
	tools/llvm-build.sh bytecode $(BIN_DIR)/tailor-profile.bin $(TARGET)

test: $(BIN_DIR)/tailor-profile
	$(BIN_DIR)/tailor-profile --symbol write --format json >/dev/null
	$(BIN_DIR)/tailor-profile --symbol write --format tsv >/dev/null
	$(BIN_DIR)/tailor-profile --symbols tests/symbols.txt --format json >/dev/null

clean:
	rm -rf $(BUILD_DIR) $(BIN_DIR) $(LIB_DIR)
