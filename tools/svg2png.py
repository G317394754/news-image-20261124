#!/usr/bin/env python3
"""Rasterise an SVG to a PNG of an exact pixel size, through Chrome's DevTools protocol.

Chrome's --screenshot flag does not promise exact output dimensions for an SVG
document, so this drives the protocol itself and asks for a clip of exactly the
size we want.

The PNG is the deliverable, so it is gated. Before a single byte is written the
rendered page is measured in the browser and four conditions must hold:

  (a) no text box reaches outside the canvas
  (b) no two text boxes intersect
  (c) no mark touches a headline
  (d) every text box of a card lies inside that card's rectangle

The page marks up its own geometry for this: a card rectangle and the texts that
belong to it share a data-card index, marks carry data-icon, and headlines carry
data-role="headline". Measuring is done with getBoundingClientRect, in screen
coordinates, so translated groups and scaled marks are accounted for.

Any violation refuses the write and exits non-zero. A picture that breaks the
layout never reaches the judge.

Usage: python3 tools/svg2png.py <input.svg> <output.png> <size, e.g. 1024> [port]
"""

import asyncio
import base64
import json
import os
import struct
import subprocess
import sys
import tempfile
import time
import urllib.request

import websockets  # type: ignore

CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"

SVG = sys.argv[1]
OUT = sys.argv[2]
SIZE = int(sys.argv[3]) if len(sys.argv) > 3 else 1024
PORT = int(sys.argv[4]) if len(sys.argv) > 4 else 9333


def refuse(message, code):
    print("REFUSED: " + message)
    raise SystemExit(code)


def port_is_open(port):
    try:
        urllib.request.urlopen("http://127.0.0.1:%d/json/version" % port, timeout=2).read()
        return True
    except Exception:
        return False


def ensure_browser(port):
    """Use the browser that is already there, or start one and wait for it."""
    if port_is_open(port):
        print("browser: using the Chrome already listening on %d" % port)
        return
    if not os.path.exists(CHROME):
        refuse("no browser at %s and nothing answering on port %d" % (CHROME, port), 10)
    print("browser: starting Chrome on port %d" % port)
    subprocess.Popen(
        [
            CHROME,
            "--remote-debugging-port=%d" % port,
            "--user-data-dir=/tmp/chrome_radar",
            "--no-first-run",
            "--no-default-browser-check",
            "--disable-features=Translate,TranslateUI",
            "--lang=en-US",
            "about:blank",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    for _ in range(80):
        if port_is_open(port):
            return
        time.sleep(0.5)
    refuse("Chrome never opened its debugging port on %d" % port, 11)


# One expression, run in the page, that measures everything the gate needs.
# Sizes are in CSS pixels, which is what the screenshot clip uses too.
PROBE = """
(() => {
  const SIZE = __SIZE__;
  const rect = (r) => ({l:r.left,t:r.top,r:r.right,b:r.bottom});
  const texts = [...document.querySelectorAll('text')].map((el) => ({
    text: el.textContent.slice(0, 44),
    role: el.getAttribute('data-role') || '',
    card: el.getAttribute('data-card'),
    box: rect(el.getBoundingClientRect())
  })).filter((o) => o.box.r > o.box.l && o.box.b > o.box.t);

  const cards = {};
  for (const el of document.querySelectorAll('rect[data-card]')) {
    cards[el.getAttribute('data-card')] = rect(el.getBoundingClientRect());
  }
  const marks = [...document.querySelectorAll('g[data-icon]')].map((el) => ({
    name: el.getAttribute('data-icon'),
    box: rect(el.getBoundingClientRect())
  }));

  // (a) the canvas
  const outside = [];
  for (const o of texts) {
    if (o.box.l < -0.5 || o.box.t < -0.5 || o.box.r > SIZE + 0.5 || o.box.b > SIZE + 0.5) {
      outside.push({text: o.text, left: Math.round(o.box.l), right: Math.round(o.box.r),
                    top: Math.round(o.box.t), bottom: Math.round(o.box.b)});
    }
  }

  // (b) text against text
  const collisions = [];
  for (let i = 0; i < texts.length; i++) {
    for (let j = i + 1; j < texts.length; j++) {
      const a = texts[i].box, b = texts[j].box;
      const ox = Math.min(a.r, b.r) - Math.max(a.l, b.l);
      const oy = Math.min(a.b, b.b) - Math.max(a.t, b.t);
      if (ox > 1 && oy > 1) {
        collisions.push({a: texts[i].text, b: texts[j].text,
                         ox: Math.round(ox), oy: Math.round(oy)});
      }
    }
  }

  // (c) marks against headlines
  const marked = [];
  const titles = texts.filter((o) => o.role === 'headline' || o.role === 'strip-headline');
  for (const h of titles) {
    for (const m of marks) {
      const a = h.box, b = m.box;
      if (!(a.r <= b.l || a.l >= b.r || a.b <= b.t || a.t >= b.b)) {
        marked.push({headline: h.text, mark: m.name,
                     headlineLeft: Math.round(a.l), markRight: Math.round(b.r)});
      }
    }
  }

  // (d) a card's texts inside that card
  const strays = [];
  for (const o of texts) {
    if (o.card === null || o.card === undefined) continue;
    const c = cards[o.card];
    if (!c) { strays.push({text: o.text, card: o.card, why: 'no such card'}); continue; }
    const b = o.box;
    if (b.l < c.l - 0.5 || b.t < c.t - 0.5 || b.r > c.r + 0.5 || b.b > c.b + 0.5) {
      strays.push({text: o.text, card: o.card,
                   textRight: Math.round(b.r), cardRight: Math.round(c.r),
                   textBottom: Math.round(b.b), cardBottom: Math.round(c.b)});
    }
  }

  return JSON.stringify({texts: texts.length, cards: Object.keys(cards).length,
                         marks: marks.length, titles: titles.length,
                         outside, collisions, marked, strays});
})()
""".replace("__SIZE__", str(SIZE))


async def main():
    ensure_browser(PORT)
    targets = json.loads(
        urllib.request.urlopen("http://127.0.0.1:%d/json/list" % PORT, timeout=10).read()
    )
    page = next((t for t in targets if t.get("type") == "page"), None)
    if page is None:
        refuse("the browser has no page target to draw into", 12)

    markup = (
        "<!doctype html><html><head><meta charset='utf-8'>"
        "<style>html,body{margin:0;padding:0;background:#fff;"
        "width:%dpx;height:%dpx;overflow:hidden}svg{display:block}</style>"
        "</head><body>" % (SIZE, SIZE)
        + open(SVG, encoding="utf-8").read()
        + "</body></html>"
    )
    workdir = tempfile.mkdtemp(prefix="svg2png_")
    document = os.path.join(workdir, "page.html")
    with open(document, "w", encoding="utf-8") as handle:
        handle.write(markup)

    counter = {"n": 0}
    async with websockets.connect(page["webSocketDebuggerUrl"], max_size=200 * 1024 * 1024) as ws:

        async def send(method, params=None):
            counter["n"] += 1
            await ws.send(json.dumps({"id": counter["n"], "method": method, "params": params or {}}))
            while True:
                reply = json.loads(await ws.recv())
                if reply.get("id") == counter["n"]:
                    if "error" in reply:
                        raise RuntimeError("%s: %s" % (method, reply["error"]))
                    return reply.get("result", {})

        async def evaluate(expression):
            reply = await send("Runtime.evaluate", {"expression": expression, "returnByValue": True})
            return reply.get("result", {}).get("value")

        await send("Page.enable")
        await send("Runtime.enable")
        await send(
            "Emulation.setDeviceMetricsOverride",
            {"width": SIZE, "height": SIZE, "deviceScaleFactor": 1, "mobile": False},
        )
        await send("Page.navigate", {"url": "file://" + document})
        for _ in range(60):
            await asyncio.sleep(0.25)
            ready = await evaluate("document.readyState + ':' + !!document.querySelector('svg')")
            if ready == "complete:true":
                break
        else:
            refuse("the page never finished loading", 13)
        await evaluate("document.fonts ? document.fonts.ready.then(() => 1) : 1")
        await asyncio.sleep(0.6)

        report = json.loads(await evaluate(PROBE))
        print("measured: %d text boxes, %d cards, %d marks, %d headlines"
              % (report["texts"], report["cards"], report["marks"], report["titles"]))

        gates = [
            ("(a) no text box outside the canvas", "outside", 2),
            ("(b) no two text boxes intersect", "collisions", 3),
            ("(c) no mark touches a headline", "marked", 4),
            ("(d) every card text inside its own card", "strays", 5),
        ]
        broken = []
        for label, key, code in gates:
            found = report[key]
            print("  [%s] %s" % ("PASS" if not found else "FAIL", label))
            for item in found[:12]:
                print("       " + json.dumps(item, ensure_ascii=False))
            if found:
                broken.append((label, code))
        if broken:
            refuse("%d layout check(s) failed; %s was not written"
                   % (len(broken), OUT), broken[0][1])

        shot = await send(
            "Page.captureScreenshot",
            {
                "format": "png",
                "captureBeyondViewport": False,
                "clip": {"x": 0, "y": 0, "width": SIZE, "height": SIZE, "scale": 1},
            },
        )
        data = base64.b64decode(shot["data"])
        if data[:8] != b"\x89PNG\r\n\x1a\n":
            refuse("the capture is not a PNG", 6)
        width, height = struct.unpack(">II", data[16:24])
        if (width, height) != (SIZE, SIZE):
            refuse("the capture came out %d by %d, wanted %d by %d" % (width, height, SIZE, SIZE), 7)
        with open(OUT, "wb") as handle:
            handle.write(data)
        print("wrote %s: %d bytes, %d by %d" % (OUT, len(data), width, height))


asyncio.run(main())
