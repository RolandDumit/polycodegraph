"""Build the frozen 0.6 Rust core for native intent compatibility checks."""

from __future__ import annotations
import hashlib
import io
import os
from pathlib import Path
import subprocess
import tarfile

BASE = "fff953388d089ae89ab0b260fec05a8326c02b69"
root = Path(__file__).resolve().parent.parent
actual = subprocess.check_output(
    ["git", "rev-parse", "v0.6.0^{commit}"], cwd=root, text=True
).strip()
assert actual == BASE, "Unexpected 0.6 baseline tag"
archive = subprocess.check_output(["git", "archive", BASE], cwd=root)
destination = root / "work/intent-baseline-source"
destination.mkdir(parents=True, exist_ok=True)
with tarfile.open(fileobj=io.BytesIO(archive)) as tar:
    tar.extractall(destination, filter="data")
env = dict(os.environ, CARGO_TARGET_DIR=str(root / "work/intent-baseline-target"))
subprocess.run(
    [
        "cargo",
        "build",
        "--manifest-path",
        str(destination / "Cargo.toml"),
        "--release",
        "--locked",
        "-p",
        "polycodegraph",
    ],
    cwd=destination,
    env=env,
    check=True,
)
binary = (
    root
    / "work/intent-baseline-target/release"
    / ("polycodegraph.exe" if os.name == "nt" else "polycodegraph")
)
print(
    f"Baseline {BASE}, binary SHA-256 {hashlib.sha256(binary.read_bytes()).hexdigest()}"
)
