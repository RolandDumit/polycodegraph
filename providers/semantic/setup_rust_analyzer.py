"""Install a pinned official rust-analyzer binary; no repository code is run."""

from __future__ import annotations

import gzip
import hashlib
import io
import json
import os
import platform
import sys
import urllib.request
import zipfile
from pathlib import Path

RELEASE = "2026-09-28"
DIGESTS = {
    "aarch64-apple-darwin.gz": "54ec873d8996e2c127d758bf45d4eacb6d3371dae4f6f6d5d3f05cedbae5fd59",
    "aarch64-pc-windows-msvc.zip": "f63c7fc9a00a7e863b21b5e0b77cda7ff61aaa9f6f83b0affa5bbb525be7c43c",
    "aarch64-unknown-linux-gnu.gz": "03bad9c3dabb0f07a2678d5f9f8f1575a3742ea141506e14b3a26b42a1f896f3",
    "x86_64-apple-darwin.gz": "d032c0eb75e4597cc8ffc35ea4cdbd9eecc8341936b6edac6749e679fc3f0682",
    "x86_64-pc-windows-msvc.zip": "ad78fb368525404c6ac09c4bba33e90797902ce1f5a17db0925c695cae096ccc",
    "x86_64-unknown-linux-gnu.gz": "23f711d86b5f826e22886f01d7355dc01e0f4c1357dafa29710a95b903b48c85",
}


def main() -> None:
    """Verify official compressed bytes and atomically install native tooling."""
    machine = platform.machine().lower()
    architecture = (
        "aarch64" if machine in {"arm64", "aarch64"} else "x86_64" if machine in {"amd64", "x86_64"} else machine
    )
    system = (
        "apple-darwin.gz"
        if sys.platform == "darwin"
        else "pc-windows-msvc.zip"
        if sys.platform == "win32"
        else "unknown-linux-gnu.gz"
    )
    target = f"{architecture}-{system}"
    if target not in DIGESTS:
        raise ValueError("No pinned binary for this host; set RUST_ANALYZER to your native installation")
    directory = Path(__file__).resolve().parent / ".tools"
    directory.mkdir(exist_ok=True)
    binary = directory / ("rust-analyzer.exe" if sys.platform == "win32" else "rust-analyzer")
    metadata = directory / "installed.json"
    if binary.is_file() and metadata.is_file():
        state = json.loads(metadata.read_text(encoding="utf-8"))
        if (
            state.get("release") == RELEASE
            and state.get("target") == target
            and state.get("sha256") == hashlib.sha256(binary.read_bytes()).hexdigest()
        ):
            print(f"rust-analyzer {RELEASE} already prepared")
            return
    url = f"https://github.com/rust-lang/rust-analyzer/releases/download/{RELEASE}/rust-analyzer-{target}"
    with urllib.request.urlopen(url, timeout=60) as response:
        compressed = response.read(128 * 1024 * 1024 + 1)
    if len(compressed) > 128 * 1024 * 1024 or hashlib.sha256(compressed).hexdigest() != DIGESTS[target]:
        raise ValueError("rust-analyzer release SHA-256 mismatch")
    if target.endswith(".zip"):
        with zipfile.ZipFile(io.BytesIO(compressed)) as archive:
            names = [name for name in archive.namelist() if name.rsplit("/", 1)[-1] == "rust-analyzer.exe"]
            if len(names) != 1:
                raise ValueError("Unexpected release archive")
            content = archive.read(names[0])
    else:
        content = gzip.decompress(compressed)
    temporary = directory / f"rust-analyzer.{os.getpid()}.tmp"
    temporary.write_bytes(content)
    temporary.chmod(0o755)
    temporary.replace(binary)
    metadata.write_text(
        json.dumps({"release": RELEASE, "target": target, "sha256": hashlib.sha256(content).hexdigest()}),
        encoding="utf-8",
    )
    print(f"Prepared rust-analyzer {RELEASE} ({target})")


if __name__ == "__main__":
    main()
