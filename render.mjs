#!/usr/bin/env node
// Renders news.json into a 1024x1024 SVG newspaper page.
//
// The page is one composition: a dark masthead that names the day, ten
// story cards in five rows of two, and a pale strip along the bottom that
// carries the remaining four stories in four columns.
//
// Nothing sits on a fixed grid. A card measures its own headline and its
// own body text, and a row is as tall as the taller of the two cards it
// holds, so no line is ever cut to fit a rectangle. Whatever room is left
// over is shared out between the rows, which is why two cards of the same
// row always end on the same line and two different rows need not.

import { readFileSync } from 'node:fs';

const news = JSON.parse(readFileSync(new URL('./news.json', import.meta.url), 'utf8'));

const W = 1024;
const H = 1024;
const M = 34;                // margin of the printed sheet
const MAST_H = 92;           // the masthead band
const CARD_TOP = MAST_H + 9; // top of the first row of cards
const CARD_INSET = 16;       // text inset inside a card
const STRIP_H = 70;          // the strip along the foot of the page
const FOOTER_RULE_Y = 1002;
const FOOTER_TEXT_Y = 1016;
const MIN_GAP = 5;           // the smallest gap two cards may have

const esc = (s) => String(s)
  .replace(/&/g, '&amp;')
  .replace(/</g, '&lt;')
  .replace(/>/g, '&gt;');

// The fourteen marks used on the page. Each is drawn in a 32x32 box at the
// origin and scaled by the caller, so a mark costs no more bytes than the
// shape it needs, and one path set serves every accent colour.
const ICONS = {
  chip: '<rect x="8" y="8" width="16" height="16" rx="2"/><rect x="13" y="13" width="6" height="6" rx="1"/><path d="M12 4v4M20 4v4M12 24v4M20 24v4M4 12h4M4 20h4M24 12h4M24 20h4"/>',
  tanker: '<path d="M3 20h20l3 4v4H3z"/><rect x="6" y="11" width="12" height="9" rx="1"/><path d="M18 13h5v7"/><path d="M2 28c2 0 2-2 4-2s2 2 4 2 2-2 4-2 2 2 4 2 2-2 4-2 2 2 4 2"/>',
  burst: '<path d="M16 3l3.2 7.4 8-1.3-5.4 6 5.4 6-8-1.3L16 27l-3.2-7.2-8 1.3 5.4-6-5.4-6 8 1.3z"/>',
  drone: '<circle cx="16" cy="16" r="5"/><path d="M6 6l6 6M26 6l-6 6M6 26l6-6M26 26l-6-6"/><circle cx="5" cy="5" r="3"/><circle cx="27" cy="5" r="3"/><circle cx="5" cy="27" r="3"/><circle cx="27" cy="27" r="3"/>',
  stars: '<circle cx="16" cy="16" r="4"/><path d="M16 3v3M16 26v3M3 16h3M26 16h3M6.8 6.8l2.1 2.1M23.1 23.1l2.1 2.1M25.2 6.8l-2.1 2.1M8.9 23.1l-2.1 2.1"/><circle cx="16" cy="5" r="1.6"/><circle cx="16" cy="27" r="1.6"/><circle cx="5" cy="16" r="1.6"/><circle cx="27" cy="16" r="1.6"/>',
  globe: '<circle cx="16" cy="16" r="12"/><ellipse cx="16" cy="16" rx="5" ry="12"/><path d="M4 16h24"/>',
  scales: '<path d="M16 5v22M8 27h16"/><path d="M16 8l-9 3M16 8l9 3"/><path d="M7 11l-4 8h8zM25 11l-4 8h8z"/>',
  chart: '<path d="M4 26V6M4 26h24"/><path d="M7 22l5-7 5 4 8-11"/>',
  quasar: '<circle cx="16" cy="16" r="5"/><ellipse cx="16" cy="16" rx="13" ry="5" transform="rotate(-24 16 16)"/><path d="M25 7l2-2M5 25l-2 2"/>',
  return: '<path d="M27 16a11 11 0 1 1-4-8.4"/><path d="M27 4v6h-6"/>',
  rocket: '<path d="M16 3c5 4 7 9 7 14l-4 5h-6l-4-5c0-5 2-10 7-14z"/><circle cx="16" cy="12" r="2.6"/><path d="M9 17l-4 3 1 5 5-2M23 17l4 3-1 5-5-2"/>',
  flood: '<path d="M3 20c3-3 6 3 9 0s6 3 9 0 6 3 8 0"/><path d="M3 26c3-3 6 3 9 0s6 3 9 0 6 3 8 0"/><path d="M12 16l4-9 4 9z"/>',
  fire: '<path d="M16 3c5 5 7 8 7 13a7 7 0 1 1-14 0c0-3 2-5 4-7 0 3 1 4 2 4 1-3 0-7 1-10z"/>',
  factory: '<path d="M3 28V16l7 4v-4l7 4v-4l7 4v8z"/><path d="M7 22v2M12 22v2M17 22v2M22 22v2"/><path d="M12 16V8h8v8"/>'
};

const icon = (name, x, y, size, color) =>
  `<g data-icon="${name}" transform="translate(${x} ${y}) scale(${size / 32})" fill="none" stroke="${color}" stroke-width="2.1" stroke-linecap="round" stroke-linejoin="round">${ICONS[name] || ICONS.globe}</g>`;

// Advance widths, in em, for the two faces on the page. They are rough on
// purpose: a line breaks only when the estimate says the next word would
// not fit, so an over-estimate costs a word or two of space while an
// under-estimate would push text out of its card.
const NARROW = "ijltfrI.,;:'!|()[]{}/\\-";
const WIDE = 'mwMW@%';

function charEm(ch, serif) {
  if (ch === ' ') return 0.27;
  if (ch >= '0' && ch <= '9') return serif ? 0.60 : 0.56;
  if (ch >= 'A' && ch <= 'Z') return serif ? 0.73 : 0.69;
  if (ch >= 'a' && ch <= 'z') {
    if (NARROW.includes(ch)) return 0.34;
    if (WIDE.includes(ch)) return 0.88;
    return serif ? 0.57 : 0.54;
  }
  return 0.36;
}

function textWidth(text, size, serif, tracking = 0) {
  let em = 0;
  for (const ch of text) em += charEm(ch, serif);
  return em * size * (serif ? 1.07 : 1.06) + tracking * text.length;
}

// Greedy wrap. A word that would push the line past maxWidth starts the
// next one, so every line is known to fit its column before it is drawn.
function wrap(text, size, maxWidth, serif, tracking = 0) {
  const words = String(text).split(/\s+/).filter(Boolean);
  const lines = [];
  let line = '';
  for (const word of words) {
    const next = line ? `${line} ${word}` : word;
    if (line && textWidth(next, size, serif, tracking) > maxWidth) {
      lines.push(line);
      line = word;
    } else {
      line = next;
    }
  }
  if (line) lines.push(line);
  return lines.length ? lines : [''];
}

const HEAD_TOP = 52;   // baseline of the first headline line, from the card top
const HEAD_GAP = 9;    // space between the headline block and the body text
const BOTTOM_PAD = 11; // space below the last body line

// A card's natural height. Lead stories get a larger headline than the two
// closing ones; the height follows from how each text actually wraps, and
// the body is never truncated to make a card shorter.
function cardMetrics(story, width) {
  const big = story.big !== false;
  const headSize = big ? 22 : 20;
  const headLead = headSize * 1.23;
  const bodySize = big ? 15.5 : 14.5;
  const bodyLead = bodySize * 1.22;
  const measure = width - CARD_INSET * 2;
  const headLines = wrap(story.headline, headSize, measure, true);
  const bodyLines = wrap(story.detail, bodySize, measure, false);
  const headBlock = HEAD_TOP + headLines.length * headLead;
  const height = headBlock + HEAD_GAP + (bodyLines.length - 1) * bodyLead + bodySize * 0.24 + BOTTOM_PAD;
  return { big, headSize, headLead, bodySize, bodyLead, headLines, bodyLines, headBlock, height };
}

// A story card: the accent rule, the mark and region label on the first
// row, the rank at the right, then the headline in Georgia and the account
// in Helvetica. The card is drawn at the height its row gives it, and its
// texts carry the card's index so the rasteriser can check they stay inside.
function renderCard(story, index, x, y, width, height) {
  const m = cardMetrics(story, width);
  const accent = story.accent;
  const headBase = y + HEAD_TOP;
  const bodyBase = y + m.headBlock + HEAD_GAP;
  const h = height.toFixed(2);
  const parts = [];
  parts.push(`<rect data-card="${index}" x="${x}" y="${y}" width="${width}" height="${h}" rx="7" fill="#ffffff" stroke="#d7dbe2" stroke-width="1.2"/>`);
  parts.push(`<rect x="${x}" y="${y}" width="5" height="${h}" rx="2.5" fill="${accent}"/>`);
  parts.push(icon(story.icon, x + CARD_INSET, y + 10, 16, accent));
  parts.push(`<text data-card="${index}" data-role="region" x="${x + CARD_INSET + 24}" y="${y + 24}" font-family="Georgia, 'Times New Roman', serif" font-size="10.5" font-weight="700" letter-spacing="1.5" fill="${accent}">${esc(story.region)}</text>`);
  parts.push(`<text data-card="${index}" data-role="rank" x="${x + width - CARD_INSET}" y="${y + 24}" text-anchor="end" font-family="Georgia, serif" font-size="10.5" font-weight="700" fill="#a7aeb9">${story.rank}</text>`);
  m.headLines.forEach((line, i) => {
    const by = (headBase + i * m.headLead).toFixed(2);
    parts.push(`<text data-card="${index}" data-role="headline" x="${x + CARD_INSET}" y="${by}" font-family="Georgia, 'Times New Roman', serif" font-size="${m.headSize}" font-weight="700" fill="#151a21">${esc(line)}</text>`);
  });
  m.bodyLines.forEach((line, i) => {
    const by = (bodyBase + i * m.bodyLead).toFixed(2);
    parts.push(`<text data-card="${index}" data-role="body" x="${x + CARD_INSET}" y="${by}" font-family="Helvetica, Arial, sans-serif" font-size="${m.bodySize}" fill="#49515f">${esc(line)}</text>`);
  });
  return `<g>${parts.join('')}</g>`;
}

// The strip: four equal columns under the last row, each with a mark, a
// region label and the headline in small Helvetica.
function renderStrip(items, y, width) {
  const inner = width - 24;
  const colW = inner / items.length;
  const parts = [`<rect x="${M}" y="${y}" width="${width}" height="${STRIP_H}" rx="7" fill="#f1f4f8" stroke="#d7dbe2" stroke-width="1.2"/>`];
  items.forEach((item, i) => {
    const cx = M + 12 + i * colW;
    const cy = y + 11;
    parts.push(icon(item.icon, cx, cy, 18, item.accent));
    parts.push(`<text data-role="strip-region" x="${cx + 24}" y="${cy + 8}" font-family="Georgia, serif" font-size="8.5" font-weight="700" letter-spacing="0.9" fill="${item.accent}">${esc(item.region)}</text>`);
    const lines = wrap(item.headline, 9.5, colW - 32, false).slice(0, 3);
    lines.forEach((line, j) => {
      parts.push(`<text data-role="strip-headline" x="${cx + 24}" y="${(cy + 22 + j * 11.5).toFixed(2)}" font-family="Helvetica, Arial, sans-serif" font-size="9.5" fill="#3f4652">${esc(line)}</text>`);
    });
  });
  return parts.join('');
}

// --- Lay the page out. Rows are paired in source order; a row is as tall
// as the taller of its two cards, which is what keeps the columns level.
const cardWidth = (W - M * 2 - 16) / 2;
const rows = [];
for (let i = 0; i < news.stories.length; i += 2) rows.push([news.stories[i], news.stories[i + 1]]);
const rowHeights = rows.map((pair) =>
  Math.max(cardMetrics(pair[0], cardWidth).height, cardMetrics(pair[1], cardWidth).height));
const rowsTotal = rowHeights.reduce((a, b) => a + b, 0);

const stripY = FOOTER_RULE_Y - 8 - STRIP_H;
const gaps = rows.length + 1;             // between the rows, and above the strip
const gap = (stripY - CARD_TOP - rowsTotal) / gaps;
if (gap < MIN_GAP) {
  console.error(`the page overflows: only ${gap.toFixed(1)}px of gap between cards; shorten a story`);
  process.exit(3);
}
console.error(`layout: rows ${rowHeights.map((h) => h.toFixed(1)).join(' / ')} | gap ${gap.toFixed(1)} | strip ${stripY.toFixed(1)}..${(stripY + STRIP_H).toFixed(1)}`);

let body = '';
let y = CARD_TOP;
rows.forEach((pair, r) => {
  const h = rowHeights[r];
  body += renderCard(pair[0], r * 2, M, y, cardWidth, h);
  body += renderCard(pair[1], r * 2 + 1, M + cardWidth + 16, y, cardWidth, h);
  y += h + gap;
});
body += renderStrip(news.strip, stripY, W - M * 2);
body += `<line x1="${M}" y1="${FOOTER_RULE_Y}" x2="${W - M}" y2="${FOOTER_RULE_Y}" stroke="#c9cfd8" stroke-width="1"/>`;
body += `<text x="${M}" y="${FOOTER_TEXT_Y}" font-family="Helvetica, Arial, sans-serif" font-size="9.5" fill="#7c8595">${esc(news.footer)}</text>`;

const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="${W}" height="${H}" viewBox="0 0 ${W} ${H}" font-family="Helvetica, Arial, sans-serif">
<rect width="${W}" height="${H}" fill="#e8ecf3"/>
<rect x="24" y="0" width="976" height="${H}" fill="#ffffff"/>
<rect x="24" y="0" width="976" height="${MAST_H}" fill="#101620"/>
<text x="${M}" y="23" font-family="Georgia, serif" font-size="9.5" letter-spacing="2.6" fill="#7f8ea6">${esc(news.kicker)}</text>
<text x="${M}" y="58" font-family="Georgia, 'Times New Roman', serif" font-size="34" font-weight="700" fill="#ffffff">${esc(news.dateLine)}</text>
<text x="${M}" y="79" font-family="Helvetica, Arial, sans-serif" font-size="12" fill="#9fb0c8">${esc(news.standfirst)}</text>
<g transform="translate(${W - M - 124} 12)" fill="none" stroke="#3f4c60" stroke-width="1.8">
<circle cx="52" cy="20" r="12"/><ellipse cx="52" cy="20" rx="5" ry="12"/><path d="M40 20h24"/>
<path d="M14 46h76" stroke="#3f4c60" stroke-width="1"/>
<text x="14" y="63" font-family="Georgia, serif" font-size="9" letter-spacing="1.6" fill="#7f8ea6" stroke="none">ONE DAY</text>
</g>
${body}
</svg>`;

process.stdout.write(svg);
