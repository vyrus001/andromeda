ARG DEBIAN_FRONTEND=noninteractive

# ────────────────────────────────────────────────────────────────────
# Stage 1: build SheLLVM pass plugin against apt-installed LLVM 16.
# Mirrors SheLLVM's own canonical Dockerfile recipe.
# ────────────────────────────────────────────────────────────────────
FROM debian:bullseye-slim AS shellvm-builder

RUN apt-get update && apt-get install -y --no-install-recommends \
        ca-certificates wget gnupg2 software-properties-common \
        cmake git build-essential \
 && wget -qO- https://apt.llvm.org/llvm-snapshot.gpg.key \
        > /etc/apt/trusted.gpg.d/apt.llvm.org.asc \
 && add-apt-repository -y 'deb http://apt.llvm.org/bullseye/ llvm-toolchain-bullseye-16 main' \
 && apt-get update && apt-get install -y --no-install-recommends \
        libllvm16 llvm-16 llvm-16-dev llvm-16-runtime \
        clang-16 clang-tools-16 \
        libclang-common-16-dev libclang-16-dev libclang1-16 \
 && rm -rf /var/lib/apt/lists/*

RUN ln -sf /usr/bin/clang-16   /usr/bin/clang  \
 && ln -sf /usr/bin/clang++-16 /usr/bin/clang++ \
 && ln -sf /usr/bin/opt-16     /usr/bin/opt

ARG SHELLVM_REF=master
RUN git clone https://github.com/SheLLVM/SheLLVM.git /opt/SheLLVM \
 && cd /opt/SheLLVM && git checkout "${SHELLVM_REF}" \
 && mkdir build && cd build && cmake .. && make -j"$(nproc)"

# ────────────────────────────────────────────────────────────────────
# Stage 2: dev environment. Same apt-installed LLVM 16, plus the
# SheLLVM pass plugin copied from stage 1. Project source is mounted
# in at /work via docker-compose; nothing is COPYed at image-build
# time so iteration doesn't trigger rebuilds.
# ────────────────────────────────────────────────────────────────────
FROM debian:bullseye-slim AS dev

# Enable Debian multiarch for x86_64, aarch64, armhf, i386 so we can
# cross-build the test loader against each target's libc. SheLLVM itself
# only needs the (target-agnostic) LLVM bits, but the loader links libc.
RUN dpkg --add-architecture amd64 \
 && dpkg --add-architecture arm64 \
 && dpkg --add-architecture armhf \
 && dpkg --add-architecture i386 \
 && apt-get update && apt-get install -y --no-install-recommends \
        ca-certificates wget gnupg2 software-properties-common \
        make file binutils python3 \
        libc6-dev:amd64    libc6-dev:arm64    libc6-dev:armhf    libc6-dev:i386 \
        libgcc-10-dev:amd64 libgcc-10-dev:arm64 libgcc-10-dev:armhf libgcc-10-dev:i386 \
        qemu-user-static \
 && wget -qO- https://apt.llvm.org/llvm-snapshot.gpg.key \
        > /etc/apt/trusted.gpg.d/apt.llvm.org.asc \
 && add-apt-repository -y 'deb http://apt.llvm.org/bullseye/ llvm-toolchain-bullseye-16 main' \
 && apt-get update && apt-get install -y --no-install-recommends \
        libllvm16 llvm-16 llvm-16-runtime \
        clang-16 libclang1-16 lld-16 \
 && rm -rf /var/lib/apt/lists/*

RUN ln -sf /usr/bin/clang-16        /usr/bin/clang        \
 && ln -sf /usr/bin/clang++-16      /usr/bin/clang++      \
 && ln -sf /usr/bin/opt-16          /usr/bin/opt          \
 && ln -sf /usr/bin/llc-16          /usr/bin/llc          \
 && ln -sf /usr/bin/llvm-ar-16      /usr/bin/llvm-ar      \
 && ln -sf /usr/bin/llvm-ranlib-16  /usr/bin/llvm-ranlib  \
 && ln -sf /usr/bin/llvm-nm-16      /usr/bin/llvm-nm      \
 && ln -sf /usr/bin/llvm-readobj-16 /usr/bin/llvm-readobj \
 && ln -sf /usr/bin/llvm-objcopy-16 /usr/bin/llvm-objcopy \
 && ln -sf /usr/bin/llvm-objdump-16 /usr/bin/llvm-objdump \
 && ln -sf /usr/bin/ld.lld-16       /usr/bin/ld.lld       \
 && ln -sf /usr/bin/ld64.lld-16     /usr/bin/ld64.lld     \
 && ln -sf /usr/bin/lld-link-16     /usr/bin/lld-link     \
 && ln -sf /usr/bin/lld-16          /usr/bin/lld

COPY --from=shellvm-builder /opt/SheLLVM/build/llvm/shellvm.so /opt/shellvm/shellvm.so
ENV SHELLVM_SO=/opt/shellvm/shellvm.so
ENV CC=clang \
    CXX=clang++ \
    AR=llvm-ar \
    RANLIB=llvm-ranlib \
    NM=llvm-nm \
    OBJCOPY=llvm-objcopy \
    OBJDUMP=llvm-objdump \
    TAILOR_ROOT=/tailor

WORKDIR /work
CMD ["bash"]

# ────────────────────────────────────────────────────────────────────
# Stage 3: agent. Adds Python + anthropic SDK on top of dev.
# Invoked via docker-compose `agent` service.
# ────────────────────────────────────────────────────────────────────
FROM dev AS agent

RUN apt-get update && apt-get install -y --no-install-recommends \
        python3 python3-venv python3-pip \
 && rm -rf /var/lib/apt/lists/*

ENV VENV=/opt/tinkr-venv
RUN python3 -m venv "$VENV"
ENV PATH="$VENV/bin:$PATH"

COPY agent/requirements.txt /tmp/agent-requirements.txt
RUN pip install --no-cache-dir -r /tmp/agent-requirements.txt

WORKDIR /work
ENTRYPOINT ["python3", "/work/agent/agent.py"]
CMD ["--help"]
