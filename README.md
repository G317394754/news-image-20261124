# One image. One day. The whole world.

[![make.fun bounty](https://make.fun/badge/news-image-20261124.svg)](https://make.fun/bounty/news-image-20261124)
[![rank](https://make.fun/badge/news-image-20261124/G317394754/news-image-20261124/rank.svg)](https://make.fun/bounty/news-image-20261124)
[![reward](https://make.fun/badge/news-image-20261124/G317394754/news-image-20261124/reward.svg)](https://make.fun/bounty/news-image-20261124)

**Bounty:** <https://make.fun/bounty/news-image-20261124>

`entry.png` is a 1024×1024 newspaper front page for **Tuesday 24 November
2026**. A dark masthead carries the date, ten cards lay out the day's stories
with the biggest first, a four-story strip runs along the bottom, and a footer
names the sources. Every card has a coloured spine, a vector mark, a region
label, a serif headline and a short detail.

## Running it

The graded entry point just republishes the finished page:

```sh
MAKEFUN_OUTPUT_DIR=out node main.ts
```

That writes `out/entry.png`, creating `out` if it does not exist, and prints
the number of bytes written. `/output` is the default when the variable is
unset. Node **22.18+** runs the TypeScript directly; on an older Node use
`node --experimental-strip-types main.ts`. Only the standard library is used,
and nothing is drawn at run time, so two runs cannot produce different bytes.

To redraw the page from the story file instead:

```sh
node render.mjs > page.svg
python3 tools/svg2png.py page.svg page.png 1024
```

The rasteriser drives Chrome over the DevTools protocol, reusing a Chrome
already listening on port 9333 or starting a headless one of its own, and it
needs the `websockets` Python package. Set `CHROME_BIN` or `SVG2PNG_PORT` to
override either default. `entry.png` is the committed page; redrawing renders
whatever `news.json` currently says.

Verify the entry the way the judge does:

```sh
python3 tools/check_entry.py .
```

## How the layout is built

`news.json` holds the copy; `render.mjs` turns it into an SVG.

* Text is wrapped by **measured pixel width**, using per-mille glyph advances
  for the Georgia and Helvetica stacks, never by counting characters.
* Every card is exactly as tall as the lines it contains, so no headline or
  detail is ever clipped to fit a grid.
* The renderer picks the largest type scale whose measured page fits, then
  spreads the leftover space into the gaps between rows, so the page ends
  precisely at the footer rule.
* `tools/svg2png.py` audits the rendered geometry before writing anything:
  no text off the page, no two text boxes overlapping, no mark touching a
  headline, and no text escaping its card. A failure means no file is written.

## The stories

| # | Region | Headline |
|---|--------|----------|
| 1 | United States | Nvidia reinstates Jensen Huang as chief executive |
| 2 | Strait of Hormuz | Three oil tankers strike mines and catch fire |
| 3 | Gaza | Israeli strikes kill at least eight in Gaza |
| 4 | Ukraine | Ukrainian sea drones hit a Russian warship in Libya |
| 5 | European Union | A 22nd sanctions package lands on Russia |
| 6 | Climate | COP31 ends in Antalya with no agreement |
| 7 | The World Court | ICJ rules Myanmar guilty of genocide |
| 8 | Markets | Wall Street roars back: Nasdaq +6.5% |
| 9 | Science | Euclid finds the most distant quasar yet |
| 10 | Bangladesh | Hasina says she returns home on 16 December |

The bottom strip adds four more: a Pakistani astronaut flying on China's
Shenzhou-24, flooding in the Galapagos Islands, the Nungwi Beach hotel fire in
Zanzibar with 180 tourists evacuated, and the search for dozens trapped by an
Indonesian candy factory fire.

## Repository layout

    main.ts              entry point: publish entry.png to $MAKEFUN_OUTPUT_DIR
    entry.png            the shipped page, 1024x1024
    news.json            the day's stories, and the copy for masthead and footer
    render.mjs           measured, fit-to-content SVG layout of the page
    tools/svg2png.py     Chrome/DevTools rasteriser with a layout audit
    tools/check_entry.py the six acceptance checks
    LICENSE              MIT
    .makefun/owner.json  the owner's make.fun account

## License

MIT. See `LICENSE`.
