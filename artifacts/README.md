# Disk Test Payloads

## macos-say-smoke-arm64.bin

A benign arm64 macOS Tinkr bytecode blob that resolves `execve` through Tailor's runtime context and executes:

```text
/usr/bin/say "soldir disk payload smoke test"
```

Run it from the Andromeda root with:

```sh
./artifacts/run-macos-say-smoke.sh
```

Equivalent direct command:

```sh
./tailor/bin/tailor-run ./artifacts/macos-say-smoke-arm64.bin --verbose
```

The source used to build it is `artifacts/macos-say-smoke.c`.
