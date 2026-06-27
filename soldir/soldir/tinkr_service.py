from __future__ import annotations

import asyncio
import os
import shlex
import subprocess
import uuid
from dataclasses import dataclass
from pathlib import Path


SOLDIR_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_TINKR_ROOT = SOLDIR_ROOT.parent / "tinkr"


class TinkrBuildError(RuntimeError):
    pass


@dataclass(frozen=True)
class TinkrBuildArtifact:
    blob: bytes
    source: str
    source_path: Path
    blob_path: Path
    stderr: str
    stdout: str


def fnv1a64(text: str) -> int:
    value = 14695981039346656037
    for byte in text.encode("utf-8"):
        value ^= byte
        value = (value * 1099511628211) & 0xFFFFFFFFFFFFFFFF
    return value


def c_string_literal(value: str) -> str:
    encoded = value.encode("utf-8")
    out = ['"']
    for byte in encoded:
        if byte == 0x5C:
            out.append("\\\\")
        elif byte == 0x22:
            out.append('\\"')
        elif byte == 0x0A:
            out.append("\\n")
        elif byte == 0x0D:
            out.append("\\r")
        elif byte == 0x09:
            out.append("\\t")
        elif 0x20 <= byte <= 0x7E:
            out.append(chr(byte))
        else:
            out.append(f"\\x{byte:02x}")
    out.append('"')
    return "".join(out)


class TinkrService:
    def __init__(self) -> None:
        self.root = Path(os.getenv("TINKR_ROOT", DEFAULT_TINKR_ROOT)).resolve()
        self.work_dir = Path(os.getenv("SOLDIR_WORK_DIR", "/tmp/soldir-bytecode")).resolve()

    async def build_macos_say_blob(
        self,
        *,
        message: str,
        target_triple: str,
        job_id: str | None = None,
    ) -> TinkrBuildArtifact:
        return await asyncio.to_thread(
            self._build_macos_say_blob_sync,
            message=message,
            target_triple=target_triple,
            job_id=job_id,
        )

    def _build_macos_say_blob_sync(
        self,
        *,
        message: str,
        target_triple: str,
        job_id: str | None,
    ) -> TinkrBuildArtifact:
        build_script = self.root / "scripts" / "build-shellcode.sh"
        if not build_script.exists():
            raise TinkrBuildError(f"Tinkr build script not found: {build_script}")

        job_slug = job_id or uuid.uuid4().hex
        job_dir = self.work_dir / job_slug
        job_dir.mkdir(parents=True, exist_ok=True)
        source_path = job_dir / "macos-say-smoke.c"
        blob_path = job_dir / "macos-say-smoke.bin"
        source = self._macos_say_source(message)
        source_path.write_text(source)

        cmd = [str(build_script), str(source_path), str(blob_path), target_triple]
        result = subprocess.run(
            cmd,
            cwd=str(self.root),
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            quoted = " ".join(shlex.quote(part) for part in cmd)
            raise TinkrBuildError(
                f"Tinkr build failed ({result.returncode}): {quoted}\n{result.stderr}"
            )
        return TinkrBuildArtifact(
            blob=blob_path.read_bytes(),
            source=source,
            source_path=source_path,
            blob_path=blob_path,
            stderr=result.stderr,
            stdout=result.stdout,
        )

    def _macos_say_source(self, message: str) -> str:
        execve_hash = fnv1a64("execve")
        message_literal = c_string_literal(message)
        return f"""#include "seeds.h"
#include "tinkr_context.h"

__attribute__((annotate("shellvm-main")))
int entry(struct seeds *s, void *args, size_t args_len) {{
    (void)s;
    if (!args || args_len < sizeof(struct tinkr_context)) {{
        return -1;
    }}
    struct tinkr_context *ctx = (struct tinkr_context *)args;
    typedef int (*execve_fn)(const char *, char *const *, char *const *);
    execve_fn execve_resolved =
        (execve_fn)tinkr_context_resolve_any(ctx, 0x{execve_hash:016x}ULL);
    if (!execve_resolved) {{
        return -2;
    }}

    char path[] = "/usr/bin/say";
    char arg0[] = "say";
    char arg1[] = {message_literal};
    char *argv[] = {{ arg0, arg1, (char *)0 }};
    char *envp[] = {{ (char *)0 }};
    return execve_resolved(path, argv, envp);
}}
"""
