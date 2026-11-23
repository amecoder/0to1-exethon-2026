// Which build a page runs: Vite names the bundle by its content hash (/assets/index-<hash>.js), so a new
// deploy shows up as a different name in index.html.
const BUNDLE = /src="(\/assets\/index-[^"]+\.js)"/;

export function buildOf(html: string): string | null {
  return html.match(BUNDLE)?.[1] ?? null;
}

// True only when both builds are known and differ — an error page or the dev server never asks for a reload.
export function isNewBuild(current: string | null, html: string): boolean {
  const next = buildOf(html);
  return current !== null && next !== null && next !== current;
}
