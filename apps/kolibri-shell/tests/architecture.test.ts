import { readFileSync, readdirSync, statSync } from 'node:fs';
import { describe, expect, it } from 'vitest';

const root = process.cwd();

function filesUnder(directory: string): string[] {
  return readdirSync(directory).flatMap((name) => {
    const path = `${directory}/${name}`;
    return statSync(path).isDirectory() ? filesUnder(path) : [path];
  });
}

describe('Shell architecture boundary', () => {
  const sourceFiles = filesUnder(`${root}/src`);
  const source = sourceFiles
    .filter((path) => /\.(ts|tsx|css)$/.test(path))
    .map((path) => readFileSync(path, 'utf8'))
    .join('\n');

  it('does not import the legacy frontend or register a service worker', () => {
    expect(source).not.toMatch(/(?:\.\.\/)+frontend\//);
    expect(source).not.toContain('navigator.serviceWorker');
    expect(sourceFiles.some((path) => /(?:^|\/)sw\.(?:js|ts)$/.test(path))).toBe(false);
  });

  it('references the approved mascot exactly once in runtime source', () => {
    expect(source.match(/\/kolibri-bird\.png/g)).toHaveLength(1);
    const packageJson = JSON.parse(readFileSync(`${root}/package.json`, 'utf8')) as {
      dependencies: Record<string, string>;
    };
    expect(packageJson.dependencies.react).toMatch(/^\^19/);
  });

  it('keeps composition, transport and domain state in separate modules', () => {
    expect(sourceFiles).toEqual(expect.arrayContaining([
      `${root}/src/api/KolibriHttpClient.ts`,
      `${root}/src/app/KolibriShell.tsx`,
      `${root}/src/model/conversation.ts`,
      `${root}/src/components/Composer.tsx`,
    ]));
    expect(readFileSync(`${root}/src/app/App.tsx`, 'utf8').split('\n').length).toBeLessThan(40);
  });
});
