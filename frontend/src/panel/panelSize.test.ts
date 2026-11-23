import { describe, expect, it } from "vitest";
import { wrapTarget } from "../ui/focusTrap";
import { clampWidth, dragWidth, flowFit, FLOW_BASE, keyWidth, KEY_STEP, maxWidth, MIN_WIDTH, presetWidth, readWidth, WIDTH_KEY, writeWidth } from "./panelSize";

function memory(seed: Record<string, string> = {}) {
  const data = new Map(Object.entries(seed));
  return {
    data,
    getItem: (k: string) => data.get(k) ?? null,
    setItem: (k: string, v: string) => void data.set(k, v),
    removeItem: (k: string) => void data.delete(k),
  };
}
const broken = () => {
  throw new Error("storage blocked");
};

describe("clampWidth", () => {
  it("keeps the panel between 360px and 80% of the viewport", () => {
    expect(clampWidth(100, 1280)).toBe(MIN_WIDTH);
    expect(clampWidth(2000, 1280)).toBe(1024);
    expect(clampWidth(700.4, 1280)).toBe(700);
    expect(maxWidth(1920)).toBe(1536);
  });

  it("never lets the maximum fall under the minimum on a tiny window", () => {
    expect(maxWidth(300)).toBe(MIN_WIDTH);
    expect(clampWidth(500, 300)).toBe(MIN_WIDTH);
  });
});

describe("presetWidth", () => {
  it("matches the two toggle widths (wider for the trace map)", () => {
    expect(presetWidth("base", "docs", 1920)).toBe(600);
    expect(presetWidth("base", "docs", 1000)).toBe(380);
    expect(presetWidth("wide", "docs", 1280)).toBe(717);
    expect(presetWidth("wide", "graph", 1280)).toBe(922);
    expect(presetWidth("wide", "graph", 1920)).toBe(1024);
  });
});

describe("dragWidth", () => {
  it("grows when the left edge moves left and shrinks when it moves right", () => {
    expect(dragWidth(500, 800, 700, 1280)).toBe(600);
    expect(dragWidth(500, 800, 900, 1280)).toBe(400);
    expect(dragWidth(500, 800, 0, 1280)).toBe(1024);
  });
});

describe("keyWidth", () => {
  it("steps 32px with the arrow keys (left = wider) and ignores other keys", () => {
    expect(keyWidth(500, "ArrowLeft", 1280)).toBe(500 + KEY_STEP);
    expect(keyWidth(500, "ArrowRight", 1280)).toBe(500 - KEY_STEP);
    expect(keyWidth(370, "ArrowRight", 1280)).toBe(MIN_WIDTH);
    expect(keyWidth(1020, "ArrowLeft", 1280)).toBe(1024);
    expect(keyWidth(500, "Enter", 1280)).toBeNull();
  });
});

describe("readWidth / writeWidth", () => {
  it("round-trips a saved width and clears it with null", () => {
    const store = memory();
    writeWidth(() => store, 640);
    expect(store.data.get(WIDTH_KEY)).toBe("640");
    expect(readWidth(() => store)).toBe(640);
    writeWidth(() => store, null);
    expect(readWidth(() => store)).toBeNull();
  });

  it("ignores junk and survives storage that throws", () => {
    expect(readWidth(() => memory({ [WIDTH_KEY]: "wide" }))).toBeNull();
    expect(readWidth(() => memory({ [WIDTH_KEY]: "-5" }))).toBeNull();
    expect(readWidth(broken)).toBeNull();
    expect(() => writeWidth(broken, 500)).not.toThrow();
    const failing = { ...memory(), setItem: broken };
    expect(() => writeWidth(() => failing, 500)).not.toThrow();
  });
});

describe("wrapTarget (focus trap)", () => {
  const items = ["a", "b", "c"];
  it("wraps Tab from the last item and Shift+Tab from the first", () => {
    expect(wrapTarget(items, "c", false)).toBe("a");
    expect(wrapTarget(items, "a", true)).toBe("c");
  });
  it("leaves focus to the browser in the middle and with nothing to focus", () => {
    expect(wrapTarget(items, "b", false)).toBeNull();
    expect(wrapTarget(items, "b", true)).toBeNull();
    expect(wrapTarget([], null, false)).toBeNull();
  });
  it("pulls focus back in when it sits outside the container", () => {
    expect(wrapTarget(items, "z", false)).toBe("a");
    expect(wrapTarget(items, null, true)).toBe("c");
  });
});

describe("flowFit (flow chart frame)", () => {
  it("keeps real size and scrolls sideways in a narrow side panel", () => {
    expect(flowFit(440, false)).toEqual({ scale: 1, width: FLOW_BASE, scroll: true });
    expect(flowFit(0, false)).toEqual({ scale: 1, width: FLOW_BASE, scroll: true });
  });
  it("shrinks to show the whole chart in a narrow full screen", () => {
    expect(flowFit(480, true)).toEqual({ scale: 0.5, width: FLOW_BASE, scroll: false });
  });
  it("scales up to fill a wide box, at most 2×", () => {
    expect(flowFit(1440, false)).toEqual({ scale: 1.5, width: FLOW_BASE, scroll: false });
    expect(flowFit(1440, true)).toEqual({ scale: 1.5, width: FLOW_BASE, scroll: false });
    expect(flowFit(2400, true)).toEqual({ scale: 2, width: FLOW_BASE, scroll: false });
  });
});
