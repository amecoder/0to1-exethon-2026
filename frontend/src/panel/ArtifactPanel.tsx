import { Expand, ExternalLink, FileText, MonitorPlay, Network, Orbit, PanelRightClose, Maximize2, Minimize2, Workflow, X } from "lucide-react";
import { useEffect, useRef, useState, type ReactNode } from "react";
import { Button } from "@/components/ui/button";
import { Tabs } from "@/components/ui/tabs";
import { cn } from "@/lib/utils";
import type { ChecklistRow, DocId, DocView, FlowChart, Project, Prototype, Swimlane } from "../api";
import LineageMap from "../graph";
import type { TeamInfo } from "../ui/useTeam";
import { useView } from "../ui/view";
import { WarningCount } from "../thread/confirm/DocTiles";
import { trapTab } from "../ui/focusTrap";
import DocBody from "./DocBody";
import { docFiles, type DocUrl } from "./docFiles";
import { RefJumpProvider } from "../ui/refs";
import { refAnchor } from "../lib/refCatalog";
import FlowPane from "./FlowPane";
import PrototypePane from "./PrototypePane";
import TeamPane from "./TeamPane";
import { clampWidth, presetWidth } from "./panelSize";
import ResizeHandle, { useViewportWidth } from "./ResizeHandle";
import { DOC_NAME, DOC_ORDER, type PanelTab, type PanelTarget, type PanelWidth } from "./types";
import { DOC_READY } from "./useDocuments";

// The artifact side panel (like a canvas next to the chat): the four documents, the sandboxed prototype
// and the trace map (lineage). Sticky beside the thread; closable; two toggle widths (wider for the map) or a
// dragged width; 「크게 보기」 turns the same panel into a full-screen dialog, so the open pane keeps its state.
export default function ArtifactPanel({ project, docs, target, onTarget, width, onWidth, px, onPx, onClose, previewUrl, flowUrl, lanesUrl, downloadUrl, team, onAgent, onPopout, standalone, className, docUrl }: {
  project: Project;
  docs: Record<DocId, DocView> | null;
  target: PanelTarget;
  onTarget: (t: PanelTarget) => void;
  width: PanelWidth;
  onWidth: (w: PanelWidth) => void;
  px: number | null;
  onPx: (px: number) => void;
  onClose: () => void;
  previewUrl: string;
  flowUrl: string;
  lanesUrl: string;
  downloadUrl: string | null;
  team: TeamInfo;
  onAgent?: (agent: string) => void;
  onPopout?: () => void; // open the same tab in a separate browser window (real mode only)
  standalone?: boolean; // this panel is that window: fills it, no resize/close controls
  className?: string;
  docUrl?: DocUrl; // 11-22: each document as PDF / Word / Markdown; absent = no download buttons
}) {
  const view = useView();
  const source = project.source;
  const doc: DocId = target.doc ?? DOC_ORDER.find((id) => DOC_READY[id](source)) ?? "brd";
  const prototypes = (source.prototype as Prototype[] | undefined) ?? [];
  const checklists = (source.qa_checklist as { rows: ChecklistRow[] }[] | undefined) ?? [];
  const protoKey = source.events.filter((e) => e.type === "prototype_built").length;
  const flows = (source.flow_chart as FlowChart[] | undefined) ?? [];
  const flowKey = source.events.filter((e) => e.type === "liner_visualization").length;
  const specs = (source.screen_spec as { swimlane?: Swimlane }[] | undefined) ?? [];
  const lanes = specs[specs.length - 1]?.swimlane;
  const lanesKey = source.events.filter((e) => e.type === "item_written" && e.data.kind === "screen_spec").length;
  const body = useRef<HTMLDivElement>(null);
  const pendingRef = useRef<string | null>(null); // a row to scroll to once its document is shown
  useEffect(() => {
    const id = pendingRef.current;
    pendingRef.current = null;
    if (!(id && flashRow(id))) body.current?.scrollTo({ top: 0 });
  }, [target.tab, doc]);
  // A link inside a document: open the document that lists the item and scroll to its row.
  const jump = (to: DocId, id: string) => {
    if (target.tab === "docs" && to === doc) flashRow(refAnchor(to, id));
    else {
      pendingRef.current = refAnchor(to, id);
      onTarget({ tab: "docs", doc: to });
    }
  };

  const viewport = useViewportWidth();
  const shown = clampWidth(px ?? presetWidth(width, target.tab, viewport), viewport);
  const [expanded, setFull] = useState(false);
  const full = expanded || Boolean(standalone);
  const shell = useRef<HTMLDivElement>(null);
  const wasFull = useRef(false);
  useEffect(() => {
    if (full) shell.current?.querySelector<HTMLElement>("[data-close]")?.focus();
    else if (wasFull.current) shell.current?.querySelector<HTMLElement>("[data-expand]")?.focus();
    wasFull.current = full;
  }, [full]);

  const tabs: { value: PanelTab; label: ReactNode }[] = [
    { value: "docs", label: <><FileText className="size-3.5" aria-hidden="true" />문서</> },
    { value: "flow", label: <><Workflow className="size-3.5" aria-hidden="true" />흐름도</> },
    { value: "prototype", label: <><MonitorPlay className="size-3.5" aria-hidden="true" />프로토타입</> },
    { value: "graph", label: <><Orbit className="size-3.5" aria-hidden="true" />추적 지도</> },
    { value: "team", label: <><Network className="size-3.5" aria-hidden="true" />팀 통신</> },
  ];

  return (
    <div
      ref={shell}
      role={standalone ? "main" : full ? "dialog" : "complementary"}
      aria-modal={expanded ? true : undefined}
      aria-label={standalone ? "결과물" : full ? "결과물 크게 보기" : "결과물 창"}
      style={full ? undefined : { width: shown }}
      onKeyDown={(e) => {
        if (!expanded) return;
        if (e.key === "Escape") {
          e.stopPropagation();
          setFull(false);
          return;
        }
        if (shell.current) trapTab(shell.current, e);
      }}
      className={cn(
        "sticky top-16 flex h-[calc(100vh-4rem)] shrink-0 animate-rise flex-col border-l border-white/[0.08] bg-deep/90 backdrop-blur-xl",
        className,
        expanded && "fixed inset-0 z-40 h-screen w-auto border-l-0 bg-deep/[0.98]",
        standalone && "static h-auto w-full border-l-0",
      )}
    >
      {!full && <ResizeHandle width={shown} viewport={viewport} onResize={onPx} />}
      <div className="flex h-14 shrink-0 items-center gap-2 border-b border-white/[0.07] px-3">
        <Tabs idBase="artifact" label="결과물 종류" items={tabs} value={target.tab} onChange={(tab) => onTarget({ tab, doc: target.doc })} />
        <div className="ml-auto flex items-center gap-1">
          {standalone ? null : expanded ? (
            <Button data-close variant="ghost" size="sm" aria-label="크게 보기 닫기" title="닫기 (Esc)" onClick={() => setFull(false)}>
              <X /> 닫기
            </Button>
          ) : (
            <>
          {onPopout && (
            <Button variant="ghost" size="icon" aria-label="새 창으로 보기" title="새 창으로 보기" onClick={onPopout}>
              <ExternalLink />
            </Button>
          )}
          <Button
            data-expand
            variant="ghost"
            size="icon"
            aria-label="크게 보기"
            title="크게 보기"
            aria-haspopup="dialog"
            onClick={() => setFull(true)}
          >
            <Expand />
          </Button>
          <Button
            variant="ghost"
            size="icon"
            aria-label={width === "wide" ? "창 좁게" : "창 넓게"}
            title={width === "wide" ? "창 좁게" : "창 넓게"}
            onClick={() => onWidth(width === "wide" ? "base" : "wide")}
          >
            {width === "wide" ? <Minimize2 /> : <Maximize2 />}
          </Button>
          <Button variant="ghost" size="icon" aria-label="결과물 창 닫기" title="닫기" onClick={onClose}>
            <PanelRightClose />
          </Button>
            </>
          )}
        </div>
      </div>

      {/* Outer tab panel (문서 · 흐름도 · 프로토타입 · 추적 지도); the documents add their own inner tab list. */}
      <div id="artifact-panel" role="tabpanel" aria-labelledby={`artifact-tab-${target.tab}`} className="flex min-h-0 flex-1 flex-col">
      {target.tab === "docs" && (
        <div className="shrink-0 border-b border-white/[0.06] px-3 py-2">
          <Tabs
            idBase="doc"
            label="문서 고르기"
            size="sm"
            className="max-w-full overflow-x-auto"
            value={doc}
            onChange={(id) => onTarget({ tab: "docs", doc: id })}
            items={DOC_ORDER.map((id) => ({
              value: id,
              disabled: !DOC_READY[id](source),
              label: (
                <>
                  {DOC_NAME[id]}
                  {docs && DOC_READY[id](source) && docs[id].warnings.length > 0 && <WarningCount warnings={docs[id].warnings} />}
                </>
              ),
            }))}
          />
        </div>
      )}

      <div
        ref={body}
        id={target.tab === "docs" ? "doc-panel" : undefined}
        role={target.tab === "docs" ? "tabpanel" : undefined}
        aria-labelledby={target.tab === "docs" ? `doc-tab-${doc}` : undefined}
        tabIndex={target.tab === "graph" ? undefined : 0}
        className={cn("min-h-0 flex-1 outline-none", target.tab === "graph" ? "flex flex-col" : cn("overflow-y-auto py-5", full ? "px-6 sm:px-10 lg:px-16" : "px-5 sm:px-6"))}
      >
        {target.tab === "docs" &&
          (!DOC_READY[doc](source) ? (
            <p className="py-10 text-center text-sm break-keep text-muted-foreground">
              요구사항을 확정하면 팀이 문서 4종을 쓰기 시작해요. 다 쓰면 여기에서 볼 수 있어요.
            </p>
          ) : docs ? (
            <RefJumpProvider onJump={jump}>
              <DocBody key={`${doc}-${view}`} doc={docs[doc]} wide={full} files={docUrl ? docFiles(doc, docUrl) : undefined} />
            </RefJumpProvider>
          ) : (
            <p className="py-10 text-center text-sm text-muted-foreground">문서를 불러오고 있어요…</p>
          ))}
        {target.tab === "flow" && <FlowPane flow={flows[flows.length - 1]} url={flowUrl} frameKey={flowKey} lanes={lanes} lanesUrl={withKey(lanesUrl, lanesKey)} full={full} />}
        {target.tab === "prototype" && (
          <PrototypePane
            prototype={prototypes[prototypes.length - 1]}
            checklist={checklists[checklists.length - 1]?.rows ?? []}
            previewUrl={previewUrl}
            previewKey={protoKey}
            downloadUrl={downloadUrl}
          />
        )}
        {target.tab === "graph" && (
          <LineageMap
            className="min-h-0 flex-1 pt-2"
            source={source}
            events={source.events}
            label={team.label}
            view={view}
            variant="panel"
            maxScale={full ? 1.6 : 1.25}
            highlight={target.highlight}
            focus={target.focus}
            onClearHighlight={() => onTarget({ tab: "graph" })}
            onAgent={onAgent}
          />
        )}
        {target.tab === "team" && <TeamPane project={project} team={team} view={view} onAgent={onAgent} />}
      </div>
      </div>
    </div>
  );
}

// Scroll a document row into view and flash it once. False when the row is not on the page.
function flashRow(id: string): boolean {
  const row = document.getElementById(id);
  if (!row) return false;
  row.scrollIntoView({ block: "center", behavior: "smooth" });
  row.animate?.([{ backgroundColor: "rgb(101 83 245 / 0.35)" }, { backgroundColor: "transparent" }], { duration: 1600 });
  return true;
}

// The lanes SVG is an <img>; a changing query makes it reload after the designer rewrites the screen spec.
function withKey(url: string, key: number): string {
  return `${url}${url.includes("?") ? "&" : "?"}v=${key}`;
}
