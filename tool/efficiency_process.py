"""Trusted POSIX launcher; bound writable files separately from captured output."""

from __future__ import annotations

import argparse
import os

DEFAULT_FILE_SIZE_BYTES = 8 * 1024 * 1024
MAX_FILE_SIZE_BYTES = 512 * 1024 * 1024


def file_size_budget(value: int) -> int:
    """Require an explicit finite allowance for an executor's owned derived files."""
    if (
        type(value) is not int
        or not DEFAULT_FILE_SIZE_BYTES <= value <= MAX_FILE_SIZE_BYTES
    ):
        raise ValueError("executor file-size budget must be 8..512 MiB")
    return value


def main() -> None:
    """Preserve process-group and file-size budgets without threaded preexec hooks."""
    import resource

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--file-size-limit-bytes", type=int, default=DEFAULT_FILE_SIZE_BYTES
    )
    parser.add_argument("command")
    args = parser.parse_args()
    if not os.path.isabs(args.command):
        raise ValueError("one absolute trusted executor path is required")
    limit = file_size_budget(args.file_size_limit_bytes)
    resource.setrlimit(resource.RLIMIT_FSIZE, (limit, limit))
    os.execv(args.command, [args.command])


if __name__ == "__main__":
    main()
