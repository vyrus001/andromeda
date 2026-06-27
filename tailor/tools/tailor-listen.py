#!/usr/bin/env python3
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import platform
import secrets
import socket
import struct
import subprocess
import sys
import tempfile
import time
import urllib.parse
import urllib.request
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def default_target_triple() -> str:
    system = platform.system().lower()
    machine = platform.machine().lower()
    if system == "darwin":
        if machine in {"arm64", "aarch64"}:
            return "arm64-apple-macos"
        if machine == "x86_64":
            return "x86_64-apple-macos"
    if system == "linux":
        if machine in {"arm64", "aarch64"}:
            return "aarch64-linux-gnu"
        if machine == "x86_64":
            return "x86_64-linux-gnu"
    return f"{machine}-{system}"


def platform_name() -> str:
    system = platform.system().lower()
    if system == "darwin":
        return "macos"
    return system or "unknown"


def collect_profile(tailor_profile: Path) -> dict:
    result = subprocess.run(
        [str(tailor_profile), "--system-only", "--format", "json"],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "tailor-profile failed")
    return json.loads(result.stdout)


def post_checkin(args: argparse.Namespace, profile_data: dict) -> str:
    instance_id = args.instance_id or socket.gethostname()
    payload = {
        "instance_id": instance_id,
        "hostname": socket.gethostname(),
        "os": platform_name(),
        "arch": platform.machine(),
        "target_triple": args.target_triple,
        "profile": profile_data,
        "metadata": {
            "kind": "tailor-listener",
            "pid": os.getpid(),
            "profile_entries": len(profile_data.get("entries", [])),
        },
    }
    url = urllib.parse.urljoin(args.soldir_url.rstrip("/") + "/", "api/checkins")
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"content-type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=args.http_timeout) as response:
        data = json.loads(response.read().decode("utf-8"))
    return data["tailor_ws_url"]


class SimpleWebSocket:
    def __init__(self, url: str, timeout: float = 30.0):
        self.url = url
        self.timeout = timeout
        self.sock: socket.socket | None = None

    def connect(self) -> None:
        parsed = urllib.parse.urlparse(self.url)
        if parsed.scheme != "ws":
            raise ValueError("tailor-listen only supports ws:// URLs")
        host = parsed.hostname or "127.0.0.1"
        port = parsed.port or 80
        path = parsed.path or "/"
        if parsed.query:
            path += "?" + parsed.query

        sock = socket.create_connection((host, port), timeout=self.timeout)
        key = base64.b64encode(secrets.token_bytes(16)).decode("ascii")
        request = (
            f"GET {path} HTTP/1.1\r\n"
            f"Host: {host}:{port}\r\n"
            "Upgrade: websocket\r\n"
            "Connection: Upgrade\r\n"
            f"Sec-WebSocket-Key: {key}\r\n"
            "Sec-WebSocket-Version: 13\r\n"
            "\r\n"
        )
        sock.sendall(request.encode("ascii"))
        header = self._recv_http_header(sock)
        if b" 101 " not in header.split(b"\r\n", 1)[0]:
            raise ConnectionError(header.decode("iso-8859-1", errors="replace"))
        self.sock = sock

    def close(self) -> None:
        if self.sock is not None:
            try:
                self.sock.close()
            finally:
                self.sock = None

    def recv_json(self) -> dict:
        while True:
            opcode, payload = self._recv_frame()
            if opcode == 0x1:
                return json.loads(payload.decode("utf-8"))
            if opcode == 0x8:
                raise ConnectionError("websocket closed")
            if opcode == 0x9:
                self._send_frame(0xA, payload)

    def send_json(self, payload: dict) -> None:
        self._send_frame(0x1, json.dumps(payload).encode("utf-8"))

    def _recv_http_header(self, sock: socket.socket) -> bytes:
        data = b""
        while b"\r\n\r\n" not in data:
            chunk = sock.recv(4096)
            if not chunk:
                break
            data += chunk
        return data

    def _read_exact(self, size: int) -> bytes:
        assert self.sock is not None
        data = b""
        while len(data) < size:
            chunk = self.sock.recv(size - len(data))
            if not chunk:
                raise ConnectionError("websocket closed")
            data += chunk
        return data

    def _recv_frame(self) -> tuple[int, bytes]:
        head = self._read_exact(2)
        opcode = head[0] & 0x0F
        masked = bool(head[1] & 0x80)
        length = head[1] & 0x7F
        if length == 126:
            length = struct.unpack("!H", self._read_exact(2))[0]
        elif length == 127:
            length = struct.unpack("!Q", self._read_exact(8))[0]
        mask = self._read_exact(4) if masked else b""
        payload = self._read_exact(length)
        if masked:
            payload = bytes(byte ^ mask[i % 4] for i, byte in enumerate(payload))
        return opcode, payload

    def _send_frame(self, opcode: int, payload: bytes) -> None:
        assert self.sock is not None
        mask = secrets.token_bytes(4)
        header = bytearray([0x80 | opcode])
        length = len(payload)
        if length < 126:
            header.append(0x80 | length)
        elif length <= 0xFFFF:
            header.append(0x80 | 126)
            header.extend(struct.pack("!H", length))
        else:
            header.append(0x80 | 127)
            header.extend(struct.pack("!Q", length))
        masked = bytes(byte ^ mask[i % 4] for i, byte in enumerate(payload))
        self.sock.sendall(bytes(header) + mask + masked)


def execute_bytecode(args: argparse.Namespace, message: dict) -> dict:
    job_id = str(message["job_id"])
    blob = base64.b64decode(message["bytecode_b64"])
    digest = hashlib.sha256(blob).hexdigest()
    args.work_dir.mkdir(parents=True, exist_ok=True)
    blob_path = args.work_dir / f"{job_id}.bin"
    blob_path.write_bytes(blob)

    cmd = [str(args.tailor_run), str(blob_path)]
    if args.verbose:
        cmd.append("--verbose")
    result = subprocess.run(cmd, capture_output=True, text=True, check=False)
    return {
        "type": "execution_result",
        "job_id": job_id,
        "returncode": result.returncode,
        "stdout": result.stdout,
        "stderr": result.stderr,
        "sha256": digest,
    }


def listen_once(args: argparse.Namespace) -> int:
    profile_data = collect_profile(args.tailor_profile)
    ws_url = post_checkin(args, profile_data)
    print(f"[tailor-listen] websocket {ws_url}", file=sys.stderr)
    ws = SimpleWebSocket(ws_url, timeout=args.http_timeout)
    ws.connect()
    try:
        while True:
            message = ws.recv_json()
            if args.verbose:
                print(f"[tailor-listen] <- {message.get('type')}", file=sys.stderr)
            if message.get("type") != "execute_bytecode":
                continue
            result = execute_bytecode(args, message)
            ws.send_json(result)
            if args.once:
                return int(result["returncode"])
    finally:
        ws.close()


def main() -> int:
    parser = argparse.ArgumentParser(description="Check in with Soldir and execute delivered Tinkr bytecode.")
    parser.add_argument("--soldir-url", default="http://127.0.0.1:8765")
    parser.add_argument("--instance-id")
    parser.add_argument("--target-triple", default=default_target_triple())
    parser.add_argument("--tailor-run", type=Path, default=ROOT / "bin" / "tailor-run")
    parser.add_argument("--tailor-profile", type=Path, default=ROOT / "bin" / "tailor-profile")
    parser.add_argument("--work-dir", type=Path, default=Path(tempfile.gettempdir()) / "tailor-listen")
    parser.add_argument("--http-timeout", type=float, default=30.0)
    parser.add_argument("--once", action="store_true", help="exit after executing one delivered bytecode job")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    while True:
        try:
            return listen_once(args)
        except KeyboardInterrupt:
            return 130
        except Exception as exc:
            print(f"[tailor-listen] {exc}", file=sys.stderr)
            if args.once:
                return 1
            time.sleep(2)


if __name__ == "__main__":
    raise SystemExit(main())
