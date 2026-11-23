// Preview devices for the prototype: an app is shown on phones of several sizes, a web site on desktop,
// laptop, tablet and mobile widths. Each frame is laid out at the device's real logical size and scaled
// down (never up) to the room the panel has, so the prototype sees that device's viewport.
export type Platform = "app" | "web";
export type DeviceKind = "phone" | "tablet" | "laptop" | "desktop";

export interface Device {
  id: string;
  name: string; // short label on the switch
  full: string; // what it stands for (tooltip and caption)
  kind: DeviceKind;
  width: number;
  height: number;
}

export const DEVICES: Record<Platform, Device[]> = {
  app: [
    { id: "galaxy-s24", name: "갤럭시 S24", full: "작은 안드로이드 폰", kind: "phone", width: 360, height: 780 },
    { id: "iphone-se", name: "아이폰 SE", full: "작은 아이폰(홈 버튼)", kind: "phone", width: 375, height: 667 },
    { id: "iphone-15", name: "아이폰 15", full: "보통 크기 아이폰", kind: "phone", width: 393, height: 852 },
    { id: "iphone-15-max", name: "Pro Max", full: "큰 아이폰(아이폰 15 Pro Max)", kind: "phone", width: 430, height: 932 },
  ],
  web: [
    { id: "desktop", name: "데스크톱", full: "데스크톱 모니터", kind: "desktop", width: 1440, height: 900 },
    { id: "laptop", name: "노트북", full: "13인치 노트북", kind: "laptop", width: 1280, height: 800 },
    { id: "tablet", name: "태블릿", full: "태블릿 세로(아이패드 Air)", kind: "tablet", width: 820, height: 1180 },
    { id: "mobile", name: "모바일", full: "휴대폰 브라우저", kind: "phone", width: 390, height: 844 },
  ],
};

// Bezel around phones and tablets; a browser bar above laptop and desktop windows.
export const BEZEL: Record<DeviceKind, number> = { phone: 12, tablet: 16, laptop: 0, desktop: 0 };
export const BROWSER_BAR = 32;
// Below this a phone's text gets too small to read (the panel scrolls instead); big screens may shrink more.
export const MIN_SCALE: Record<DeviceKind, number> = { phone: 0.66, tablet: 0.3, laptop: 0.2, desktop: 0.2 };

export function devicesFor(platform: string | undefined): Device[] {
  return DEVICES[platform === "web" ? "web" : "app"];
}

export function frameBox(d: Device): { width: number; height: number } {
  const bezel = BEZEL[d.kind];
  const bar = d.kind === "laptop" || d.kind === "desktop" ? BROWSER_BAR : 0;
  return { width: d.width + bezel * 2, height: d.height + bezel * 2 + bar };
}

export function fitScale(d: Device, availableWidth: number, availableHeight: number): number {
  const box = frameBox(d);
  if (!(availableWidth > 0) || !(availableHeight > 0)) return 1;
  const fit = Math.min(1, availableWidth / box.width, availableHeight / box.height);
  return Math.max(MIN_SCALE[d.kind], Math.round(fit * 1000) / 1000);
}
