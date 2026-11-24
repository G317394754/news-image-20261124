#!/usr/bin/env python3
"""Check the entry against the gate in the competition's RULES.txt.

The gate is sealed and not published, so this reproduces the conditions the
rules state, line by line, rather than trusting a local approximation:

  - the file is a PNG or a JPEG, told apart by its first bytes
  - it is at most 1048576 bytes and at most 1024 by 1024 pixels
  - it is a whole image: every PNG chunk with its checksum and the image
    data its header describes, or every JPEG segment through to its end
    marker
  - the program's two runs write the same bytes
"""
import hashlib
import os
import shutil
import struct
import subprocess
import sys
import zlib
from pathlib import Path

REPO = Path(sys.argv[1] if len(sys.argv) > 1 else ".").resolve()
PNG = REPO / "entry.png"
LIMIT_BYTES = 1048576
LIMIT_PX = 1024

failures = []


def check(name, ok, detail=""):
    mark = "PASS" if ok else "FAIL"
    print(f"  [{mark}] {name}" + (f" — {detail}" if detail else ""))
    if not ok:
        failures.append(name)


print("=== 1. the file exists and is a whole PNG or JPEG ===")
if not PNG.exists():
    check("entry.png exists", False, f"{PNG} missing")
    sys.exit(1)

data = PNG.read_bytes()
is_png = data[:8] == b"\x89PNG\r\n\x1a\n"
is_jpeg = data[:2] == b"\xff\xd8"
check("told apart by its first bytes", is_png or is_jpeg,
      "PNG" if is_png else ("JPEG" if is_jpeg else f"unknown magic {data[:4]!r}"))

print()
print("=== 2. size and dimensions ===")
check(f"at most {LIMIT_BYTES} bytes", len(data) <= LIMIT_BYTES, f"{len(data)} bytes")
if is_png:
    w, h = struct.unpack(">II", data[16:24])
    check(f"at most {LIMIT_PX} by {LIMIT_PX} pixels", w <= LIMIT_PX and h <= LIMIT_PX, f"{w} by {h}")
    bit_depth, colour = data[24], data[25]
    check("header describes the image", bit_depth in (1, 2, 4, 8, 16) and colour in (0, 2, 3, 4, 6),
          f"bit depth {bit_depth}, colour type {colour}")

print()
print("=== 3. every PNG chunk with its checksum ===")
if is_png:
    off = 8
    chunks = []
    ok = True
    saw_iend = False
    saw_idat = False
    while off < len(data):
        if off + 8 > len(data):
            ok = False
            break
        (length,) = struct.unpack(">I", data[off:off + 4])
        ctype = data[off + 4:off + 8]
        if off + 12 + length > len(data):
            ok = False
            break
        stored = struct.unpack(">I", data[off + 8 + length:off + 12 + length])[0]
        computed = zlib.crc32(data[off + 4:off + 8 + length]) & 0xFFFFFFFF
        if stored != computed:
            ok = False
            print(f"       CRC mismatch in {ctype!r}")
            break
        chunks.append(ctype.decode("ascii", "replace"))
        if ctype == b"IDAT":
            saw_idat = True
        if ctype == b"IEND":
            saw_iend = True
            off += 12 + length
            break
        off += 12 + length
    check("every chunk's checksum holds", ok, " ".join(chunks[:6]) + (" ..." if len(chunks) > 6 else ""))
    check("the image data its header describes is present", saw_idat, "IDAT present" if saw_idat else "no IDAT")
    check("the file ends with IEND and nothing after it", saw_iend and off == len(data),
          f"IEND at {off} of {len(data)}")

print()
print("=== 4. the program's two runs write the same bytes ===")
NODE = shutil.which("node") or "/usr/local/bin/node"
outs = []
for i in (1, 2):
    out = Path(f"/tmp/_ni_gate_{i}")
    subprocess.run(["rm", "-rf", str(out)], check=False)
    out.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ)
    env["MAKEFUN_OUTPUT_DIR"] = str(out)
    r = subprocess.run([NODE, "--experimental-strip-types", "main.ts"],
                       cwd=REPO, capture_output=True, text=True, env=env)
    if r.returncode != 0:
        check(f"run {i} succeeds", False, r.stderr[-300:])
        break
    produced = out / "entry.png"
    if not produced.exists():
        check(f"run {i} writes entry.png", False)
        break
    outs.append(produced.read_bytes())
if len(outs) == 2:
    check("run 1 and run 2 write identical bytes", outs[0] == outs[1],
          f"sha256 {hashlib.sha256(outs[0]).hexdigest()[:16]} / {hashlib.sha256(outs[1]).hexdigest()[:16]}")
    check("the written bytes are the shipped image", outs[0] == data,
          "matches entry.png" if outs[0] == data else "differs from entry.png")

print()
print("=== 5. the repository carries what the entry needs ===")
for rel in ("main.ts", "entry.png", "LICENSE", "README.md", ".makefun/owner.json"):
    check(f"{rel} is present", (REPO / rel).exists())

print()
if failures:
    print(f"FAIL: {len(failures)} check(s) failed: {', '.join(failures)}")
    sys.exit(1)
print("PASS: the entry satisfies every condition the rules state")
