#!/usr/bin/env python3
"""Rasterise an SVG into a PNG of an exact size, and refuse to ship a bad page.

    python3 tools/svg2png.py input.svg output.png 1024

Chrome is driven over the DevTools protocol: a fresh tab is pointed at the
SVG, the device metrics are forced to the requested width and height, and the
screenshot is taken with an explicit clip, so the result is exactly that many
pixels, never a scaled or padded one.

The picture is only written once the layout has been proved sound in the
browser itself, using the real geometry of the rendered glyphs:

  * the SVG parsed and actually produced text;
  * every text box lies inside the page;
  * no two text boxes overlap;
  * no vector mark touches a headline;
  * no text escapes the panel (card or strip) that contains it.

Any failure prints the offending elements and exits non-zero without writing
the output file, so a broken page can never be mistaken for a finished one.

Chrome is reused when one already listens on the debugging port (its other
tabs are left alone), otherwise a private headless instance is started for
the duration of the run. Needs the 'websockets' package.
"""

import base64
import json
import os
import shutil
import struct
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request

try:
    from websockets.sync.client import connect as ws_connect
except ImportError:  # pragma: no cover - environment problem, not a page problem
    sys.stderr.write("svg2png: the 'websockets' package is required (pip install websockets)\n")
    raise SystemExit(2)

PORT = int(os.environ.get("SVG2PNG_PORT", "9333"))
BROWSER = f"http://127.0.0.1:{PORT}"
TIMEOUT = 90

CHROME_CANDIDATES = [
    os.environ.get("CHROME_BIN", ""),
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Chromium.app/Contents/MacOS/Chromium",
    "/Applications/Google Chrome Canary.app/Contents/MacOS/Google Chrome Canary",
    "/usr/bin/google-chrome",
    "/usr/bin/chromium",
    "/usr/bin/chromium-browser",
]


def http_json(path, method="GET"):
    req = urllib.request.Request(BROWSER + path, method=method)
    with urllib.request.urlopen(req, timeout=5) as response:
        body = response.read().decode("utf-8", "replace")
    try:
        return json.loads(body)
    except json.JSONDecodeError:
        # Some endpoints answer with a bare string such as "Target is closing".
        return {"raw": body}


def running_browser():
    try:
        return http_json("/json/version")
    except (urllib.error.URLError, OSError):
        return None


def start_browser():
    """Launch a private headless Chrome and wait for its debugging port."""
    executable = next((p for p in CHROME_CANDIDATES if p and os.path.exists(p)), None)
    if executable is None:
        executable = shutil.which("google-chrome") or shutil.which("chromium")
    if executable is None:
        raise SystemExit("svg2png: no Chrome found; set CHROME_BIN or start Chrome with "
                         f"--remote-debugging-port={PORT}")
    profile = tempfile.mkdtemp(prefix="svg2png-chrome-")
    process = subprocess.Popen(
        [executable, f"--remote-debugging-port={PORT}", f"--user-data-dir={profile}",
         "--headless=new", "--no-first-run", "--no-default-browser-check", "--hide-scrollbars",
         "--force-device-scale-factor=1", "about:blank"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    deadline = time.time() + 45
    while time.time() < deadline:
        if running_browser():
            return process
        if process.poll() is not None:
            break
        time.sleep(0.4)
    process.kill()
    raise SystemExit("svg2png: Chrome did not open its debugging port in time")


class Tab:
    """One freshly created tab, driven over its own websocket."""

    def __init__(self):
        self.owned_process = None
        if running_browser() is None:
            self.owned_process = start_browser()
        target = http_json("/json/new?about:blank", method="PUT")
        self.target_id = target["id"]
        self.ws = ws_connect(target["webSocketDebuggerUrl"], max_size=256 * 1024 * 1024)
        self.next_id = 0
        self.send("Page.enable")
        self.send("Runtime.enable")

    def send(self, method, **params):
        self.next_id += 1
        message_id = self.next_id
        self.ws.send(json.dumps({"id": message_id, "method": method, "params": params}))
        deadline = time.time() + TIMEOUT
        while time.time() < deadline:
            message = json.loads(self.ws.recv())
            if message.get("id") == message_id:
                if "error" in message:
                    raise SystemExit(f"svg2png: {method} failed: {message['error']}")
                return message.get("result", {})
        raise SystemExit(f"svg2png: timed out waiting for {method}")

    def evaluate(self, expression):
        result = self.send("Runtime.evaluate", expression=expression,
                           returnByValue=True, awaitPromise=True)
        if "exceptionDetails" in result:
            raise SystemExit(f"svg2png: page script failed: {result['exceptionDetails']}")
        return result.get("result", {}).get("value")

    def close(self):
        try:
            self.ws.close()
        except OSError:
            pass
        try:
            http_json(f"/json/close/{self.target_id}")
        except (urllib.error.URLError, OSError):
            pass
        if self.owned_process is not None:
            self.owned_process.terminate()


# The layout audit. It runs inside the page and reports real pixel geometry.
AUDIT = r"""
(() => {
  const W = window.innerWidth, H = window.innerHeight;
  const bad = [];
  const box = (el) => {
    const r = el.getBoundingClientRect();
    return {x: r.x, y: r.y, w: r.width, h: r.height,
            text: (el.textContent || el.tagName).trim().slice(0, 40)};
  };
  const overlap = (a, b) => Math.min(a.x + a.w, b.x + b.w) - Math.max(a.x, b.x) > 1.5 &&
                            Math.min(a.y + a.h, b.y + b.h) - Math.max(a.y, b.y) > 1.5;
  const parseError = document.querySelector('parsererror');
  if (parseError) return {error: 'the SVG is not well-formed XML: ' + parseError.textContent.slice(0, 300)};
  const svg = document.querySelector('svg');
  if (!svg) return {error: 'no svg root in the document'};
  if (svg.getBoundingClientRect().width < 10) return {error: 'svg laid out at zero width'};

  const texts = [...svg.querySelectorAll('text')].map(box);
  if (!texts.length) return {error: 'the page contains no text runs at all'};
  for (const t of texts) {
    if (t.w <= 0) bad.push({kind: 'empty-text', ...t});
    if (t.x < -0.5 || t.y < -0.5 || t.x + t.w > W + 0.5 || t.y + t.h > H + 0.5)
      bad.push({kind: 'text-off-page', ...t});
  }
  for (let i = 0; i < texts.length; i++)
    for (let j = i + 1; j < texts.length; j++)
      if (overlap(texts[i], texts[j]))
        bad.push({kind: 'text-overlap', a: texts[i].text, b: texts[j].text,
                  at: [texts[i].x, texts[i].y]});

  const marks = [...svg.querySelectorAll('g.mark')].map(box);
  const headlines = [...svg.querySelectorAll('text.headline, text.strip-headline')].map(box);
  for (const m of marks)
    for (const h of headlines)
      if (overlap(m, h)) bad.push({kind: 'mark-touches-headline', mark: m.text, headline: h.text});

  for (const panel of svg.querySelectorAll('g.card, g.strip')) {
    const bg = panel.querySelector('rect.panel');
    if (!bg) { bad.push({kind: 'panel-without-background', text: panel.textContent.slice(0, 40)}); continue; }
    const p = box(bg);
    for (const t of [...panel.querySelectorAll('text')].map(box)) {
      if (t.x < p.x - 0.5 || t.y < p.y - 0.5 ||
          t.x + t.w > p.x + p.w + 0.5 || t.y + t.h > p.y + p.h + 0.5)
        bad.push({kind: 'text-escapes-panel', text: t.text,
                  text_box: [t.x, t.y, t.w, t.h], panel_box: [p.x, p.y, p.w, p.h]});
    }
  }
  return {width: W, height: H, textCount: texts.length,
          panelCount: svg.querySelectorAll('g.card, g.strip').length,
          markCount: marks.length, problems: bad};
})()
"""


def png_size(data):
    if data[:8] != b"\x89PNG\r\n\x1a\n":
        return None
    return struct.unpack(">II", data[16:24])


def main():
    if len(sys.argv) != 4:
        raise SystemExit(__doc__)
    source, destination, size_arg = sys.argv[1], sys.argv[2], sys.argv[3]
    size = int(size_arg)
    source = os.path.abspath(source)
    if not os.path.isfile(source):
        raise SystemExit(f"svg2png: no such SVG: {source}")

    tab = Tab()
    try:
        tab.send("Emulation.setDeviceMetricsOverride", width=size, height=size,
                 deviceScaleFactor=1, mobile=False)
        tab.send("Page.navigate", url="file://" + source)
        deadline = time.time() + TIMEOUT
        while time.time() < deadline:
            ready = tab.evaluate(
                "document.readyState === 'complete' && !!document.querySelector('svg, parsererror') "
                "&& (!document.fonts || document.fonts.status === 'loaded')")
            if ready:
                break
            time.sleep(0.2)
        else:
            raise SystemExit("svg2png: the SVG never finished loading")

        audit = tab.evaluate(AUDIT)
        if audit is None or "error" in audit:
            raise SystemExit(f"svg2png: could not audit the page: {audit}; "
                             f"{destination} was not written")
        print(f"page {audit['width']}x{audit['height']}; {audit['textCount']} text runs, "
              f"{audit['panelCount']} panels, {audit['markCount']} marks")
        if audit["problems"]:
            for problem in audit["problems"]:
                print("  LAYOUT FAIL:", json.dumps(problem, ensure_ascii=False), file=sys.stderr)
            raise SystemExit(f"svg2png: {len(audit['problems'])} layout problem(s); "
                             f"{destination} was not written")
        print("layout checks: no text off-page, no overlapping text, "
              "no mark on a headline, no text outside its panel")

        shot = tab.send("Page.captureScreenshot", format="png", fromSurface=True,
                        clip={"x": 0, "y": 0, "width": size, "height": size, "scale": 1})
        data = base64.b64decode(shot["data"])
        actual = png_size(data)
        if actual != (size, size):
            raise SystemExit(f"svg2png: capture came back {actual}, expected {(size, size)}; "
                             f"{destination} was not written")
        with open(destination, "wb") as handle:
            handle.write(data)
        print(f"wrote {destination}: {size}x{size}, {len(data)} bytes")
    finally:
        tab.close()


if __name__ == "__main__":
    main()
