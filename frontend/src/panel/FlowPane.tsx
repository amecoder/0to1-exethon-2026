import { ShieldCheck, Workflow } from "lucide-react";
import { useRef, useState } from "react";
import { Tabs } from "@/components/ui/tabs";
import { cn } from "@/lib/utils";
import type { FlowChart, Swimlane } from "../api";
import { useSize } from "../graph/useMotion";
import { RefId, useView } from "../ui/view";
import { flowViews, shownView, type FlowView } from "./flowViews";
import { flowFit } from "./panelSize";

const FULL_H = "max(28rem, 100vh - 15rem)";
const VIEW_TABS: { value: FlowView; label: string }[] = [
  { value: "lanes", label: "역할별 흐름" },
  { value: "liner", label: "Liner 흐름도" },
];

// S5 flow charts. 「역할별 흐름」 is the role swimlane the server draws from the designer's screen spec, shown as
// an <img> (an SVG image runs no script and loads nothing). 「Liner 흐름도」 is the Liner Visualization chart.
export default function FlowPane({ flow, url, frameKey, lanes, lanesUrl, full = false }: {
  flow: FlowChart | undefined;
  url: string;
  frameKey: string | number;
  lanes?: Swimlane;
  lanesUrl: string;
  full?: boolean;
}) {
  const views = flowViews(lanes, flow);
  const [picked, setPicked] = useState<FlowView | null>(null);
  const view = shownView(views, picked);
  if (!view) {
    return (
      <p className="px-1 py-10 text-center text-sm break-keep text-muted-foreground">
        화면설계서를 다 쓰면 디자이너가 역할별 흐름도와 Liner 시각화 흐름도를 그려 여기에 띄워요.
      </p>
    );
  }
  return (
    <div className="flex flex-col gap-4">
      {views.length > 1 && (
        <Tabs idBase="flow-view" label="흐름도 종류" size="sm" className="self-start"
          items={VIEW_TABS} value={view} onChange={setPicked} />
      )}
      {view === "lanes" && lanes
        ? <LanesView lanes={lanes} url={lanesUrl} full={full} />
        : flow && <LinerView flow={flow} url={url} frameKey={frameKey} full={full} />}
    </div>
  );
}

// Lanes are drawn at their natural size; a narrow panel scrolls sideways, full screen fits the width.
function LanesView({ lanes, url, full }: { lanes: Swimlane; url: string; full: boolean }) {
  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-col gap-1">
        <p className="flex items-center gap-1.5 text-base font-semibold text-foreground">
          <Workflow className="size-4 text-cyan" aria-hidden="true" /> 역할별 흐름도
        </p>
        <p className="text-sm break-keep text-muted-foreground">
          {lanes.lanes.join(" · ")} 중 누가 무엇을 하는지 왼쪽에서 오른쪽 순서로 보여요. 빨간 점선은 실패·취소 같은 예외 갈림이에요.
        </p>
      </div>
      <div className="w-full overflow-x-auto rounded-2xl border border-border-strong bg-white shadow-card">
        <img
          src={url}
          alt={`역할별 흐름도: ${lanes.steps.map((s) => `${s.lane} — ${s.label}`).join(", ")}`}
          className={cn("block h-auto", full ? "w-full" : "max-w-none")}
        />
      </div>
    </div>
  );
}

// Liner Visualization chart in the same isolated frame as the prototype (sandbox with scripts only + the
// server's CSP). Outside stylesheets and fonts were stripped before it was stored.
function LinerView({ flow, url, frameKey, full }: { flow: FlowChart; url: string; frameKey: string | number; full: boolean }) {
  const team = useView() === "team";
  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-col gap-1">
        <p className="flex items-center gap-1.5 text-base font-semibold text-foreground">
          <Workflow className="size-4 text-cyan" aria-hidden="true" /> 사용자 흐름도
          {team && <RefId id={flow.id} />}
        </p>
        {flow.description && <p className="text-sm break-keep text-muted-foreground">{flow.description}</p>}
        <p className="flex items-center gap-1.5 text-sm text-muted-foreground">
          <ShieldCheck className="size-4 shrink-0 text-cyan" aria-hidden="true" />
          안전한 칸 안에서 열려요 · 바깥 글꼴·스타일은 지워서 모양이 단순할 수 있어요
          {team && flow.violations.length > 0 && ` · 지운 외부 자원 ${flow.violations.length}곳`}
        </p>
      </div>
      <FlowFrame url={url} frameKey={frameKey} full={full} />
    </div>
  );
}

const PANEL_H = 28 * 16; // h-[28rem]

// Same frame element in both sizes (so switching to full screen does not reload it). The chart page is drawn
// at FLOW_BASE wide and scaled to the box; a narrow side panel scrolls it sideways at real size instead.
function FlowFrame({ url, frameKey, full }: { url: string; frameKey: string | number; full: boolean }) {
  const box = useRef<HTMLDivElement>(null);
  const fit = flowFit(useSize(box).width, full);
  const height = full ? FULL_H : `${PANEL_H}px`;
  return (
    <div ref={box} className="flex w-full flex-col gap-2">
      {fit.scroll && (
        <p className="text-xs break-keep text-muted-foreground">
          흐름도가 가로로 넓어요. 옆으로 밀어 보거나, 패널을 넓히거나, 「크게 보기」로 한눈에 보세요.
        </p>
      )}
      <div
        className={cn("mx-auto max-w-full rounded-2xl border border-border-strong bg-white shadow-card",
          fit.scroll ? "overflow-x-auto overflow-y-hidden" : "overflow-hidden")}
        style={{ width: fit.scroll ? "100%" : fit.width * fit.scale, height }}
      >
        <iframe
          key={frameKey}
          className="block border-0 bg-white"
          style={{
            width: fit.width,
            height: fit.scale !== 1 ? `calc(${height} / ${fit.scale})` : height,
            transform: fit.scale !== 1 ? `scale(${fit.scale})` : undefined,
            transformOrigin: "0 0",
          }}
          title="사용자 흐름도 (격리됨)"
          sandbox="allow-scripts"
          referrerPolicy="no-referrer"
          src={url}
        />
      </div>
    </div>
  );
}
