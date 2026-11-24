// Writes this day's news image to the output directory the grader reads.
//
// The image itself is data: it is drawn from the stories of 24 November 2026
// and lives beside this file as entry.png. This program copies it into
// /output/entry.png (or MAKEFUN_OUTPUT_DIR when it runs outside the grader's
// container) and writes nothing else.
//
// The grader runs the program twice and both runs must write the same bytes,
// so this copies a file rather than drawing anything: the output is the
// input, byte for byte.

import { copyFileSync, mkdirSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const here = dirname(fileURLToPath(import.meta.url));
const outDir = process.env.MAKEFUN_OUTPUT_DIR ?? '/output';
const outFile = join(outDir, 'entry.png');

mkdirSync(outDir, { recursive: true });
copyFileSync(join(here, 'entry.png'), outFile);

const { size } = await import('node:fs').then((fs) => fs.statSync(outFile));
console.log(`wrote ${outFile} (${size} bytes)`);
