import { Crosshair, X } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import type { AppEvent } from "../api";
import { withSubject, type View } from "../lib/labels";
import type { Label } from "../lib/summarize";
import LineageDetail from "./LineageDetail";
import {
  buildLineage,
  fixedText,
  KIND_COLOR,
  stagesText,
  highlightOf,
  KIND_KO,
  layoutLineage,
  NODE_H,
  NODE_W,
  nodeName,
  traceOf,
  type LEdge,
  type LNode,
  type NodeKind,
} from "./lineage";
import { useReducedMotion, useSize } from "./useMotion";

const EDGE_COLOR: Record<LEdge["kind"], string> = { ref: "#b3a8ff", change: "#ffb86b", complaint: "#ff8f8f" };

function edgePath(a: { x: number; y: number }, b: { x: number; y: number }): string {
  const ay = a.y + NODE_H / 2;
  const by = b.y + NODE_H / 2;
  if (b.x > a.x) {
    const x1 = a.x + NODE_W;
    const x2 = b.x - 5;
    const dx = (x2 - x1) / 2;
    return `M${x1},${ay} C${x1 + dx},${ay} ${x2 - dx},${by} ${x2},${by}`;
  }
  if (b.x === a.x) {
    const x = a.x + NODE_W;
    const bulge = 16 + Math.min(36, Math.abs(by - ay) / 4);
    return `M${x},${ay} C${x + bulge},${ay} ${x + bulge},${by} ${x + 5},${by}`;
  }
  const x1 = a.x;
  const x2 = b.x + NODE_W + 5;
  return `M${x1},${ay} C${x1 - 48},${ay} ${x2 + 48},${by} ${x2},${by}`;
}

// The trace map as stream lineage: lanes left → right in flow order, directed links, the producing agent
// between lanes. Selecting an item lights where it came from and what depends on it and dims the rest.
export default function LineageMap({ source, events, label, view, variant = "panel", className, highlight: litIds, onClearHighlight, focus, onAgent, maxScale = 1 }: {
  source: Record<string, unknown>;
  events: AppEvent[];
  label: Label;
  view: View;
  variant?: "hero" | "panel";
  className?: string;
  highlight?: string[]; // items lit together (a change request's impact); a selection wins
  onClearHighlight?: () => void;
  focus?: string; // select this item (from an agent log link)
  onAgent?: (agent: string) => void;
  maxScale?: number; // grow past real size to fill a wide panel or the full-screen view
}) {
  const scroller = useRef<HTMLDivElement>(null);
  const size = useSize(scroller);
  const reduced = useReducedMotion();
  const [sel, setSel] = useState<string | null>(null);
  const [hover, setHover] = useState<string | null>(null);
  const [showLoose, setShowLoose] = useState(false);
  const nodeRefs = useRef(new Map<string, HTMLButtonElement>());

  const graph = useMemo(() => buildLineage(source, events), [source, events]);
  const layout = useMemo(() => layoutLineage(graph, { showLoose }), [graph, showLoose]);
  const byId = useMemo(() => new Map(graph.nodes.map((n) => [n.id, n])), [graph]);
  const lit = litIds && litIds.length > 0 ? litIds : null;
  const trace = useMemo(() => (sel ? traceOf(graph, sel) : lit ? highlightOf(graph, lit) : null), [graph, sel, lit]);
  const litNodes = trace ? new Set([...(sel ? [sel] : []), ...trace.up, ...trace.down]) : null;

  useEffect(() => {
    if (sel && !byId.has(sel)) setSel(null);
  }, [byId, sel]);
  useEffect(() => {
    if (!focus || !byId.has(focus)) return;
    setSel(focus);
    if (layout.loose.includes(focus)) setShowLoose(true);
    const t = window.setTimeout(() => {
      const el = nodeRefs.current.get(focus);
      el?.scrollIntoView({ block: "nearest", inline: "center" });
      el?.focus({ preventScroll: true });
    }, 60);
    return () => window.clearTimeout(t);
  }, [focus]); // eslint-disable-line react-hooks/exhaustive-deps

  const minScale = variant === "hero" ? 0.55 : 0.74;
  const scale = size.width > 0 && layout.width > 0 ? Math.max(minScale, Math.min(maxScale, (size.width - 4) / layout.width)) : 1;
  // In the panel (not the small hero map) titles may wrap to two lines instead of being cut.
  const roomy = variant === "panel";
  const name = (id: string) => (byId.has(id) ? nodeName(byId.get(id)!, view) : id);
  const selNode = sel ? byId.get(sel) ?? null : null;
  const hoverNode = hover ? byId.get(hover) ?? null : null;
  const empty = graph.nodes.length === 0;

  return (
    <div
      className={cn("relative flex min-h-0 flex-col", className)}
      // The inline glimpse in the thread is as tall as the map (up to 22rem); the panel fills its space.
      style={variant === "hero" ? { height: Math.min(Math.max(layout.height * scale, 160) + 16, 352) } : undefined}
      onKeyDown={(e) => {
        if (e.key === "Escape" && sel) {
          setSel(null);
          e.stopPropagation();
        }
      }}
    >
      <div className="relative min-h-0 flex-1">
        <div ref={scroller} className="absolute inset-0 overflow-auto" role="group" aria-label={empty ? "추적 지도: 아직 그릴 항목이 없어요" : `추적 지도: 항목 ${graph.nodes.length}개, 연결 ${graph.edges.length}개. 항목을 누르면 온 길과 이어진 길이 밝아져요`}>
          {empty ? (
            <p className="grid h-full min-h-40 place-items-center px-6 text-center text-sm text-muted-foreground">
              팀이 무언가를 쓰기 시작하면 원문에서 오른쪽으로 이어져요
            </p>
          ) : (
            <div className="relative" style={{ width: layout.width * scale, height: layout.height * scale }}>
              <div className="absolute top-0 left-0" style={{ width: layout.width, height: layout.height, transform: `scale(${scale})`, transformOrigin: "0 0" }}>
                <svg width={layout.width} height={layout.height} className="absolute inset-0 overflow-visible" aria-hidden="true">
                  <defs>
                    {(["ref", "change", "complaint"] as const).map((k) => (
                      <marker key={k} id={`arrow-${k}`} viewBox="0 0 8 8" refX="7" refY="4" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
                        <path d="M0,0 L8,4 L0,8 z" fill={EDGE_COLOR[k]} />
                      </marker>
                    ))}
                  </defs>
                  {layout.bandY !== null && (
                    <g>
                      <line x1={8} x2={layout.width - 8} y1={layout.bandY} y2={layout.bandY} stroke="rgba(255,255,255,0.14)" strokeDasharray="4 6" />
                      <text x={10} y={layout.bandY + 16} fill="#ffb86b" fontSize="11" fontWeight={600}>변경·불만</text>
                    </g>
                  )}
                  {graph.edges.map((e) => {
                    const a = layout.pos.get(e.from);
                    const b = layout.pos.get(e.to);
                    if (!a || !b) return null;
                    const on = trace?.edges.has(e.key) ?? false;
                    const dim = trace && !on;
                    const d = edgePath(a, b);
                    const to = byId.get(e.to)!;
                    return (
                      <g key={e.key} opacity={dim ? 0.07 : 1}>
                        <path
                          d={d}
                          fill="none"
                          stroke={EDGE_COLOR[e.kind]}
                          strokeOpacity={on ? 0.95 : 0.4}
                          strokeWidth={on ? 2 : 1.2}
                          strokeDasharray={e.kind === "ref" || on ? undefined : "4 4"}
                          className={on && !reduced ? "lineage-flow" : undefined}
                          markerEnd={`url(#arrow-${e.kind})`}
                        />
                        <path d={d} fill="none" stroke="transparent" strokeWidth={10} style={{ pointerEvents: "stroke" }}>
                          <title>
                            {`${e.agent ? `${label(e.agent)}: ` : ""}${name(e.from)} → ${name(e.to)}${to.stages.length ? ` · ${stagesText(to)}` : ""} · ${fixedText(to)}`}
                          </title>
                        </path>
                      </g>
                    );
                  })}
                </svg>

                {layout.columns.map((c) => (
                  <p key={c.key} className="absolute text-center text-xs font-semibold text-soft" style={{ left: c.x, top: 4, width: NODE_W }}>
                    {c.title}
                  </p>
                ))}
                {layout.chips.map((chip) => {
                  const agent = chip.agent !== "client" && onAgent;
                  return (
                    <button
                      key={`${chip.agent}-${chip.x}`}
                      type="button"
                      disabled={!agent}
                      onClick={() => agent && onAgent(chip.agent)}
                      className="absolute inline-flex h-5 -translate-x-1/2 items-center rounded-full border border-cyan/40 bg-deep px-2 text-[11px] font-medium whitespace-nowrap text-cyan outline-none hover:bg-cyan-soft focus-visible:ring-[3px] focus-visible:ring-primary-ring disabled:cursor-default disabled:border-white/15 disabled:text-muted-foreground"
                      style={{ left: chip.x, top: chip.y }}
                      aria-label={agent ? `${label(chip.agent)} 활동 기록 열기` : `${withSubject(label(chip.agent))} 고름`}
                      title={agent ? `${label(chip.agent)} — 이 칸의 항목을 만든 에이전트. 눌러서 활동 기록 보기` : `${withSubject(label(chip.agent))} 고른 답`}
                    >
                      {label(chip.agent)}
                    </button>
                  );
                })}

                {graph.nodes.map((n) => {
                  const p = layout.pos.get(n.id);
                  if (!p) return null;
                  const dim = litNodes && !litNodes.has(n.id);
                  const selected = n.id === sel;
                  return (
                    <button
                      key={n.id}
                      ref={(el) => {
                        if (el) nodeRefs.current.set(n.id, el);
                        else nodeRefs.current.delete(n.id);
                      }}
                      type="button"
                      aria-pressed={selected}
                        onClick={() => {
                        setHover(null);
                        setSel(selected ? null : n.id);
                      }}
                      onMouseEnter={() => setHover(n.id)}
                      onMouseLeave={() => setHover((h) => (h === n.id ? null : h))}
                      onFocus={(e) => e.currentTarget.matches(":focus-visible") && setHover(n.id)}
                      onBlur={() => setHover((h) => (h === n.id ? null : h))}
                      className={cn(
                        "absolute flex animate-rise flex-col justify-center overflow-hidden rounded-lg border bg-[#0f2163] pr-1.5 pl-2.5 text-left outline-none transition-opacity",
                        "hover:border-white/40 focus-visible:ring-[3px] focus-visible:ring-primary-ring",
                        selected ? "border-white/80 shadow-[0_0_0_2px_rgb(127_227_240/0.5)]" : "border-white/[0.12]",
                        dim && "opacity-25",
                      )}
                      style={{ left: p.x, top: p.y, width: NODE_W, height: NODE_H }}
                    >
                      <span className="absolute inset-y-0 left-0 w-1" style={{ background: KIND_COLOR[n.kind] }} aria-hidden="true" />
                      <span className="flex items-center gap-1 text-[10px] leading-3 text-muted-foreground">
                        {view === "team" ? <code className="font-mono text-[10px] text-primary-text">{n.id}</code> : KIND_KO[n.kind]}
                        {n.tags.map((t) => (
                          <span key={t} className="rounded bg-warning-soft px-1 text-[9px] text-warning">{t}</span>
                        ))}
                      </span>
                      <span
                        className={cn(
                          "font-medium text-foreground",
                          roomy ? "line-clamp-2 text-[11px] leading-[13px] break-keep" : "truncate text-xs leading-4",
                        )}
                      >
                        {n.title}
                      </span>
                    </button>
                  );
                })}
              </div>
              {hoverNode && layout.pos.get(hoverNode.id) && (
                <HoverCard node={hoverNode} at={layout.pos.get(hoverNode.id)!} scale={scale} width={layout.width * scale} label={label} />
              )}
            </div>
          )}
        </div>

        {((selNode && variant === "hero") || (!selNode && lit && trace)) && (
          <div className="pointer-events-none absolute bottom-2 left-3 flex max-w-[calc(100%-1.5rem)]">
            <p className="pointer-events-auto inline-flex max-w-full items-center gap-2 rounded-full border border-border-strong bg-popover/95 py-1 pr-1 pl-3 text-xs text-soft backdrop-blur" role="status">
              <Crosshair className="size-3.5 shrink-0 text-cyan" aria-hidden="true" />
              <span className="truncate">
                {selNode
                  ? `「${nodeName(selNode, view)}」 온 길 ${trace?.up.size ?? 0}개 · 이어진 것 ${trace?.down.size ?? 0}개`
                  : `변경 요청의 영향 ${lit?.length ?? 0}개를 밝혔어요`}
              </span>
              {(selNode || onClearHighlight) && (
                <Button
                  variant="ghost"
                  size="icon"
                  className="size-6 rounded-full"
                  aria-label={selNode ? "선택 풀기" : "영향 강조 끄기"}
                  onClick={() => (selNode ? setSel(null) : onClearHighlight?.())}
                >
                  <X className="size-3.5" />
                </Button>
              )}
            </p>
          </div>
        )}
      </div>

      {variant === "panel" && !empty && (
        <div className="max-h-[40%] shrink-0 overflow-y-auto border-t border-border px-4 py-3">
          {selNode ? (
            <LineageDetail graph={graph} node={selNode} source={source} view={view} label={label} name={name} onAgent={onAgent} onSelect={setSel} onClose={() => setSel(null)} />
          ) : (
            <Legend graph={graph} loose={layout.loose.length} showLoose={showLoose} onLoose={() => setShowLoose((v) => !v)} />
          )}
        </div>
      )}
    </div>
  );
}

function HoverCard({ node, at, scale, width, label }: { node: LNode; at: { x: number; y: number }; scale: number; width: number; label: Label }) {
  const left = Math.min(Math.max(at.x * scale, 4), Math.max(width - 284, 4));
  return (
    <div
      className="pointer-events-none absolute z-20 w-max max-w-[17.5rem] rounded-xl border border-border-strong bg-popover/95 px-3 py-2 text-xs shadow-card backdrop-blur"
      style={{ left, top: (at.y + NODE_H) * scale + 6 }}
      role="tooltip"
    >
      <p className="flex items-center gap-1.5 font-semibold text-foreground">
        <span className="inline-block size-2 rounded-full" style={{ background: KIND_COLOR[node.kind] }} aria-hidden="true" />
        {KIND_KO[node.kind]}
        <code className="font-mono text-[11px] text-primary-text">{node.id}</code>
      </p>
      <p className="mt-1 leading-relaxed break-keep text-soft">{node.detail || node.title}</p>
      <p className="mt-1 text-muted-foreground">
        {node.author ? `만든 이 ${label(node.author)}` : "만든 이 기록 없음"}
        {node.stages.length ? ` · ${stagesText(node)}` : ""}
        {` · ${fixedText(node)}`}
      </p>
    </div>
  );
}

function Legend({ graph, loose, showLoose, onLoose }: { graph: { nodes: LNode[] }; loose: number; showLoose: boolean; onLoose: () => void }) {
  const kinds = (Object.keys(KIND_KO) as NodeKind[]).filter((k) => graph.nodes.some((n) => n.kind === k));
  return (
    <div className="flex flex-wrap items-center gap-x-3.5 gap-y-1.5 text-xs text-muted-foreground">
      <ul className="flex flex-wrap items-center gap-x-3 gap-y-1" aria-label="범례">
        {kinds.map((k) => (
          <li key={k} className="inline-flex items-center gap-1.5">
            <span className="inline-block h-2.5 w-1 rounded-sm" style={{ background: KIND_COLOR[k] }} aria-hidden="true" />
            {KIND_KO[k]} <span className="tabular-nums text-faint">{graph.nodes.filter((n) => n.kind === k).length}</span>
          </li>
        ))}
      </ul>
      <p className="basis-full break-keep">화살표는 만든 순서, 칸 사이 이름표는 그 칸을 만든 에이전트예요. 항목을 누르면 온 길과 이어진 길을 글로 보여 줘요.</p>
      {loose > 0 && (
        <Button variant="ghost" size="sm" className="-ml-2 h-7 text-xs" onClick={onLoose} aria-pressed={showLoose}>
          {showLoose ? `연결 없는 원문 ${loose}줄 숨기기` : `연결 없는 원문 ${loose}줄 보기`}
        </Button>
      )}
    </div>
  );
}
