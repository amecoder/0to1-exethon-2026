import { describe, expect, it } from "vitest";
import { buildOf, isNewBuild } from "./version";

const page = (js: string) => `<html><head><script type="module" crossorigin src="/assets/${js}"></script><link rel="stylesheet" href="/assets/index-Q6.css"></head></html>`;

describe("which build a page runs", () => {
  it("reads the hashed bundle name from index.html", () => {
    expect(buildOf(page("index-eTJU-Izk.js"))).toBe("/assets/index-eTJU-Izk.js");
  });

  it("knows no build in a page without the bundle (dev server, error page)", () => {
    expect(buildOf("<html><body>Internal Server Error</body></html>")).toBeNull();
  });
});

describe("whether a newer build was deployed", () => {
  it("says yes only when both builds are known and they differ", () => {
    expect(isNewBuild("/assets/index-old.js", page("index-new.js"))).toBe(true);
    expect(isNewBuild("/assets/index-same.js", page("index-same.js"))).toBe(false);
  });

  it("stays quiet when either side is unknown, so an error page never asks for a reload", () => {
    expect(isNewBuild(null, page("index-new.js"))).toBe(false);
    expect(isNewBuild("/assets/index-old.js", "<html>502 Bad Gateway</html>")).toBe(false);
  });
});
