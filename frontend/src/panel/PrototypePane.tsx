import { useEffect, useRef, useState, type ReactNode } from "react";
import { Download, Laptop, Monitor, ShieldCheck, Smartphone, Tablet } from "lucide-react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import type { ChecklistRow, Prototype } from "../api";
import { BEZEL, BROWSER_BAR, devicesFor, fitScale, frameBox, type Device, type DeviceKind } from "../lib/devices";
import { Checklist } from "../thread/confirm/PrototypeSection";
import { useView } from "../ui/view";

const KIND_ICON: Record<DeviceKind, typeof Smartphone> = { phone: Smartphone, tablet: Tablet, laptop: Laptop, desktop: Monitor };
// Space kept under the frame so its bottom edge is not flush with the panel edge.
const BOTTOM_MARGIN = 16;

// The prototype in a doubly isolated frame: sandbox with scripts only (opaque origin, no same-origin
// access) here, plus the server's CSP that refuses every outside request. `previewKey` reloads the frame
// when a new prototype arrives. An app is shown on phones of several sizes, a web site from desktop down
// to mobile; each device is drawn at its real size and scaled to fit, so the prototype gets that viewport.
export default function PrototypePane({ prototype, checklist, previewUrl, previewKey, downloadUrl }: {
  prototype: Prototype | undefined;
  checklist: ChecklistRow[];
  previewUrl: string;
  previewKey: string | number;
  downloadUrl: string | null;
}) {
  const team = useView() === "team";
  const devices = devicesFor(prototype?.platform);
  const [deviceId, setDeviceId] = useState<string | null>(null);
  if (!prototype) {
    return (
      <p className="px-1 py-10 text-center text-sm break-keep text-muted-foreground">
        프로토타입 작성을 승인하면 개발자 에이전트가 만든 프로토타입이 여기에 떠요.
      </p>
    );
  }
  const device = devices.find((d) => d.id === deviceId) ?? devices[prototype.platform === "web" ? 0 : 2];
  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center gap-2">
        <p className="flex min-w-0 flex-1 items-center gap-1.5 text-sm text-muted-foreground">
          <ShieldCheck className="size-4 shrink-0 text-cyan" aria-hidden="true" />
          {prototype.platform === "web" ? "웹사이트" : "앱"} · 안전한 칸 안에서 열려요
          {team && ` · ${prototype.id} · ${prototype.origin === "template" ? "템플릿 대체본" : "개발자 작성"}`}
        </p>
        {downloadUrl && (
          <Button size="sm" asChild>
            <a href={downloadUrl} download>
              <Download /> 내려받기
            </a>
          </Button>
        )}
      </div>
      <DeviceSwitch devices={devices} current={device} onPick={setDeviceId} />
      <DeviceFrame device={device}>
        <iframe
          key={`${previewKey}-${device.id}`}
          className="block h-full w-full border-0 bg-white"
          title={`프로토타입 미리보기 · ${device.full} (격리됨)`}
          sandbox="allow-scripts"
          referrerPolicy="no-referrer"
          src={previewUrl}
        />
      </DeviceFrame>
      <Checklist rows={checklist} missing={prototype.missing_screens} />
    </div>
  );
}

function DeviceSwitch({ devices, current, onPick }: { devices: Device[]; current: Device; onPick: (id: string) => void }) {
  return (
    <div role="radiogroup" aria-label="미리볼 기기" className="flex flex-wrap items-center gap-1 rounded-xl border border-border bg-white/[0.04] p-1">
      {devices.map((d) => {
        const Icon = KIND_ICON[d.kind];
        const on = d.id === current.id;
        return (
          <button
            key={d.id}
            type="button"
            role="radio"
            aria-checked={on}
            title={`${d.full} · ${d.width}×${d.height}`}
            onClick={() => onPick(d.id)}
            className={cn(
              "inline-flex h-8 cursor-pointer items-center gap-1.5 rounded-lg px-2.5 text-xs font-semibold whitespace-nowrap transition-colors outline-none focus-visible:ring-[3px] focus-visible:ring-primary-ring",
              on ? "bg-white/[0.12] text-foreground" : "text-muted-foreground hover:text-foreground",
            )}
          >
            <Icon className="size-3.5" aria-hidden="true" />
            {d.name}
            <span className="font-normal text-faint">{d.width}</span>
          </button>
        );
      })}
    </div>
  );
}

// Height from the frame's top to the bottom of the panel that scrolls it (or the window), minus a margin.
function roomBelow(el: HTMLElement): number {
  let scroller: HTMLElement | null = el.parentElement;
  while (scroller && !/(auto|scroll)/.test(getComputedStyle(scroller).overflowY)) scroller = scroller.parentElement;
  const bottom = scroller ? scroller.getBoundingClientRect().bottom : window.innerHeight;
  return Math.min(bottom, window.innerHeight) - el.getBoundingClientRect().top - BOTTOM_MARGIN;
}

// The device at its real logical size inside a bezel (phone, tablet) or a browser window (laptop, desktop),
// scaled with a transform to the room left in the panel.
function DeviceFrame({ device, children }: { device: Device; children: ReactNode }) {
  const holder = useRef<HTMLDivElement>(null);
  const [scale, setScale] = useState(1);
  useEffect(() => {
    const el = holder.current;
    if (!el) return;
    const measure = () => setScale(fitScale(device, el.clientWidth, roomBelow(el)));
    measure();
    const observer = new ResizeObserver(measure);
    observer.observe(el);
    window.addEventListener("resize", measure);
    return () => {
      observer.disconnect();
      window.removeEventListener("resize", measure);
    };
  }, [device]);
  const box = frameBox(device);
  const bezel = BEZEL[device.kind];
  const browser = device.kind === "laptop" || device.kind === "desktop";
  return (
    <div ref={holder} className="flex w-full flex-col items-center gap-2">
      <div style={{ width: box.width * scale, height: box.height * scale }}>
        <div
          className={cn(
            "flex origin-top-left flex-col overflow-hidden",
            browser
              ? "rounded-xl border border-border-strong bg-white shadow-card"
              : "bg-[#06080f] shadow-[0_0_0_1px_rgb(255_255_255/0.14),0_0_0_5px_rgb(255_255_255/0.035),0_30px_70px_-20px_rgb(0_0_0/0.75)]",
            device.kind === "phone" && "rounded-[3.25rem]",
            device.kind === "tablet" && "rounded-[2.25rem]",
          )}
          style={{ width: box.width, height: box.height, padding: bezel, transform: `scale(${scale})` }}
        >
          {browser && (
            <div className="flex shrink-0 items-center gap-1.5 border-b border-black/10 bg-[#eef0f6] px-3" style={{ height: BROWSER_BAR }} aria-hidden="true">
              <span className="size-2.5 rounded-full bg-[#ff6b6b]" />
              <span className="size-2.5 rounded-full bg-[#f5c04a]" />
              <span className="size-2.5 rounded-full bg-[#4cd08a]" />
            </div>
          )}
          <div
            className={cn(
              "min-h-0 flex-1 overflow-hidden bg-white",
              device.kind === "phone" && "rounded-[2.5rem]",
              device.kind === "tablet" && "rounded-[1.5rem]",
            )}
          >
            {children}
          </div>
        </div>
      </div>
      <p className="text-xs text-faint">
        {device.full} · {device.width}×{device.height} · {Math.round(scale * 100)}%로 보는 중
      </p>
    </div>
  );
}
