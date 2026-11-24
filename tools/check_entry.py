#!/usr/bin/env python3
"""Check the entry against the gate in the competition's RULES.txt.

The gate itself is sealed, so this reproduces the conditions the rules state,
one by one, instead of trusting a looser local approximation:

  * entry.png is there and is a PNG or a JPEG, told apart by its first bytes
  * it is at most 1048576 bytes
  * it is at most 1024 by 1024 pixels
  * every PNG chunk carries a correct CRC32 and the file ends with IEND
  * two runs of main.ts, into two different output directories, write
    identical bytes, and those bytes are the shipped entry.png
  * the repository carries main.ts, entry.png, LICENSE, README.md and
    .makefun/owner.json

Every check prints PASS or FAIL. A single FAIL makes the whole script exit
non-zero, so a defect cannot slip through unnoticed.

Usage: python3 tools/check_entry.py [repo-root]   (default: the current dir)
"""

import hashlib
import os
import shutil
import struct
import subprocess
import sys
import tempfile
import zlib
from pathlib import Path

PNG_MAGIC = b"\x89PNG\r\n\x1a\n"
JPEG_MAGIC = b"\xff\xd8"
MAX_BYTES = 1048576
MAX_SIDE = 1024
REQUIRED_FILES = ("main.ts", "entry.png", "LICENSE", "README.md", ".makefun/owner.json")

REPO = Path(sys.argv[1] if len(sys.argv) > 1 else ".").resolve()
IMAGE = REPO / "entry.png"

failures = []


def check(name, ok, detail=""):
    """Print one PASS/FAIL line and remember any failure for the exit code."""
    print("  [%s] %s%s" % ("PASS" if ok else "FAIL", name,
                           (" -- " + detail) if detail else ""))
    if not ok:
        failures.append(name)
    return ok


def jpeg_size(data):
    """Read the frame dimensions out of a JPEG, or None if they are missing."""
    offset = 2
    end = len(data)
    while offset + 4 <= end:
        if data[offset] != 0xFF:
            offset += 1
            continue
        marker = data[offset + 1]
        if marker in (0xD8, 0x01) or 0xD0 <= marker <= 0xD7:
            offset += 2
            continue
        if marker == 0xD9:  # end of image
            break
        (length,) = struct.unpack(">H", data[offset + 2:offset + 4])
        # SOF0..SOF15, minus the three markers that share the range but
        # carry no frame: DHT, JPG and DAC.
        if 0xC0 <= marker <= 0xCF and marker not in (0xC4, 0xC8, 0xCC):
            height, width = struct.unpack(">HH", data[offset + 5:offset + 9])
            return width, height
        offset += 2 + length
    return None


print("=== 1. entry.png exists and is a PNG or a JPEG ===")
if not IMAGE.is_file():
    check("entry.png exists", False, "%s is missing" % IMAGE)
    print()
    print("FAIL: 1 check(s) failed: %s" % ", ".join(failures))
    sys.exit(1)

data = IMAGE.read_bytes()
is_png = data[:8] == PNG_MAGIC
is_jpeg = data[:2] == JPEG_MAGIC
check("entry.png exists", True, "%d bytes" % len(data))
check("told apart by its first bytes", is_png or is_jpeg,
      "PNG" if is_png else ("JPEG" if is_jpeg else "unknown magic %r" % (data[:4],)))

print()
print("=== 2. size and dimensions ===")
check("at most %d bytes" % MAX_BYTES, len(data) <= MAX_BYTES,
      "%d bytes" % len(data))

if is_png:
    width, height = struct.unpack(">II", data[16:24])
    check("at most %d by %d pixels" % (MAX_SIDE, MAX_SIDE),
          width <= MAX_SIDE and height <= MAX_SIDE, "%d by %d" % (width, height))
    bit_depth, colour = data[24], data[25]
    check("the header describes the image",
          bit_depth in (1, 2, 4, 8, 16) and colour in (0, 2, 3, 4, 6),
          "bit depth %d, colour type %d" % (bit_depth, colour))
elif is_jpeg:
    size = jpeg_size(data)
    if size is None:
        check("at most %d by %d pixels" % (MAX_SIDE, MAX_SIDE), False,
              "no frame header found")
    else:
        width, height = size
        check("at most %d by %d pixels" % (MAX_SIDE, MAX_SIDE),
              width <= MAX_SIDE and height <= MAX_SIDE, "%d by %d" % (width, height))
else:
    check("dimensions", False, "not a PNG or a JPEG")

print()
print("=== 3. every PNG chunk with its checksum ===")
if is_png:
    offset = 8
    chunks = []
    crc_ok = True
    saw_idat = False
    saw_iend = False
    while offset < len(data):
        if offset + 8 > len(data):
            crc_ok = False
            break
        (length,) = struct.unpack(">I", data[offset:offset + 4])
        kind = data[offset + 4:offset + 8]
        if offset + 12 + length > len(data):
            crc_ok = False
            print("       chunk %r runs past the end of the file" % kind)
            break
        stored = struct.unpack(">I", data[offset + 8 + length:offset + 12 + length])[0]
        computed = zlib.crc32(data[offset + 4:offset + 8 + length]) & 0xFFFFFFFF
        if stored != computed:
            crc_ok = False
            print("       CRC mismatch in %r" % kind)
            break
        chunks.append(kind.decode("ascii", "replace"))
        if kind == b"IDAT":
            saw_idat = True
        offset += 12 + length
        if kind == b"IEND":
            saw_iend = True
            break
    check("every chunk's checksum holds", crc_ok,
          " ".join(chunks[:6]) + (" ..." if len(chunks) > 6 else ""))
    check("the image data its header describes is present", saw_idat,
          "IDAT present" if saw_idat else "no IDAT")
    check("the file ends with IEND and nothing after it",
          saw_iend and offset == len(data),
          "IEND at %d of %d" % (offset, len(data)))

print()
print("=== 4. two runs of main.ts write the same bytes ===")
NODE = shutil.which("node") or "/usr/local/bin/node"
outputs = []
for run in (1, 2):
    out_dir = tempfile.mkdtemp(prefix="_news_image_run%d_" % run)
    try:
        env = dict(os.environ)
        env["MAKEFUN_OUTPUT_DIR"] = out_dir
        result = subprocess.run([NODE, "--experimental-strip-types", "main.ts"],
                                cwd=str(REPO), capture_output=True, text=True, env=env)
        if result.returncode != 0:
            check("run %d succeeds" % run, False, result.stderr[-300:])
            break
        produced = Path(out_dir) / "entry.png"
        if not produced.is_file():
            check("run %d writes entry.png" % run, False, "nothing in %s" % out_dir)
            break
        check("run %d succeeds" % run, True, result.stdout.strip())
        outputs.append(produced.read_bytes())
    finally:
        shutil.rmtree(out_dir, ignore_errors=True)

if len(outputs) == 2:
    check("the two runs write identical bytes", outputs[0] == outputs[1],
          "sha256 %s / %s" % (hashlib.sha256(outputs[0]).hexdigest()[:16],
                              hashlib.sha256(outputs[1]).hexdigest()[:16]))
    check("the written bytes are the shipped image", outputs[0] == data,
          "matches entry.png" if outputs[0] == data else "differs from entry.png")

print()
print("=== 5. the repository carries what the entry needs ===")
for relative in REQUIRED_FILES:
    check("%s is present" % relative, (REPO / relative).exists())

print()
if failures:
    print("FAIL: %d check(s) failed: %s" % (len(failures), ", ".join(failures)))
    sys.exit(1)
print("PASS: the entry satisfies every condition the rules state")
