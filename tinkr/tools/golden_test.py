#!/usr/bin/env python3
"""Golden test harness: prompt -> blob -> exec -> validate.

Runs from the host. For each test in agent/golden/<spec>.yaml:

  1. `docker compose run --rm agent --target=... -o <blob>` generates
     the blob from the prompt.
  2. `docker compose run --rm dev` builds the matching loader and
     executes the blob (qemu-user wrapper if target arch != host arch).
  3. Captures stdout and the loader process's exit code. Compares to
     expected.

Each test is a complete agent invocation, so first-run cache writes
get amortized across the suite via Anthropic's 5-minute prompt cache.

Usage:
  python3 tools/golden_test.py
  python3 tools/golden_test.py agent/golden/v1.yaml
  python3 tools/golden_test.py --filter syscall

Exit 0 if all pass, 1 otherwise.
"""
import argparse
import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


def load_yaml_via_container(path):
    """Host Python has no pyyaml; shell out to the agent container
    (which does) to parse the spec into JSON."""
    rel = Path(path).resolve().relative_to(REPO_ROOT)
    py = (
        "import yaml, json, sys; "
        f"print(json.dumps(yaml.safe_load(open('/work/{rel}').read())))"
    )
    r = subprocess.run(
        ["docker", "compose", "run", "--rm", "--entrypoint", "python3",
         "agent", "-c", py],
        capture_output=True, text=True, check=False,
    )
    if r.returncode != 0:
        sys.exit(f"yaml parse failed: {r.stderr}")
    # docker compose may prepend its own progress lines; find the JSON object.
    for line in r.stdout.splitlines():
        line = line.strip()
        if line.startswith("{"):
            return json.loads(line)
    sys.exit(f"no JSON in container output:\n{r.stdout}")

TARGET_TO_QEMU = {
    "x86_64-linux-gnu":     "qemu-x86_64-static",
    "aarch64-linux-gnu":    "qemu-aarch64-static",
    "arm-linux-gnueabihf":  "qemu-arm-static",
    "i686-linux-gnu":       "qemu-i386-static",
}

TARGET_TO_ARCH = {
    "x86_64-linux-gnu":     "x86_64",
    "aarch64-linux-gnu":    "aarch64",
    "arm-linux-gnueabihf":  "armv7l",
    "i686-linux-gnu":       "i686",
}


def host_container_arch():
    """The arch reported by `uname -m` inside the dev container."""
    r = subprocess.run(
        ["docker", "compose", "run", "--rm", "--entrypoint", "uname", "dev", "-m"],
        capture_output=True, text=True, check=False,
    )
    return r.stdout.strip()


def run_one(test, host_arch, debug=False):
    name = test["name"]
    prompt = test["prompt"]
    target = test.get("target", "")
    blob_path = f"golden_{name}.bin"

    # 1. Agent -> blob
    agent_cmd = [
        "docker", "compose", "run", "--rm", "agent",
        prompt,
        "-o", f"/work/{blob_path}",
    ]
    if target:
        agent_cmd += ["--target", target]
    if debug:
        print(f"  $ {' '.join(agent_cmd)}", file=sys.stderr)
    r = subprocess.run(agent_cmd, capture_output=True, text=True)
    if r.returncode != 0:
        return False, f"agent failed (exit {r.returncode}): {r.stderr.strip()[:400]}"

    # 2. Build loader + run blob (in dev container)
    target_arg = f' "{target}"' if target else ""
    if target and target in TARGET_TO_ARCH and TARGET_TO_ARCH[target] != host_arch:
        runner = TARGET_TO_QEMU[target] + " /tmp/loader"
    else:
        runner = "/tmp/loader"
    bash_script = (
        f"./tools/build-loader.sh /tmp/loader{target_arg} >/dev/null && "
        f"{runner} /work/{blob_path}; echo \"__exit=$?\""
    )
    run_cmd = ["docker", "compose", "run", "--rm", "dev", "bash", "-c", bash_script]
    if debug:
        print(f"  $ {' '.join(run_cmd)}", file=sys.stderr)
    r = subprocess.run(run_cmd, capture_output=True, text=True)

    stdout = r.stdout
    # Pull the loader's exit code out of the captured stdout.
    exit_code = None
    for line in stdout.splitlines():
        if line.startswith("__exit="):
            try:
                exit_code = int(line.split("=", 1)[1])
            except ValueError:
                pass
    # Strip the marker line + loader's own stderr line from what we compare.
    stdout_lines = [
        ln for ln in stdout.splitlines()
        if not ln.startswith("__exit=") and not ln.startswith("[loader]")
    ]
    stdout_clean = "\n".join(stdout_lines)

    expect_stdout = test.get("expect_stdout", "")
    expect_exit = test.get("expect_exit")

    if expect_stdout and expect_stdout not in stdout_clean:
        return False, (
            f"stdout missing {expect_stdout!r}; got:\n"
            f"{stdout_clean!r}\nstderr: {r.stderr.strip()[:200]}"
        )
    if expect_exit is not None and exit_code != expect_exit:
        return False, f"exit {exit_code}, expected {expect_exit}"

    return True, "ok"


def main():
    p = argparse.ArgumentParser()
    p.add_argument("spec", nargs="?", default="agent/golden/v1.yaml",
                   help="golden-test YAML spec (default: agent/golden/v1.yaml)")
    p.add_argument("--filter", help="substring filter on test name")
    p.add_argument("--debug", action="store_true", help="show docker commands")
    args = p.parse_args()

    spec_path = REPO_ROOT / args.spec
    if not spec_path.exists():
        sys.exit(f"spec not found: {spec_path}")
    spec = load_yaml_via_container(spec_path)
    tests = spec.get("tests", [])
    if args.filter:
        tests = [t for t in tests if args.filter in t["name"]]
    if not tests:
        sys.exit("no tests matched")

    host = host_container_arch()
    print(f"[golden] host arch (in dev container): {host}")
    print(f"[golden] running {len(tests)} test(s)\n")

    fails = []
    for i, test in enumerate(tests, 1):
        print(f"[{i}/{len(tests)}] {test['name']}", flush=True)
        ok, why = run_one(test, host, debug=args.debug)
        if ok:
            print(f"    PASS")
        else:
            print(f"    FAIL: {why}")
            fails.append(test["name"])
        print()

    print(f"[golden] {len(tests) - len(fails)}/{len(tests)} passed")
    if fails:
        print(f"[golden] FAILED: {', '.join(fails)}")
        sys.exit(1)


if __name__ == "__main__":
    main()
