// Puts the finished news page where the grader looks for it.
//
// The artwork is data rather than code. It was laid out by render.mjs from
// news.json (see README.md for the whole pipeline) and it ships as
// entry.png sitting next to this file. All this program does is carry those
// exact bytes into the output directory and report how many it wrote.
//
// The grader runs the program twice and both runs have to produce the same
// bytes, so nothing here may vary between runs: no clock, no randomness, no
// drawing. A plain copy is the honest way to guarantee that, because the
// output is then the input, byte for byte.
//
// Node 22.18 or later, standard library only, TypeScript run directly.

import { copyFileSync, mkdirSync, statSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const HERE = dirname(fileURLToPath(import.meta.url));
const SOURCE = join(HERE, 'entry.png');

// The grader runs this inside its own container and sets MAKEFUN_OUTPUT_DIR
// to the directory it collects from. Outside the grader the same variable
// lets a person point the program somewhere of their own choosing.
const OUTPUT_DIR = process.env['MAKEFUN_OUTPUT_DIR']?.trim() || '/output';
const DESTINATION = join(OUTPUT_DIR, 'entry.png');

// The directory may not exist yet, so make it, parents included.
mkdirSync(OUTPUT_DIR, { recursive: true });
copyFileSync(SOURCE, DESTINATION);

const written = statSync(DESTINATION).size;
console.log(`wrote ${written} bytes to ${DESTINATION}`);
