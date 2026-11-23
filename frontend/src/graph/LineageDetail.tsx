import { ArrowDownRight, ArrowUpLeft, ScrollText, X } from "lucide-react";
import type { ReactNode } from "react";
import { Button } from "@/components/ui/button";
import type { View } from "../lib/labels";
import type { Label } from "../lib/summarize";
import { describePath, fixedText, KIND_COLOR, KIND_KO, pathsOf, stagesText, type LineageGraph, type LNode } from "./lineage";

const PATH_LIMIT = 6;
const LOG_AGENTS = new Set(["coordinator", "fde_lead", "researcher", "pm", "designer", "developer", "qa", "consumer"]);

// The selected item in words: what it is, who made it in which stage and version, and every path into
// it and out of it ("SRC-05 → (PM) → REQ-02 → (디자이너) → SCR-01").
export default function LineageDetail({ graph, node, source, view, label, name, onAgent, onSelect, onClose }: {
  graph: LineageGraph;
  node: LNode;
  source: Record<string, unknown>;
  view: View;
  label: Label;
  name: (id: string) => string;
  onAgent?: (agent: string) => void;
  onSelect: (id: string) => void;
  onClose: () => void;
}) {
  const up = pathsOf(graph, node.id, "up", PATH_LIMIT);
  const down = pathsOf(graph, node.id, "down", PATH_LIMIT);
  const change = node.kind === "CHG"
    ? ((source.changes as Record<string, any>[] | undefined) ?? []).find((c) => c.id === node.id)
    : undefined;
  const impact: string[] = change?.impact ? [...(change.impact.requirements ?? []), ...(change.impact.screens ?? []), ...(change.impact.tests ?? [])] : [];

  return (
    <section aria-label="선택한 항목의 계보" className="flex flex-col gap-2 text-sm">
      <div className="flex items-start gap-2">
        <span className="mt-1 inline-block h-4 w-1 shrink-0 rounded-sm" style={{ background: KIND_COLOR[node.kind] }} aria-hidden="true" />
        <div className="min-w-0 flex-1">
          <p className="text-xs text-muted-foreground">
            {KIND_KO[node.kind]}
            {view === "team" && <code className="ml-1.5 font-mono text-[11px] text-primary-text">{node.id}</code>}
          </p>
          <p className="font-semibold break-keep text-foreground">{node.title}</p>
          {node.detail && node.detail !== node.title && <p className="mt-0.5 text-xs leading-relaxed break-keep text-soft">{node.detail}</p>}
        </div>
        <Button variant="ghost" size="icon" className="size-7 shrink-0" aria-label="선택 풀기" onClick={onClose}>
          <X className="size-4" />
        </Button>
      </div>
      <p className="flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-muted-foreground">
        <span>
          만든 이 <b className="font-semibold text-soft">{node.author ? label(node.author) : "기록 없음"}</b>
        </span>
        {node.author && LOG_AGENTS.has(node.author) && onAgent && (
          <Button variant="ghost" size="sm" className="h-6 px-2 text-xs" onClick={() => onAgent(node.author!)}>
            <ScrollText className="size-3.5" aria-hidden="true" />
            활동 기록
          </Button>
        )}
        {node.stages.length > 0 && <span>· 단계 {stagesText(node)}</span>}
        <span>· {fixedText(node)}</span>
      </p>

      <PathList
        icon={<ArrowUpLeft className="size-3.5 text-cyan" aria-hidden="true" />}
        title="어디서 왔나"
        empty={node.kind === "SRC" ? "발주사가 처음 준 원문이에요" : "이어진 출처가 없어요"}
        paths={up.map((p) => describePath(graph, p, name, label))}
      />
      <PathList
        icon={<ArrowDownRight className="size-3.5 text-cyan" aria-hidden="true" />}
        title="무엇이 기대나"
        empty="아직 이 항목에 기대는 것이 없어요"
        paths={down.map((p) => describePath(graph, p, name, label))}
      />
      {change && impact.length > 0 && (
        <div>
          <p className="text-xs font-semibold text-soft">코드가 계산한 영향 {impact.length}개</p>
          <ul className="mt-1 flex flex-wrap gap-1.5">
            {impact.map((id) => (
              <li key={id}>
                <button
                  type="button"
                  onClick={() => onSelect(id)}
                  className="rounded-md border border-border px-1.5 py-0.5 text-xs text-soft outline-none hover:border-white/30 focus-visible:ring-[3px] focus-visible:ring-primary-ring"
                >
                  {name(id)}
                </button>
              </li>
            ))}
          </ul>
        </div>
      )}
    </section>
  );
}

function PathList({ icon, title, empty, paths }: { icon: ReactNode; title: string; empty: string; paths: string[] }) {
  return (
    <div>
      <p className="flex items-center gap-1.5 text-xs font-semibold text-soft">
        {icon}
        {title}
        {paths.length > 0 && <span className="font-normal text-faint">{paths.length}{paths.length >= PATH_LIMIT ? "+" : ""}갈래</span>}
      </p>
      {paths.length === 0 ? (
        <p className="mt-0.5 text-xs text-muted-foreground">{empty}</p>
      ) : (
        <ul className="mt-1 flex flex-col gap-0.5">
          {paths.map((p) => (
            <li key={p} className="text-xs leading-relaxed break-keep text-foreground">{p}</li>
          ))}
        </ul>
      )}
    </div>
  );
}
