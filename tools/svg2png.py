#!/usr/bin/env python3
"""Rasterise an SVG file to a PNG of exact pixel size, using Chrome over CDP.

Chrome's --screenshot flag does not guarantee exact output dimensions for an
SVG document, so this drives the DevTools protocol and asks for a clip of the
exact size we want.
"""
import asyncio
import base64
import json
import os
import sys
import urllib.request

import websockets  # type: ignore

SVG = sys.argv[1]
OUT = sys.argv[2]
SIZE = int(sys.argv[3]) if len(sys.argv) > 3 else 1024
PORT = int(sys.argv[4]) if len(sys.argv) > 4 else 9333


async def main() -> None:
    targets = json.loads(
        urllib.request.urlopen(f"http://127.0.0.1:{PORT}/json/list", timeout=10).read()
    )
    page = next(t for t in targets if t.get("type") == "page")
    counter = {"n": 0}

    async with websockets.connect(
        page["webSocketDebuggerUrl"], max_size=200 * 1024 * 1024
    ) as ws:

        async def send(method, params=None):
            counter["n"] += 1
            msg = {"id": counter["n"], "method": method, "params": params or {}}
            await ws.send(json.dumps(msg))
            while True:
                resp = json.loads(await ws.recv())
                if resp.get("id") == counter["n"]:
                    if "error" in resp:
                        raise RuntimeError(f"{method}: {resp['error']}")
                    return resp.get("result", {})

        html = (
            "<!doctype html><html><head><meta charset='utf-8'>"
            "<style>html,body{margin:0;padding:0;background:#fff;"
            f"width:{SIZE}px;height:{SIZE}px;overflow:hidden}}</style></head>"
            "<body>" + open(SVG, encoding="utf-8").read() + "</body></html>"
        )
        tmp = "/tmp/_news_svg_render.html"
        with open(tmp, "w", encoding="utf-8") as fh:
            fh.write(html)

        await send("Page.enable")
        await send("Runtime.enable")
        await send(
            "Emulation.setDeviceMetricsOverride",
            {
                "width": SIZE,
                "height": SIZE,
                "deviceScaleFactor": 1,
                "mobile": False,
            },
        )
        await send("Page.navigate", {"url": "file://" + tmp})
        await asyncio.sleep(2.5)

        probe = await send(
            "Runtime.evaluate",
            {
                "expression": (
                    "(()=>{const s=document.querySelector('svg');"
                    "if(!s)return 'no-svg';"
                    "const r=s.getBoundingClientRect();"
                    "return JSON.stringify({w:r.width,h:r.height});})()"
                ),
                "returnByValue": True,
            },
        )
        print("probe:", probe.get("result", {}).get("value"))

        # Overflow check: every text node must sit inside the card box it
        # belongs to. The cards live inside a translated group, so their
        # geometry has to be measured on screen rather than read off the
        # SVG attributes.
        check = await send(
            "Runtime.evaluate",
            {
                "expression": (
                    "(()=>{"
                    "const cards=[...document.querySelectorAll('rect[fill=\"#ffffff\"]')]"
                    ".filter(r=>+r.getAttribute('width')>100)"
                    ".map(r=>r.getBoundingClientRect());"
                    "const bad=[];"
                    "for(const t of document.querySelectorAll('text')){"
                    "  const b=t.getBoundingClientRect();"
                    "  const host=cards.find(c=>b.left>=c.left-1&&b.right<=c.right+1&&"
                    "    b.top>=c.top-1&&b.bottom<=c.bottom+1);"
                    "  if(host)continue;"
                    "  const near=cards.filter(c=>b.top>=c.top-2&&b.bottom<=c.bottom+40)"
                    ".sort((a,b)=>Math.abs(a.top-b.top)-Math.abs(b.top-b.top))[0];"
                    "  if(near){bad.push({text:t.textContent.slice(0,42),"
                    "    bottom:Math.round(b.bottom),cardBottom:Math.round(near.bottom),"
                    "    right:Math.round(b.right),cardRight:Math.round(near.right)});}"
                    "}"
                    "return JSON.stringify({cards:cards.length,bad});})()"
                ),
                "returnByValue": True,
            },
        )
        report = check.get("result", {}).get("value")
        print("overflow-check:", report)
        if report and '"bad":[]' not in report.replace(" ", ""):
            print("!! OVERFLOW DETECTED")
            raise SystemExit(2)

        # Canvas check: nothing may fall outside the page, or below the
        # footer line, however it is laid out.
        bounds = await send(
            "Runtime.evaluate",
            {
                "expression": (
                    "(()=>{const W=1024,H=1024;const bad=[];"
                    "for(const t of document.querySelectorAll('text')){"
                    "  const b=t.getBoundingClientRect();"
                    "  if(b.bottom>H-1||b.right>W-1||b.left<-1||b.top<-1){"
                    "    bad.push({text:t.textContent.slice(0,40),"
                    "    bottom:Math.round(b.bottom),right:Math.round(b.right)});}}"
                    "const svg=document.querySelector('svg').getBoundingClientRect();"
                    "return JSON.stringify({svgH:Math.round(svg.height),bad});})()"
                ),
                "returnByValue": True,
            },
        )
        binfo = bounds.get("result", {}).get("value")
        print("bounds-check:", binfo)
        if binfo and '"bad":[]' not in binfo.replace(" ", ""):
            print("!! OUT OF CANVAS")
            raise SystemExit(3)

        # Icon check: the mark in a card's top-left corner must not touch the
        # headline below it. The headline is the first text under the region
        # label, so the mark's box has to end above it.
        iconcheck = await send(
            "Runtime.evaluate",
            {
                "expression": (
                    "(()=>{const bad=[];"
                    "const heads=[...document.querySelectorAll('text')]"
                    ".filter(t=>{const s=t.getAttribute('font-size');"
                    "  return s&&parseFloat(s)>=19;})"
                    ".map(t=>({t:t.textContent,b:t.getBoundingClientRect()}));"
                    "const marks=[...document.querySelectorAll('g[transform*=\"scale\"]')]"
                    ".map(g=>g.getBoundingClientRect());"
                    "for(const h of heads){"
                    "  for(const m of marks){"
                    "    const overlap=!(h.b.right<=m.left||h.b.left>=m.right||"
                    "      h.b.bottom<=m.top||h.b.top>=m.bottom);"
                    "    if(overlap){bad.push({head:h.t.slice(0,34),"
                    "      headTop:Math.round(h.b.top),headLeft:Math.round(h.b.left),"
                    "      markBottom:Math.round(m.bottom),markRight:Math.round(m.right)});break;}"
                    "  }"
                    "}"
                    "return JSON.stringify({heads:heads.length,bad});})()"
                ),
                "returnByValue": True,
            },
        )
        icheck = iconcheck.get("result", {}).get("value")
        print("icon-check:", icheck)
        if icheck and '"bad":[]' not in icheck.replace(" ", ""):
            print("!! ICON OVERLAPS A HEADLINE")
            raise SystemExit(4)

        # Overlap check: no two text boxes may intersect. This catches a
        # headline sitting on its own detail, which the card-bounds check
        # alone would not.
        overlap = await send(
            "Runtime.evaluate",
            {
                "expression": (
                    "(()=>{const ts=[...document.querySelectorAll('text')]"
                    ".map(t=>({t:t.textContent.slice(0,30),b:t.getBoundingClientRect()}))"
                    ".filter(o=>o.b.width>0&&o.b.height>0);"
                    "const bad=[];"
                    "for(let i=0;i<ts.length;i++){"
                    " for(let j=i+1;j<ts.length;j++){"
                    "  const a=ts[i].b,c=ts[j].b;"
                    "  const ox=Math.min(a.right,c.right)-Math.max(a.left,c.left);"
                    "  const oy=Math.min(a.bottom,c.bottom)-Math.max(a.top,c.top);"
                    "  if(ox>1.5&&oy>1.5){bad.push({a:ts[i].t,b:ts[j].t,"
                    "    ox:Math.round(ox),oy:Math.round(oy)});}"
                    " }}"
                    "return JSON.stringify({texts:ts.length,bad});})()"
                ),
                "returnByValue": True,
            },
        )
        oinfo = overlap.get("result", {}).get("value")
        print("text-overlap-check:", oinfo)
        if oinfo and '"bad":[]' not in oinfo.replace(" ", ""):
            print("!! TEXT OVERLAP")
            raise SystemExit(5)

        shot = await send(
            "Page.captureScreenshot",
            {
                "format": "png",
                "captureBeyondViewport": False,
                "clip": {"x": 0, "y": 0, "width": SIZE, "height": SIZE, "scale": 1},
            },
        )
        data = base64.b64decode(shot["data"])
        with open(OUT, "wb") as fh:
            fh.write(data)
        print(f"wrote {OUT}: {len(data)} bytes")


asyncio.run(main())
