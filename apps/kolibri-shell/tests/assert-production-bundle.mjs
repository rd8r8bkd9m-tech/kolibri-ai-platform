import { readFileSync, readdirSync, statSync } from 'node:fs';
import { resolve } from 'node:path';

const dist = resolve(process.cwd(), 'dist');
const forbidden = [
  '__KOLIBRI_DEV_ESTIMATE_FIXTURE__',
  'fixture-response',
  'гамбургер динамично',
  'estimateVisualFixture',
];

function filesUnder(directory) {
  return readdirSync(directory).flatMap((name) => {
    const path = resolve(directory, name);
    return statSync(path).isDirectory() ? filesUnder(path) : [path];
  });
}

const files = filesUnder(dist);
for (const file of files) {
  const content = readFileSync(file);
  const text = content.toString('utf8');
  for (const marker of forbidden) {
    if (file.includes(marker) || text.includes(marker)) {
      throw new Error(`DEV fixture leaked into production bundle: ${marker} in ${file}`);
    }
  }
}

console.log(`Production bundle is fixture-free (${files.length} files checked).`);
