"""Required SDK-backed native MCP checks; no Gradle/Xcode/project hooks run."""

from __future__ import annotations

import argparse
import json
import os
import platform
import shutil
import subprocess
import tempfile
from pathlib import Path

from smoke import Client


def run(binary: Path, fixture: Path, config: dict, model: dict, verify):
    with tempfile.TemporaryDirectory(prefix="polycodegraph SDK spaces ") as temp:
        root = Path(temp)
        shutil.copytree(fixture, root, dirs_exist_ok=True)
        (root / "polycodegraph.mobile.json").write_text(
            json.dumps(model), encoding="utf-8"
        )
        (root / "polycodegraph.json").write_text(json.dumps(config), encoding="utf-8")
        client = Client(binary, root)
        try:
            arch = client.call("get_architecture")
            errors = [d for d in arch["diagnostic_samples"] if d["severity"] == "error"]
            assert not errors, errors
            verify(client)
            print(
                json.dumps(
                    {
                        "sdk_fixture": fixture.name,
                        "symbols": arch["symbols"],
                        "edges": arch["edges"],
                    }
                )
            )
        finally:
            client.close()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--binary", type=Path, required=True)
    parser.add_argument("--config", type=Path)
    parser.add_argument("--android", action="store_true")
    parser.add_argument("--ios", action="store_true")
    a = parser.parse_args()
    base = Path(__file__).resolve().parent.parent
    config = json.loads(a.config.read_text()) if a.config else {}
    config["providers_path"] = str(base / "providers")
    binary = a.binary.resolve()
    if a.android:
        sdk = Path(
            os.environ.get("ANDROID_HOME", os.environ.get("ANDROID_SDK_ROOT", ""))
        )
        jars = sorted((sdk / "platforms").glob("*/android.jar"), reverse=True)
        assert jars, "ANDROID_HOME with an installed Android platform required"
        model = {
            "kotlin": [
                {
                    "name": "AndroidFixture",
                    "files": ["*.kt"],
                    "classpath": [str(jars[0].resolve())],
                }
            ]
        }

        def android(client):
            assert (
                client.call(
                    "search_symbol",
                    query="MainActivity",
                    kind="class",
                    language="kotlin",
                )["total"]
                == 1
            )
            target = next(
                row[0]
                for row in client.call("search_symbol", query="reload", kind="method")[
                    "rows"
                ]
                if row[3] == "MainActivity.kt"
            )
            calls = client.call("callees", target=target)["rows"]
            assert any("Repository.fetch" in row[0] for row in calls), calls

        run(binary, base / "test/fixtures/android_sdk", config, model, android)
    if a.ios:
        assert platform.system() == "Darwin", (
            "UIKit validation requires macOS with Xcode"
        )

        def xcrun(*args):
            return subprocess.check_output(["/usr/bin/xcrun", *args], text=True).strip()

        sdk = xcrun("--sdk", "iphonesimulator", "--show-sdk-path")
        clang = xcrun("--find", "clang")
        resource = subprocess.check_output(
            [clang, "-print-resource-dir"], text=True
        ).strip()
        config["swiftc_path"] = xcrun("--find", "swiftc")
        library = (Path(clang).parent / "../lib/libclang.dylib").resolve()
        assert library.is_file(), library
        config["libclang_path"] = str(library)
        target = (
            "arm64" if platform.machine() == "arm64" else "x86_64"
        ) + "-apple-ios17.0-simulator"
        model = {
            "swift": [
                {
                    "name": "IOSFixture",
                    "files": ["*.swift"],
                    "sdk": sdk,
                    "target": target,
                    "bridging_header": "Domain.h",
                }
            ],
            "objectivec": [
                {
                    "files": ["*.h", "*.m"],
                    "sdk": sdk,
                    "target": target,
                    "arc": True,
                    "resource_dir": resource,
                }
            ],
        }

        def ios(client):
            assert (
                client.call(
                    "search_symbol", query="Screen", kind="class", language="swift"
                )["total"]
                == 1
            )
            assert (
                client.call(
                    "search_symbol",
                    query="ProductViewController",
                    tag="view_controller",
                    language="objectivec",
                )["total"]
                > 0
            )
            target = next(
                row[0]
                for row in client.call(
                    "search_symbol", query="reload", language="swift"
                )["rows"]
                if row[3] == "Screen.swift"
            )
            calls = client.call("callees", target=target)["rows"]
            assert any("SwiftRepository.fetch" in row[0] for row in calls), calls
            target = next(
                row[0]
                for row in client.call(
                    "search_symbol", query="reload:", language="objectivec"
                )["rows"]
                if row[3] == "Domain.m"
            )
            assert client.call("callees", target=target)["total"] == 1

        run(binary, base / "test/fixtures/ios_sdk", config, model, ios)


if __name__ == "__main__":
    main()
