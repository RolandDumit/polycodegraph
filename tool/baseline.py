"""Build the immutable v0.4.0 oracle and its release benchmark helper."""

import os
import shutil
import subprocess
from pathlib import Path

base = Path(__file__).resolve().parent.parent
oracle = base / "work/oracle"
build = base / "work/baseline"
build.mkdir(parents=True, exist_ok=True)
if not oracle.exists():
    subprocess.run(
        [
            "git",
            "clone",
            "--depth",
            "1",
            "--branch",
            "v0.4.0",
            "https://github.com/RolandDumit/polycodegraph.git",
            str(oracle),
        ],
        check=True,
    )
dart = Path(shutil.which("dart")).resolve()
if (dart.parent / "cache/dart-sdk/bin").is_dir():
    dart = (
        dart.parent / "cache/dart-sdk/bin" / ("dart.exe" if os.name == "nt" else "dart")
    )
elif dart.suffix == ".bat":
    dart = dart.with_suffix(".exe")
env = dict(os.environ, DASH__SUPPRESS_ANALYTICS="true")
subprocess.run(
    [str(dart), "pub", "get", "--enforce-lockfile"], cwd=oracle, env=env, check=True
)
exe = ".exe" if os.name == "nt" else ""
subprocess.run(
    [
        str(dart),
        "compile",
        "exe",
        "bin/polycodegraph.dart",
        "-o",
        str(build / ("polycodegraph" + exe)),
    ],
    cwd=oracle,
    env=env,
    check=True,
)
subprocess.run(
    [
        str(dart),
        "compile",
        "exe",
        "--packages=" + str(oracle / ".dart_tool/package_config.json"),
        str(base / "tool/benchmark_dart.dart"),
        "-o",
        str(build / ("benchmark_dart" + exe)),
    ],
    cwd=oracle,
    env=env,
    check=True,
)
(base / "work/sdk-config.json").write_text(
    __import__("json").dumps({"sdk_path": str(dart.parent.parent)}), encoding="utf-8"
)
