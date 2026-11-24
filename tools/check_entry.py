#!/usr/bin/env python3
"""Acceptance checks for the make.fun entry.

    python3 tools/check_entry.py [repo]

Six things must hold, and each is reported on its own line as PASS or FAIL:

  1  entry.png is present and opens with the PNG or JPEG magic bytes;
  2  it is no larger than 1048576 bytes;
  3  its pixel dimensions are no larger than 1024 by 1024;
  4  every PNG chunk carries a correct CRC32 and the file ends with IEND;
  5  two runs of main.ts into different output directories produce identical
     bytes, and those bytes are exactly the shipped entry.png;
  6  main.ts, entry.png, LICENSE, README.md and .makefun/owner.json all exist.

The exit status is non-zero if anything fails. Standard library only.
"""

import os
import struct
import subprocess
import sys
import tempfile
import zlib

MAX_BYTES = 1048576
MAX_SIDE = 1024
PNG_MAGIC = b"\x89PNG\r\n\x1a\n"
JPEG_MAGIC = b"\xff\xd8\xff"
REQUIRED = ["main.ts", "entry.png", "LICENSE", "README.md", os.path.join(".makefun", "owner.json")]

failures = []


def report(name, ok, detail=""):
    print(f"{'PASS' if ok else 'FAIL'}  {name}" + (f" -- {detail}" if detail else ""))
    if not ok:
        failures.append(name)
    return ok


def dimensions(data):
    """Return (width, height) for a PNG or JPEG, or None if unrecognised."""
    if data.startswith(PNG_MAGIC) and len(data) >= 24:
        return struct.unpack(">II", data[16:24])
    if data.startswith(JPEG_MAGIC):
        # Walk the JPEG segments to the first start-of-frame header.
        at = 2
        while at + 9 < len(data):
            if data[at] != 0xFF:
                break
            marker = data[at + 1]
            if marker in (0xD8, 0xD9) or 0xD0 <= marker <= 0xD7:
                at += 2
                continue
            length = struct.unpack(">H", data[at + 2:at + 4])[0]
            if 0xC0 <= marker <= 0xCF and marker not in (0xC4, 0xC8, 0xCC):
                height, width = struct.unpack(">HH", data[at + 5:at + 9])
                return width, height
            at += 2 + length
    return None


def png_structure(data):
    """Check the signature, each chunk CRC, and that IEND closes the file."""
    if not data.startswith(PNG_MAGIC):
        return "not a PNG"
    at = 8
    chunks = 0
    while at + 12 <= len(data):
        length = struct.unpack(">I", data[at:at + 4])[0]
        kind = data[at + 4:at + 8]
        end = at + 12 + length
        if end > len(data):
            return f"chunk {kind!r} runs past the end of the file"
        payload = data[at + 4:end - 4]
        expected = struct.unpack(">I", data[end - 4:end])[0]
        if zlib.crc32(payload) & 0xFFFFFFFF != expected:
            return f"CRC mismatch in chunk {kind!r}"
        chunks += 1
        at = end
        if kind == b"IEND":
            if at != len(data):
                return f"{len(data) - at} trailing bytes after IEND"
            return None if chunks else "no chunks"
    return "no IEND chunk found"


def run_entry(repo, destination):
    env = dict(os.environ, MAKEFUN_OUTPUT_DIR=destination)
    result = subprocess.run(["node", "main.ts"], cwd=repo, env=env,
                            capture_output=True, text=True, timeout=120)
    if result.returncode != 0:
        raise RuntimeError(f"node main.ts exited {result.returncode}: "
                           f"{(result.stderr or result.stdout).strip()[:400]}")
    return result.stdout.strip()


def main():
    repo = os.path.abspath(sys.argv[1] if len(sys.argv) > 1 else ".")
    print(f"checking entry in {repo}")
    entry = os.path.join(repo, "entry.png")

    data = None
    if report("1/6 entry.png exists with PNG or JPEG magic bytes", os.path.isfile(entry),
              entry if os.path.isfile(entry) else "file not found"):
        with open(entry, "rb") as handle:
            data = handle.read()
        magic_ok = data.startswith(PNG_MAGIC) or data.startswith(JPEG_MAGIC)
        if not magic_ok:
            report("1/6 entry.png exists with PNG or JPEG magic bytes", False,
                   f"unrecognised magic bytes {data[:8]!r}")

    if data is not None:
        report("2/6 entry.png is at most 1048576 bytes", len(data) <= MAX_BYTES, f"{len(data)} bytes")
        size = dimensions(data)
        report("3/6 entry.png is at most 1024x1024 pixels",
               size is not None and size[0] <= MAX_SIDE and size[1] <= MAX_SIDE,
               f"{size[0]}x{size[1]}" if size else "dimensions unreadable")
        problem = png_structure(data)
        report("4/6 every PNG chunk CRC32 is valid and the file ends with IEND",
               problem is None, problem or "all chunk CRCs verified, IEND is last")
    else:
        for name in ("2/6 entry.png is at most 1048576 bytes",
                     "3/6 entry.png is at most 1024x1024 pixels",
                     "4/6 every PNG chunk CRC32 is valid and the file ends with IEND"):
            report(name, False, "entry.png could not be read")

    try:
        with tempfile.TemporaryDirectory(prefix="entry-check-") as tmp:
            first, second = os.path.join(tmp, "a"), os.path.join(tmp, "b")
            line_a = run_entry(repo, first)
            line_b = run_entry(repo, second)
            out_a = os.path.join(first, "entry.png")
            out_b = os.path.join(second, "entry.png")
            if not (os.path.isfile(out_a) and os.path.isfile(out_b)):
                raise RuntimeError("a run did not leave an entry.png in its output directory")
            with open(out_a, "rb") as handle:
                bytes_a = handle.read()
            with open(out_b, "rb") as handle:
                bytes_b = handle.read()
            detail = f"{len(bytes_a)} bytes each; {line_a}; {line_b}"
            if bytes_a != bytes_b:
                report("5/6 two runs write identical bytes matching entry.png", False,
                       "the two output files differ")
            elif data is not None and bytes_a != data:
                report("5/6 two runs write identical bytes matching entry.png", False,
                       "the program's output is not the shipped entry.png")
            else:
                report("5/6 two runs write identical bytes matching entry.png", True, detail)
    except (OSError, subprocess.SubprocessError, RuntimeError) as exc:
        report("5/6 two runs write identical bytes matching entry.png", False, str(exc))

    missing = [name for name in REQUIRED if not os.path.isfile(os.path.join(repo, name))]
    report("6/6 main.ts, entry.png, LICENSE, README.md and .makefun/owner.json are present",
           not missing, "all present" if not missing else "missing: " + ", ".join(missing))

    print()
    if failures:
        print(f"RESULT: FAIL ({len(failures)} check(s) failed)")
        return 1
    print("RESULT: PASS (all 6 checks)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
