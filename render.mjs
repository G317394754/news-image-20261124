// render.mjs -- draw the day's newspaper page as an SVG on stdout.
//
//   node render.mjs > page.svg
//
// Everything on the page is sized from the text itself. Headlines and details
// are wrapped by measured pixel width, not by counting characters, and each
// card is as tall as the lines it actually contains. Nothing is clipped to
// fit a grid: if the copy ever grew past the page, the type scale is stepped
// down and the whole page is measured again rather than cutting a line.
//
// The glyph widths below were measured in Chrome against the same two font
// stacks the SVG uses, and are stored per mille of the em so the table stays
// small integers. Measuring with them agrees with Chrome's own
// getBoundingClientRect to within a couple of pixels per line, which is all
// the wrapping needs; the rasteriser then re-checks the real boxes.

import { readFileSync } from 'node:fs';

const news = JSON.parse(readFileSync(new URL('./news.json', import.meta.url), 'utf8'));

const W = 1024;
const H = 1024;
const MARGIN = 34;                  // white margin around the two columns
const GUTTER = 16;                  // space between the columns
const COL = (W - MARGIN * 2 - GUTTER) / 2;
const INSET = 16;                   // card edge to text
const TEXT_W = COL - INSET * 2;
const MAST_H = 92;
const BODY_TOP = MAST_H + 14;
const FOOT_RULE_Y = H - 36;
const FOOT_TEXT_Y = H - 18;
const STRIP_GAP = 14;               // gap below the strip, above the footer rule
const AVAIL = FOOT_RULE_Y - STRIP_GAP - BODY_TOP;
const MIN_GAP = 10;

// XML attribute values are double quoted, so the font stacks are written with
// single quotes around the family names that contain a space.
const SERIF = "Georgia, 'Times New Roman', serif";
const SANS = 'Helvetica, Arial, sans-serif';

const GLYPHS = " !\"#$%&'()*+,-./0123456789:;<=>?@ABCDEFGHIJKLMNOPQRSTUVWXYZ[\\]^_`abcdefghijklmnopqrstuvwxyz{|}~’‘“”—–";
const WIDTHS = {
  serifBold: [
    254,376,510,703,641,879,799,269,447,447,482,703,328,379,328,472,701,
    490,626,625,649,599,648,554,676,648,367,367,703,703,703,548,967,758,
    757,715,834,721,671,807,913,446,595,817,686,1023,839,820,701,820,797,
    649,684,834,762,1126,809,732,689,447,472,447,703,703,500,596,646,531,
    663,572,393,577,680,354,346,632,344,1016,690,636,658,648,520,513,397,
    677,567,863,588,562,525,500,388,500,703,269,269,519,519,928,703,
  ],
  serif: [
    241,331,412,643,610,817,710,215,375,375,472,643,270,374,270,469,614,
    430,559,552,565,528,566,502,596,566,312,312,643,643,643,479,929,671,
    654,642,749,653,599,725,815,390,518,694,604,927,767,744,610,744,702,
    561,619,756,666,976,710,615,602,375,469,375,643,643,500,504,560,454,
    574,483,325,509,582,293,292,536,286,881,591,539,571,560,410,432,345,
    575,497,737,505,492,444,430,375,430,643,227,227,410,410,857,643,
  ],
  sans: [
    278,278,355,556,556,889,667,191,333,333,389,584,278,333,278,278,556,
    556,556,556,556,556,556,556,556,556,278,278,584,584,584,556,1015,667,
    667,722,722,667,611,778,722,278,500,667,556,833,722,778,667,778,722,
    667,611,722,667,944,667,667,611,278,278,278,469,556,333,556,556,500,
    556,556,278,556,556,222,222,500,222,833,556,556,556,556,333,500,278,
    556,500,722,500,500,500,334,260,334,584,222,222,333,333,1000,556,
  ],
};
const FALLBACK = WIDTHS.sans[GLYPHS.indexOf('a')];

function measure(text, family, size, tracking = 0) {
  const table = WIDTHS[family];
  let perMille = 0;
  for (const ch of text) {
    const at = GLYPHS.indexOf(ch);
    perMille += at < 0 ? FALLBACK : table[at];
  }
  return (perMille * size) / 1000 + tracking * text.length;
}

// Greedy word wrap against a pixel budget. A word longer than the budget
// still gets a line of its own; it is never broken or dropped.
function wrap(text, family, size, budget, tracking = 0) {
  const lines = [];
  let line = '';
  for (const word of text.split(' ')) {
    const candidate = line ? line + ' ' + word : word;
    if (line && measure(candidate, family, size, tracking) > budget) {
      lines.push(line);
      line = word;
    } else {
      line = candidate;
    }
  }
  if (line) lines.push(line);
  return lines;
}

// One escaper for both text nodes and attribute values, so the output is
// always well-formed XML no matter what the copy contains.
const esc = (s) => String(s)
  .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
  .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
const n = (v) => Math.round(v * 100) / 100;

// The page's vector marks. Each sits in a 32x32 box and is drawn in the
// current colour, so a card tints its own mark through the group opacity.
const MARKS = {
  chip: '<rect x="9" y="9" width="14" height="14" rx="2"/><rect x="13" y="13" width="6" height="6"/><path d="M14 3v5M18 3v5M14 24v5M18 24v5M3 14h5M3 18h5M24 14h5M24 18h5"/>',
  tanker: '<path d="M2 21h28l-4 8H7z"/><path d="M8 21V14h16v7"/><path d="M13 14V9h6v5"/><path d="M16 9V5"/><path d="M19 6h5"/><path d="M2 32c3-2 5 2 8 0s5 2 8 0 5 2 8 0"/>',
  burst: '<path d="M16 3l3.4 7.4 8 .9-5.9 5.6 1.5 8.1-7-4.2-7 4.2 1.5-8.1L4.6 11.3l8-.9z"/>',
  drone: '<path d="M8 12l16 8M24 12l-16 8"/><rect x="12" y="13" width="8" height="6" rx="2"/><circle cx="7" cy="11" r="4"/><circle cx="25" cy="11" r="4"/><circle cx="7" cy="21" r="4"/><circle cx="25" cy="21" r="4"/>',
  stars: '<path d="M4 5h24M4 27h24M9 5v22M23 5v22"/><path d="M16 10l1.8 3.8 4.2.5-3.1 2.8.8 4.2-3.7-2.1-3.7 2.1.8-4.2-3.1-2.8 4.2-.5z"/>',
  globe: '<circle cx="16" cy="16" r="12"/><ellipse cx="16" cy="16" rx="5" ry="12"/><path d="M4 16h24M7 8h18M7 24h18"/>',
  scales: '<path d="M16 4v24M9 28h14M5 9h22"/><path d="M5 9l-4 9h8zM27 9l-4 9h8z"/><path d="M1 18a4 4 0 008 0M23 18a4 4 0 008 0"/>',
  chart: '<path d="M4 4v24h24"/><path d="M8 22l6-8 5 4 7-11"/><path d="M21 7h5v5"/>',
  quasar: '<circle cx="16" cy="16" r="3"/><ellipse cx="16" cy="16" rx="12" ry="4.5" transform="rotate(-25 16 16)"/><path d="M16 2v6M16 24v6"/><path d="M9 9l-3-3M23 23l3 3"/>',
  return: '<path d="M9 8L3 15l6 7"/><path d="M3 15h15a9 9 0 010 18h-4"/><path d="M20 26l4 4 6-8"/>',
  rocket: '<path d="M16 2c5 4 7 10 6 16l-6 4-6-4c-1-6 1-12 6-16z"/><circle cx="16" cy="13" r="2.5"/><path d="M10 18l-5 6 6-1M22 18l5 6-6-1"/><path d="M14 24l2 6 2-6"/>',
  flood: '<path d="M3 20l6-7 6 7z"/><path d="M15 20l6-10 8 10z"/><path d="M2 24c3-2 5 2 8 0s5 2 8 0 5 2 8 0 5 2 6 1M2 29c3-2 5 2 8 0s5 2 8 0 5 2 8 0 5 2 6 1"/>',
  fire: '<path d="M16 3c2 6-6 8-6 14a6 6 0 0012 0c0-3-2-4-2-4s4 1 5 5a9 9 0 01-18 0C7 10 13 9 16 3z"/>',
  factory: '<path d="M3 29V14l8 5V14l8 5V9h10v20z"/><path d="M25 9V3h4v6"/><path d="M7 23h3M14 23h3M21 23h3M7 27h3M14 27h3M21 27h3"/>',
};

function mark(name, x, y, size, colour, opacity = 1) {
  return `<g class="mark" transform="translate(${n(x)},${n(y)}) scale(${n(size / 32)})" opacity="${opacity}">`
    + `<g fill="none" stroke="${colour}" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">${MARKS[name] || MARKS.globe}</g></g>`;
}

// A card is planned before it is drawn: the plan records every baseline so
// that drawing is a pure read-out of the measurement.
function planCard(story, scale) {
  const hs = (story.big ? 22 : 20) * scale;
  const ds = (story.big ? 13 : 12.5) * scale;
  const heads = wrap(story.headline, 'serifBold', hs, TEXT_W);
  const dets = wrap(story.detail, 'sans', ds, TEXT_W);
  const headLH = hs * 1.3;
  const detLH = ds * 1.34;
  const headBase = 34 + hs * 0.96;
  const detBase = headBase + (heads.length - 1) * headLH + ds * 1.9;
  const lastDet = detBase + (dets.length - 1) * detLH;
  return { story, hs, ds, heads, dets, headLH, detLH, headBase, detBase, height: lastDet + ds * 0.3 + 14 };
}

function planStrip(scale) {
  const fs = 9 * scale;
  const cellW = (W - MARGIN * 2 - 24) / news.strip.length;
  const budget = cellW - 26 - 10;
  const cells = news.strip.map((s) => ({ story: s, lines: wrap(s.headline, 'sans', fs, budget) }));
  const rows = Math.max(...cells.map((c) => c.lines.length));
  const lh = fs * 1.33;
  const headBase = 46;
  return { cells, cellW, fs, lh, headBase, height: headBase + (rows - 1) * lh + fs * 0.3 + 12 };
}

// Choose the largest type scale whose measured page still fits. The gaps
// (between the rows, and before the strip) soak up whatever is left, so the
// page always ends exactly at the footer rule.
function planPage() {
  const big = news.stories.filter((s) => s.big);
  const small = news.stories.filter((s) => !s.big);
  const pairs = [];
  for (let i = 0; i < big.length; i += 2) pairs.push([big[i], big[i + 1]]);
  if (small.length) pairs.push(small);

  for (let scale = 1.08; scale >= 0.79; scale -= 0.01) {
    const rows = pairs.map((pair) => {
      const plans = pair.map((s) => planCard(s, scale));
      return { plans, height: Math.max(...plans.map((p) => p.height)) };
    });
    const strip = planStrip(scale);
    const used = rows.reduce((a, r) => a + r.height, 0) + strip.height;
    const gap = (AVAIL - used) / rows.length;
    if (gap >= MIN_GAP) return { scale, rows, strip, gap };
  }
  throw new Error('the copy does not fit on one page even at the smallest type scale');
}

const page = planPage();
console.error(`type scale ${page.scale.toFixed(2)}; row gap ${page.gap.toFixed(1)}px; `
  + `rows ${page.rows.map((r) => Math.round(r.height)).join('/')}; strip ${Math.round(page.strip.height)}`);

const out = [];
out.push(`<svg xmlns="http://www.w3.org/2000/svg" width="${W}" height="${H}" viewBox="0 0 ${W} ${H}" font-family="${esc(SANS)}">`);
out.push(`<rect width="${W}" height="${H}" fill="#eef1f6"/>`);
out.push(`<rect x="${MARGIN - 10}" y="0" width="${W - (MARGIN - 10) * 2}" height="${H}" fill="#ffffff"/>`);

// Masthead
out.push(`<rect x="${MARGIN - 10}" y="0" width="${W - (MARGIN - 10) * 2}" height="${MAST_H}" fill="#101620"/>`);
out.push(`<text x="${MARGIN}" y="22" font-family="${esc(SERIF)}" font-size="9.5" letter-spacing="2.6" fill="#7f8ea6">${esc(news.kicker)}</text>`);
out.push(`<text x="${MARGIN}" y="60" font-family="${esc(SERIF)}" font-size="34" font-weight="bold" fill="#ffffff">${esc(news.dateLine)}</text>`);
out.push(`<text x="${MARGIN}" y="81" font-family="${esc(SANS)}" font-size="12" fill="#9fb0c8">${esc(news.standfirst)}</text>`);
out.push(`<g class="mark" transform="translate(866,12)"><g fill="none" stroke="#5b6b82" stroke-width="1.4">`
  + `<circle cx="52" cy="20" r="12"/><ellipse cx="52" cy="20" rx="5" ry="12"/><path d="M40 20h24M44 12h16M44 28h16"/>`
  + `<path d="M14 46h76"/></g><text x="14" y="63" font-family="${esc(SERIF)}" font-size="9" letter-spacing="1.6" fill="#7f8ea6">ONE DAY</text></g>`);

// Cards
let y = BODY_TOP;
for (const row of page.rows) {
  row.plans.forEach((plan, i) => {
    const x = MARGIN + i * (COL + GUTTER);
    const { story } = plan;
    out.push('<g class="card">');
    out.push(`<rect class="panel" x="${n(x)}" y="${n(y)}" width="${n(COL)}" height="${n(row.height)}" rx="7" fill="#ffffff" stroke="#d5d9e0" stroke-width="1"/>`);
    out.push(`<path d="M${n(x)} ${n(y + 7)}a7 7 0 017-7v${n(row.height)}a7 7 0 01-7-7z" fill="${story.accent}"/>`);
    out.push(mark(story.icon, x + INSET, y + 12, 17, story.accent, 0.85));
    out.push(`<text class="region" x="${n(x + INSET + 24)}" y="${n(y + 26)}" font-family="${esc(SERIF)}" font-size="10.5" font-weight="bold" letter-spacing="1.6" fill="${story.accent}">${esc(story.region)}</text>`);
    out.push(`<text class="rank" x="${n(x + COL - INSET)}" y="${n(y + 26)}" text-anchor="end" font-family="${esc(SERIF)}" font-size="10" font-weight="bold" fill="#a8b0bd">${story.rank}</text>`);
    plan.heads.forEach((line, li) => {
      out.push(`<text class="headline" x="${n(x + INSET)}" y="${n(y + plan.headBase + li * plan.headLH)}" font-family="${esc(SERIF)}" font-size="${n(plan.hs)}" font-weight="bold" fill="#14181f">${esc(line)}</text>`);
    });
    plan.dets.forEach((line, li) => {
      out.push(`<text class="detail" x="${n(x + INSET)}" y="${n(y + plan.detBase + li * plan.detLH)}" font-family="${esc(SANS)}" font-size="${n(plan.ds)}" fill="#4a5261">${esc(line)}</text>`);
    });
    out.push('</g>');
  });
  y += row.height + page.gap;
}

// The remaining stories, in one strip along the bottom
const strip = page.strip;
out.push('<g class="strip">');
out.push(`<rect class="panel" x="${MARGIN}" y="${n(y)}" width="${W - MARGIN * 2}" height="${n(strip.height)}" rx="7" fill="#f2f4f8" stroke="#d5d9e0" stroke-width="1"/>`);
strip.cells.forEach((cell, i) => {
  const cx = MARGIN + 12 + i * strip.cellW;
  out.push('<g class="cell">');
  out.push(mark(cell.story.icon, cx, y + 12, 18, cell.story.accent, 0.85));
  out.push(`<text class="region" x="${n(cx + 26)}" y="${n(y + 26)}" font-family="${esc(SERIF)}" font-size="8.5" font-weight="bold" letter-spacing="0.9" fill="${cell.story.accent}">${esc(cell.story.region)}</text>`);
  cell.lines.forEach((line, li) => {
    out.push(`<text class="strip-headline" x="${n(cx + 26)}" y="${n(y + strip.headBase + li * strip.lh)}" font-family="${esc(SANS)}" font-size="${n(strip.fs)}" fill="#3a4150">${esc(line)}</text>`);
  });
  out.push('</g>');
});
out.push('</g>');

out.push(`<path d="M${MARGIN} ${FOOT_RULE_Y}h${W - MARGIN * 2}" stroke="#c9cfd8" stroke-width="1"/>`);
out.push(`<text x="${MARGIN}" y="${FOOT_TEXT_Y}" font-family="${esc(SANS)}" font-size="9.5" fill="#7c8595">${esc(news.footer)}</text>`);
out.push('</svg>');

console.log(out.join('\n'));
