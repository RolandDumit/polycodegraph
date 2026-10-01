"""Prepare the pinned Kotlin compiler and build PolyCodeGraph's trusted plugin."""

from __future__ import annotations

import hashlib
import io
import json
import os
import subprocess
import sys
import urllib.request
import zipfile
from pathlib import Path

VERSION = "2.3.10"
DIGEST = "c8d546f9ff433b529fb0ad43feceb39831040cae2ca8d17e7df46364368c9a9e"


def main() -> None:
    """Never run project Gradle, compiler plugins or downloaded shell launchers."""
    directory = Path(__file__).resolve().parent.parent / "kotlin"
    destination = directory / ".tools"
    libraries = destination / "kotlinc" / "lib"
    libraries.mkdir(parents=True, exist_ok=True)
    metadata = destination / "installed.json"
    source = directory / "GraphPlugin.kt"
    source_hash = hashlib.sha256(source.read_bytes()).hexdigest()
    if not metadata.exists() or json.loads(metadata.read_text(encoding="utf-8")).get("version") != VERSION:
        url = f"https://github.com/JetBrains/kotlin/releases/download/v{VERSION}/kotlin-compiler-{VERSION}.zip"
        with urllib.request.urlopen(url, timeout=60) as response:
            data = response.read(128 * 1024 * 1024 + 1)
        if len(data) > 128 * 1024 * 1024 or hashlib.sha256(data).hexdigest() != DIGEST:
            raise ValueError("Kotlin distribution SHA-256 mismatch")
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            for item in archive.infolist():
                if item.filename.startswith("kotlinc/lib/") and item.filename.endswith(".jar"):
                    if (
                        item.file_size > 128 * 1024 * 1024
                        or Path(item.filename).name != item.filename[len("kotlinc/lib/") :]
                    ):
                        raise ValueError("Unexpected Kotlin archive entry")
                    (libraries / Path(item.filename).name).write_bytes(archive.read(item))
    plugin = destination / "graph-plugin.jar"
    java = sys.argv[1] if len(sys.argv) == 2 else "java"
    subprocess.run(
        [
            java,
            "-Dfile.encoding=UTF-8",
            "-cp",
            str(libraries / "*"),
            "org.jetbrains.kotlin.cli.jvm.K2JVMCompiler",
            "-no-stdlib",
            "-no-reflect",
            "-classpath",
            os.pathsep.join(str(p) for p in sorted(libraries.glob("*.jar"))),
            "-d",
            str(plugin),
            str(source),
        ],
        cwd=directory,
        check=True,
        timeout=120,
    )
    with zipfile.ZipFile(plugin, "a") as archive:
        archive.writestr(
            "META-INF/services/org.jetbrains.kotlin.compiler.plugin.CompilerPluginRegistrar",
            "polycodegraph.Registrar\n",
        )
    metadata.write_text(
        json.dumps({"version": VERSION, "source_sha256": source_hash, "distribution_sha256": DIGEST}), encoding="utf-8"
    )
    print(f"Prepared Kotlin K2 {VERSION} and PolyCodeGraph graph plugin")


if __name__ == "__main__":
    main()
