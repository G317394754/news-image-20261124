// Renders news.json into a 1024x1024 SVG newspaper page.
// The page is one composition: a masthead that names the day, a lead story,
// two supporting leads, then the rest of the field as cards, then a strip.
import { readFileSync } from 'node:fs';

const news = JSON.parse(readFileSync(new URL('./news.json', import.meta.url), 'utf8'));

const W = 1024;
const H = 1024;
const M = 34;
const COL = (W - M * 2 - 16) / 2;

const esc = (s) => String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');

// A small set of flat vector marks. Each is drawn in a 32x32 box at the
// origin and scaled by the caller, so a mark never costs more bytes than
// the shape it needs.
const ICONS = {
  chip: '<rect x="8" y="8" width="16" height="16" rx="2"/><rect x="13" y="13" width="6" height="6" rx="1"/><path d="M12 4v4M20 4v4M12 24v4M20 24v4M4 12h4M4 20h4M24 12h4M24 20h4"/>',
  tanker: '<path d="M3 20h20l3 4v4H3z"/><rect x="6" y="11" width="12" height="9" rx="1"/><path d="M18 13h5v7"/><path d="M2 28c2 0 2-2 4-2s2 2 4 2 2-2 4-2 2 2 4 2 2-2 4-2 2 2 4 2"/>',
  burst: '<path d="M16 3l3.2 7.4 8-1.3-5.4 6 5.4 6-8-1.3L16 27l-3.2-7.2-8 1.3 5.4-6-5.4-6 8 1.3z"/>',
  drone: '<circle cx="16" cy="16" r="5"/><path d="M6 6l6 6M26 6l-6 6M6 26l6-6M26 26l-6-6"/><circle cx="5" cy="5" r="3"/><circle cx="27" cy="5" r="3"/><circle cx="5" cy="27" r="3"/><circle cx="27" cy="27" r="3"/>',
  stars: '<circle cx="16" cy="16" r="4"/><g id="st"><path d="M16 3v3M16 26v3M3 16h3M26 16h3M6.8 6.8l2.1 2.1M23.1 23.1l2.1 2.1M25.2 6.8l-2.1 2.1M8.9 23.1l-2.1 2.1"/></g><circle cx="16" cy="5" r="1.6"/><circle cx="16" cy="27" r="1.6"/><circle cx="5" cy="16" r="1.6"/><circle cx="27" cy="16" r="1.6"/>',
  globe: '<circle cx="16" cy="16" r="12"/><ellipse cx="16" cy="16" rx="5" ry="12"/><path d="M4 16h24"/>',
  scales: '<path d="M16 5v22M8 27h16"/><path d="M16 8l-9 3M16 8l9 3"/><path d="M7 11l-4 8h8zM25 11l-4 8h8z"/>',
  chart: '<path d="M4 26V6M4 26h24"/><path d="M7 22l5-7 5 4 8-11"/>',
  quasar: '<circle cx="16" cy="16" r="5"/><ellipse cx="16" cy="16" rx="13" ry="5" transform="rotate(-24 16 16)"/><path d="M25 7l2-2M5 25l-2 2"/>',
  return: '<path d="M27 16a11 11 0 1 1-4-8.4"/><path d="M27 4v6h-6"/>',
  rocket: '<path d="M16 3c5 4 7 9 7 14l-4 5h-6l-4-5c0-5 2-10 7-14z"/><circle cx="16" cy="12" r="2.6"/><path d="M9 17l-4 3 1 5 5-2M23 17l4 3-1 5-5-2"/>',
  flood: '<path d="M3 20c3-3 6 3 9 0s6 3 9 0 6 3 8 0"/><path d="M3 26c3-3 6 3 9 0s6 3 9 0 6 3 8 0"/><path d="M12 16l4-9 4 9z"/>',
  fire: '<path d="M16 3c5 5 7 8 7 13a7 7 0 1 1-14 0c0-3 2-5 4-7 0 3 1 4 2 4 1-3 0-7 1-10z"/>'
};

const icon = (name, x, y, size, color) =>
  `<g transform="translate(${x} ${y}) scale(${size / 32})" fill="none" stroke="${color}" stroke-width="2.1" stroke-linecap="round" stroke-linejoin="round">${ICONS[name] || ICONS.globe}</g>`;

// A story card. Big stories get a headline in two columns of space; small
// ones are laid out for the lower band. The card measures its own text and
// reports back how many lines it needs, so the caller can size the row.
function wrap(text, maxChars) {
  const words = text.split(' ');
  const lines = [];
  let line = '';
  for (const w of words) {
    if ((line + ' ' + w).trim().length > maxChars && line) { lines.push(line); line = w; }
    else line = (line + ' ' + w).trim();
  }
  if (line) lines.push(line);
  return lines;
}

// Lines the detail may occupy inside a card of the given height. The detail
// block starts below the headline, so the budget depends on the headline's
// own line count.
function detailBudget(headLines, cardH, detSize) {
  const headY = 44;
  const detY = headY + headLines * (bigLH(headLines)) + 9;
  const room = cardH - detY - 10;
  return Math.max(1, Math.floor(room / (detSize + 3.5)));
}

function bigLH(headLines) {
  return headLines > 1 ? 25 : 23;
}

// Trims a detail to the lines that fit, cutting at a word boundary.
function clampDetail(text, maxLines, maxChars) {
  const lines = wrap(text, maxChars);
  if (lines.length <= maxLines) return lines;
  const kept = lines.slice(0, maxLines);
  const last = kept[maxLines - 1];
  kept[maxLines - 1] = last.replace(/\s+\S*$/, '') + '...';
  return kept;
}

// Measures a card's natural height: the header band, the headline as it
// wraps, and the detail as it wraps. Nothing is truncated at this point.
function measure(s) {
  const big = s.big;
  const fs = big ? 21 : 19;
  const maxChars = big ? 27 : 26;
  const lines = wrap(s.headline, maxChars);
  const lh = bigLH(lines.length);
  const detSize = big ? 13 : 12.5;
  const detMax = big ? 50 : 47;
  const detLines = wrap(s.detail, detMax);
  // The header band holds the mark and the region label; the headline
  // starts below it and the detail below the headline.
  const headTop = 48;
  const headH = headTop + lines.length * lh + 8;
  const h = headH + detLines.length * (detSize + 3) + 11;
  return { fs, lines, lh, detSize, detMax, detLines, headH, h, headTop };
}

// Renders a card of the given height, dropping whole detail lines when the
// height cannot hold them all. A dropped line is cut at a word boundary and
// marked with an ellipsis, never left dangling mid-sentence.
//
// The header is two rows: a mark and a region label on the first, the
// headline on the second. The headline therefore never sits under the
// mark, whatever the text measures.
function card(s, x, y, w, h) {
  const accent = s.accent;
  const m = measure(s);
  const maxDetLines = Math.max(1, Math.floor((y + h - 10 - (y + m.headH)) / (m.detSize + 3)));
  const detLines = clampDetail(s.detail, maxDetLines, m.detMax);
  const headY = y + m.headTop;
  const detY = y + m.headH;

  return `
  <g>
    <rect x="${x}" y="${y}" width="${w}" height="${h}" rx="7" fill="#ffffff" stroke="#d5d9e0" stroke-width="1.2"/>
    <rect x="${x}" y="${y}" width="5" height="${h}" rx="2.5" fill="${accent}"/>
    ${icon(s.icon, x + 14, y + 10, 17, accent)}
    <text x="${x + 38}" y="${y + 24}" font-family="Georgia, 'Times New Roman', serif" font-size="10.5" font-weight="700" letter-spacing="1.6" fill="${accent}">${esc(s.region)}</text>
    <text x="${x + w - 16}" y="${y + 24}" text-anchor="end" font-family="Georgia, serif" font-size="10" font-weight="700" fill="#a8b0bd">${s.rank}</text>
    ${m.lines.map((l, i) => `<text x="${x + 15}" y="${headY + i * m.lh}" font-family="Georgia, 'Times New Roman', serif" font-size="${m.fs}" font-weight="700" fill="#14181f">${esc(l)}</text>`).join('')}
    ${detLines.map((l, i) => `<text x="${x + 15}" y="${detY + i * (m.detSize + 3)}" font-family="Helvetica, Arial, sans-serif" font-size="${m.detSize}" fill="#4a5261">${esc(l)}</text>`).join('')}
  </g>`;
}

const big = news.stories.filter((s) => s.big);
const small = news.stories.filter((s) => !s.big);
const strip = news.strip;

let body = '';

// Rows are laid out in pairs. A row is as tall as the taller of its two
// cards, so the two columns line up and no text is cut for the sake of a
// fixed grid. The last row carries the three one-line items of the strip
// under its two cards, so the page has no separate band for them.
const rows = [];
for (let i = 0; i < big.length; i += 2) rows.push([big[i], big[i + 1]]);
rows.push([small[0], small[1]]);

const mastH = 92;
const footerH = 30;
const GAP = 9;

// The strip rides at the foot of the last row, inside the page's width.
const stripH = 50;
const stripOffset = 5;

let y = 0;
for (let r = 0; r < rows.length; r++) {
  const [a, b] = rows[r];
  const last = r === rows.length - 1;
  const h = Math.max(measure(a).h, measure(b).h);
  body += card(a, M, y, COL, h);
  body += card(b, M + COL + 16, y, COL, h);
  y += h + GAP;
}

// --- Strip: three one-line items under the last row.
const stripY = y + stripOffset - GAP;
body += `<rect x="${M}" y="${stripY}" width="${W - M * 2}" height="${stripH}" rx="7" fill="#f2f4f8" stroke="#d5d9e0" stroke-width="1.2"/>`;
strip.forEach((s, i) => {
  const cw = (W - M * 2 - 24) / 3;
  const cx = M + 12 + i * cw;
  body += icon(s.icon, cx, stripY + 11, 18, s.accent);
  body += `<text x="${cx + 25}" y="${stripY + 18}" font-family="Georgia, serif" font-size="9" font-weight="700" letter-spacing="1.2" fill="${s.accent}">${esc(s.region)}</text>`;
  const lines = wrap(s.headline, 33).slice(0, 3);
  lines.forEach((ln, i) => {
    body += `<text x="${cx + 25}" y="${stripY + 30 + i * 10.5}" font-family="Helvetica, Arial, sans-serif" font-size="9" fill="#4a5261">${esc(ln)}</text>`;
  });
});

// The page must fill exactly 1024 pixels. The body lives inside a group
// translated down by the masthead, so the footer line is placed in the
// body's own coordinates.
const bodyBottom = stripY + stripH;
const footerY = H - footerH + 6 - mastH;
const fill = footerY - bodyBottom;
if (fill < 10) {
  console.error(`layout overflows: ${-fill}px past the footer line`);
  process.exit(3);
}
body += `<line x1="${M}" y1="${footerY}" x2="${W - M}" y2="${footerY}" stroke="#c9cfd8" stroke-width="1"/>`;
body += `<text x="${M}" y="${footerY + 16}" font-family="Helvetica, Arial, sans-serif" font-size="9.5" fill="#7c8595">${esc(news.footer)}</text>`;

const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="${W}" height="${H}" viewBox="0 0 ${W} ${H}" font-family="Helvetica, Arial, sans-serif">
<rect width="${W}" height="${H}" fill="#eef1f6"/>
<rect x="${M - 10}" y="0" width="${W - (M - 10) * 2}" height="${H}" fill="#ffffff"/>
<rect x="${M - 10}" y="0" width="${W - (M - 10) * 2}" height="${mastH}" fill="#101620"/>
<text x="${M}" y="24" font-family="Georgia, serif" font-size="9.5" letter-spacing="2.6" fill="#7f8ea6">${esc(news.kicker)}</text>
<text x="${M}" y="58" font-family="Georgia, 'Times New Roman', serif" font-size="34" font-weight="700" fill="#ffffff">${esc(news.dateLine)}</text>
<text x="${M}" y="77" font-family="Helvetica, Arial, sans-serif" font-size="12" fill="#9fb0c8">${esc(news.standfirst)}</text>
<g transform="translate(${W - M - 124} 12)" fill="none" stroke="#3f4c60" stroke-width="1.8">
<circle cx="52" cy="20" r="12"/><ellipse cx="52" cy="20" rx="5" ry="12"/><path d="M40 20h24"/>
<path d="M14 46h76" stroke="#3f4c60" stroke-width="1"/>
<text x="14" y="63" font-family="Georgia, serif" font-size="9" letter-spacing="1.6" fill="#7f8ea6" stroke="none">ONE DAY</text>
</g>
<g transform="translate(${M} ${mastH})">${body}</g>
</svg>`;

process.stdout.write(svg);
