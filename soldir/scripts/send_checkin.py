#!/usr/bin/env python3
from __future__ import annotations

import json
import socket
import sys
import urllib.request


def main() -> int:
    url = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8765/api/checkins"
    hostname = socket.gethostname()
    payload = {
        "instance_id": hostname,
        "hostname": hostname,
        "os": sys.platform,
        "arch": "unknown",
        "ip_addresses": [],
        "metadata": {"source": "scripts/send_checkin.py"},
    }
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"content-type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=10) as response:
        print(response.read().decode("utf-8"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

