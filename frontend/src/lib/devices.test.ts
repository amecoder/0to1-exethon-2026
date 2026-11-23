import { describe, expect, it } from "vitest";
import { DEVICES, MIN_SCALE, devicesFor, fitScale, frameBox } from "./devices";

describe("devices", () => {
  it("shows phones for an app and desktop to mobile widths for a web site", () => {
    expect(devicesFor("app").map((d) => d.kind)).toEqual(["phone", "phone", "phone", "phone"]);
    expect(devicesFor("web").map((d) => d.width)).toEqual([1440, 1280, 820, 390]);
    expect(devicesFor(undefined)).toBe(DEVICES.app);
  });

  it("keeps the real size when there is room and shrinks to the tighter side", () => {
    const phone = DEVICES.app[2];
    const box = frameBox(phone);
    expect(box).toEqual({ width: 393 + 24, height: 852 + 24 });
    expect(fitScale(phone, 2000, 2000)).toBe(1);
    expect(fitScale(phone, box.width * 0.8, 3000)).toBe(0.8);
    const desktop = DEVICES.web[0];
    expect(frameBox(desktop).height).toBe(900 + 32);
    expect(fitScale(desktop, 720, 2000)).toBe(0.5);
  });

  it("never goes below a readable size and survives an unmeasured box", () => {
    expect(fitScale(DEVICES.app[0], 50, 50)).toBe(MIN_SCALE.phone);
    expect(fitScale(DEVICES.web[0], 50, 50)).toBe(MIN_SCALE.desktop);
    expect(fitScale(DEVICES.app[0], 0, 0)).toBe(1);
    expect(fitScale(DEVICES.app[0], Number.NaN, 500)).toBe(1);
  });
});
