import { Codes } from "../../ui/refs";
import { Check, GitBranch, LoaderCircle, Orbit, PenLine, Play, Undo2 } from "lucide-react";
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Notice } from "@/components/ui/notice";
import type { ChangeItem, ChangeRevision, Impact, RequirementText } from "../../api";
import { diffWords, sides, type DiffPart } from "../../lib/diff";
import { withSubject } from "../../lib/labels";
import type { Label } from "../../lib/summarize";
import type { PanelTarget } from "../../panel/types";
import { RefId, useTitles, useView } from "../../ui/view";
import { AgentAvatar } from "../AgentAvatar";
import WorkingRow from "../WorkingRow";
import { impactCount, impactIds, layeredRequirements, type ImpactLayer } from "./model";

const NOTE_TITLE: Partial<Record<ChangeItem["status"], string>> = {
  unmapped: "어느 요구사항인지 찾지 못했어요",
  unrelated: "확정한 요구와 관련 없는 말씀이에요",
  no_change: "이미 그렇게 돼 있어요",
};

export function SaidBubble({ intent, text }: { intent: string; text: string }) {
  return (
    <div className="flex flex-col items-end gap-1 px-3 py-1">
      <p className="text-xs text-muted-foreground">{intent}</p>
      <span className="max-w-[85%] rounded-3xl rounded-tr-lg border border-white/[0.08] bg-white/[0.07] px-4 py-2 text-base break-keep text-foreground">
        {text}
      </span>
    </div>
  );
}

const GROUPS: { key: keyof Impact; label: string }[] = [
  { key: "requirements", label: "요구사항" },
  { key: "screens", label: "화면" },
  { key: "tests", label: "테스트" },
];

const LAYER_TAG: Record<ImpactLayer, string> = { target: "바뀌는 곳", direct: "직접 기댐", transitive: "연결 따라" };

function ImpactList({ item }: { item: ChangeItem }) {
  const titles = useTitles();
  const impact = item.impact!;
  const layers = new Map(layeredRequirements(item).map((r) => [r.id, r.layer]));
  const ordered: Impact = { ...impact, requirements: [...layers.keys()] };
  return (
    <div className="grid gap-3 sm:grid-cols-3">
      {GROUPS.map(({ key, label }) => (
        <div key={key} className="rounded-2xl border border-border bg-white/[0.025] p-3.5">
          <p className="text-sm font-semibold text-foreground">
            {label} <span className="tabular-nums text-muted-foreground">{impact[key].length}</span>
          </p>
          {impact[key].length === 0 ? (
            <p className="mt-1.5 text-sm text-faint">영향 없음</p>
          ) : (
            <ul className="mt-1.5 flex flex-col gap-1">
              {ordered[key].map((id) => {
                const layer = key === "requirements" ? layers.get(id) : undefined;
                return (
                  <li key={id} className={`flex flex-wrap items-center gap-x-1.5 text-sm break-keep ${layer === "transitive" ? "text-faint" : "text-soft"}`}>
                    <span className={layer === "target" ? "font-semibold text-foreground" : undefined}>{titles[id] ?? id}</span>
                    <RefId id={id} />
                    {layer && (
                      <span className={`text-xs whitespace-nowrap ${layer === "transitive" ? "text-faint" : "text-primary-text"}`}>{LAYER_TAG[layer]}</span>
                    )}
                  </li>
                );
              })}
            </ul>
          )}
        </div>
      ))}
    </div>
  );
}

function DiffLine({ parts, side }: { parts: DiffPart[]; side: "before" | "after" }) {
  return (
    <p className="text-base leading-relaxed break-keep text-soft">
      {parts.map((p, i) =>
        p.kind === "same" ? (
          <span key={i}>{p.text}</span>
        ) : side === "before" ? (
          <del key={i} className="rounded bg-[rgb(255_138_138/0.14)] px-0.5 text-destructive decoration-[rgb(255_138_138/0.7)]">
            {p.text}
          </del>
        ) : (
          <ins key={i} className="rounded bg-cyan-soft px-0.5 text-cyan no-underline">
            {p.text}
          </ins>
        ),
      )}
    </p>
  );
}

function Diff({ before, after }: { before: string; after: string }) {
  const { before: b, after: a } = sides(diffWords(before, after));
  return (
    <div className="flex flex-col overflow-hidden rounded-2xl border border-border">
      <div className="flex gap-3 border-b border-border bg-white/[0.02] px-4 py-3">
        <span className="w-10 shrink-0 pt-0.5 text-xs font-semibold text-muted-foreground">지금</span>
        <DiffLine parts={b} side="before" />
      </div>
      <div className="flex gap-3 bg-[rgb(127_227_240/0.04)] px-4 py-3">
        <span className="w-10 shrink-0 pt-0.5 text-xs font-semibold text-cyan">바뀐 뒤</span>
        <DiffLine parts={a} side="after" />
      </div>
    </div>
  );
}

function acceptanceText(r: RequirementText): string {
  const a = r.acceptance;
  return [a.given, a.when, a.then].filter(Boolean).join(" · ");
}

// After CP5: the requirements the PM rewrote so they agree with the change (before → after).
function RevisionList({ revision }: { revision: ChangeRevision }) {
  const titles = useTitles();
  if (revision.requirements.length === 0) return null;
  return (
    <details className="mx-3 rounded-2xl border border-border bg-white/[0.02] px-4 py-3">
      <summary className="cursor-pointer text-sm font-semibold text-foreground">
        변경에 맞춰 고친 요구사항 <span className="tabular-nums text-primary-text">{revision.requirements.length}개</span>
      </summary>
      <ul className="mt-3 flex flex-col gap-4">
        {revision.requirements.map((r) => (
          <li key={r.id} className="flex flex-col gap-2">
            <p className="flex items-center gap-1.5 text-sm font-medium text-soft">
              {titles[r.id] ?? r.after.title} <RefId id={r.id} />
            </p>
            {r.fields.includes("statement") && <Diff before={r.before.statement} after={r.after.statement} />}
            {r.fields.includes("acceptance") && <Diff before={acceptanceText(r.before)} after={acceptanceText(r.after)} />}
          </li>
        ))}
      </ul>
    </details>
  );
}

// FR-21 / CP5: one change request in the thread. Before approval nothing in the source changes.
export default function ChangeCard({ item, label, onOpen, onDecide, onContinue }: {
  item: ChangeItem;
  label: Label;
  onOpen: (t: PanelTarget) => void;
  onDecide?: (approved: boolean, reason?: string) => Promise<void>;
  onContinue?: () => Promise<void>;
}) {
  const team = useView() === "team";
  const titles = useTitles();
  const [rejecting, setRejecting] = useState(false);
  const [reason, setReason] = useState("");
  const [pending, setPending] = useState<"approve" | "reject" | "continue" | null>(null);
  const showGraph = () => onOpen({ tab: "graph", highlight: impactIds(item.impact) });
  const run = async (kind: "approve" | "reject" | "continue", fn: () => Promise<void>) => {
    setPending(kind);
    try {
      await fn();
    } finally {
      setPending(null);
    }
  };
  const said = <SaidBubble intent={item.complaint_ref ? "바꾸고 싶어요 · 「이거 아닌데요」에서 이어짐" : "바꾸고 싶어요"} text={item.utterance} />;

  if (item.status === "mapping") {
    return (
      <div className="flex flex-col gap-1">
        {said}
        <WorkingRow agent="pm" text={`${withSubject(label("pm"))} 어느 요구사항을 바꾸는 말씀인지 찾고 있어요`} />
      </div>
    );
  }
  if (item.status === "unmapped" || item.status === "unrelated" || item.status === "no_change" || item.status === "failed") {
    return (
      <div className="flex flex-col gap-2">
        {said}
        <Notice kind={item.limit ? "reason" : "info"} title={NOTE_TITLE[item.status] ?? "변경 요청을 처리하지 못했어요"} defaultOpen>
          <p className="text-sm break-keep text-soft">{item.error}</p>
          {item.limit && onContinue && (
            <Button className="mt-3" size="sm" disabled={pending !== null} onClick={() => run("continue", onContinue)}>
              {pending === "continue" ? <LoaderCircle className="animate-spin" /> : <Play />} 계속하고 다시 보내기
            </Button>
          )}
        </Notice>
      </div>
    );
  }
  if (item.status === "approved" || item.status === "rejected") {
    const approved = item.status === "approved";
    return (
      <div className="flex flex-col gap-1">
        {said}
        <div className="flex flex-wrap items-center justify-end gap-2 px-3 py-1.5">
          <span className="inline-flex items-center gap-1.5 rounded-full border border-white/[0.08] bg-white/[0.05] px-3.5 py-1.5 text-sm font-medium break-keep text-soft">
            <Check className={approved ? "size-4 shrink-0 text-cyan" : "size-4 shrink-0 text-warning"} aria-hidden="true" />
            {approved
              ? `「${titles[item.target ?? ""] ?? item.title}」 변경을 반영했어요${team ? ` → ${item.version}` : ""} · 다시 볼 것 ${impactCount(item.impact)}개`
              : `변경을 반영하지 않았어요 — ${item.decided?.reason ?? ""}`}
          </span>
          {approved && (
            <Button variant="ghost" size="sm" onClick={showGraph}>
              <Orbit /> 영향 보기
            </Button>
          )}
        </div>
        {approved && item.revision && <RevisionList revision={item.revision} />}
      </div>
    );
  }

  // awaiting_cp5 — the big confirmation card.
  const impact = item.impact!;
  return (
    <div className="flex flex-col gap-3">
      {said}
      <Card className="animate-rise px-8 pt-7 pb-7" aria-labelledby={`cp5-${item.id}`}>
        <p className="flex items-center gap-2 text-sm font-semibold text-primary-text">
          <GitBranch className="size-4" aria-hidden="true" /> <Codes text="변경 체크포인트(CP5) · 바꿀 때마다 1번" />
          {team && <RefId id={item.id} />}
        </p>
        <h2 id={`cp5-${item.id}`} className="mt-3 text-title font-bold tracking-[-0.02em] text-balance break-keep text-foreground">
          「{titles[item.target ?? ""] ?? item.title}」을 이렇게 바꿀까요?
        </h2>
        <p className="mt-2 text-base break-keep text-muted-foreground">
          {team
            ? `승인하면 ${item.target} 진술이 바뀌고 새 버전이 고정돼요(지금 ${item.based_on}). 반려하면 원본은 그대로예요.`
            : "승인하면 바뀐 내용으로 새 버전을 고정해요. 반려하면 지금 그대로 둬요."}
        </p>

        {(item.history?.length ?? 0) > 0 && (
          <Notice kind="info" className="mt-5" title={item.reverts_to ? `${item.reverts_to} 때 내용으로 되돌리는 요청이에요` : "전에도 바뀐 적이 있는 요구사항이에요"} defaultOpen>
            <p className="text-sm break-keep text-soft">
              이 요구사항은 {item.history!.join(", ")}에서 이미 한 번 바뀌었어요.
              {item.reverts_to ? ` 이번 문장은 ${item.reverts_to}에 확정했던 문장과 같아요. 승인하면 그때로 돌아가요.` : " 승인하면 한 번 더 바뀌어요."}
            </p>
          </Notice>
        )}
        <div className="mt-6 flex flex-col gap-5">
          <section aria-label="바뀌는 문장" className="flex flex-col gap-2">
            <h3 className="text-base font-semibold text-foreground">
              바뀌는 문장 <RefId id={item.target ?? ""} />
            </h3>
            <Diff before={item.before ?? ""} after={item.after ?? ""} />
            {team && (item.candidates?.length ?? 0) > 0 && (
              <p className="text-xs break-keep text-muted-foreground">
                Liner 재정렬이 PM에게 준 후보 ·{" "}
                {item.candidates!.map((c) => `${c.id} ${c.score.toFixed(2)}`).join(" · ")} — 고른 것은 PM이에요
              </p>
            )}
          </section>

          <section aria-label="영향받는 것" className="flex flex-col gap-2">
            <div className="flex flex-wrap items-center gap-2">
              <h3 className="text-base font-semibold text-foreground">
                함께 다시 봐야 하는 것 <span className="tabular-nums text-primary-text">{impactCount(impact)}개</span>
              </h3>
              <Button variant="ghost" size="sm" className="ml-auto" onClick={showGraph}>
                <Orbit /> 추적 지도에서 보기
              </Button>
            </div>
            <p className="text-sm break-keep text-muted-foreground">
              바뀌는 요구사항과 그것에 기대는 요구사항, 거기에 연결된 화면·테스트예요. 연결 기록으로 계산했어요.
              「직접 기댐」은 바뀌는 요구사항을 바로 참조하고, 「연결 따라」는 그 뒤로 이어진 것이에요.
            </p>
            <ImpactList item={item} />
          </section>

          <section aria-label="다시 확인할 담당" className="flex flex-col gap-2">
            <h3 className="text-base font-semibold text-foreground">다시 확인할 담당</h3>
            <ul className="flex flex-wrap gap-2">
              {(item.recheck ?? []).map((r) => (
                <li key={r.agent} className="flex items-center gap-2 rounded-full border border-border bg-white/[0.03] py-1 pr-3.5 pl-1">
                  <AgentAvatar id={r.agent} size="sm" />
                  <span className="text-sm text-soft">
                    {label(r.agent)} <span className="text-muted-foreground">{team ? r.items.join(", ") : `${r.items.length}개`}</span>
                  </span>
                </li>
              ))}
            </ul>
            <p className="text-xs break-keep text-faint">영향받은 항목을 맡은 담당만 적었어요. 나머지는 다시 볼 필요가 없어요.</p>
          </section>
        </div>

        <div className="mt-7 border-t border-border pt-6">
          {onDecide ? (
            <div className="flex flex-col gap-4">
              <div className="flex flex-wrap items-center gap-3">
                <Button size="lg" disabled={pending !== null} onClick={() => run("approve", () => onDecide(true))}>
                  {pending === "approve" ? <LoaderCircle className="animate-spin" /> : <Check />} 반영할게요
                </Button>
                {!rejecting && (
                  <Button variant="outline" size="lg" disabled={pending !== null} onClick={() => setRejecting(true)}>
                    <PenLine /> 지금은 그대로 둘게요
                  </Button>
                )}
              </div>
              {rejecting && (
                <form
                  className="flex flex-col gap-2"
                  onSubmit={(e) => {
                    e.preventDefault();
                    if (reason.trim()) void run("reject", () => onDecide(false, reason.trim()));
                  }}
                >
                  <label htmlFor={`cp5-reason-${item.id}`} className="text-sm font-medium text-soft">
                    반영하지 않는 이유를 한 줄로 남겨 주세요. 원본은 그대로예요.
                  </label>
                  <div className="flex items-center gap-2 rounded-2xl border border-border bg-white/[0.03] py-1.5 pr-1.5 pl-4 focus-within:border-primary-text/60">
                    <input
                      id={`cp5-reason-${item.id}`}
                      value={reason}
                      maxLength={200}
                      onChange={(e) => setReason(e.target.value)}
                      placeholder="예) 이번 버전에서는 그대로 두고 다음에 볼게요"
                      className="h-10 min-w-0 flex-1 border-0 bg-transparent p-0 text-base text-foreground outline-none placeholder:text-faint focus-visible:outline-none"
                    />
                    <Button type="submit" variant="secondary" disabled={pending !== null || !reason.trim()}>
                      {pending === "reject" ? <LoaderCircle className="animate-spin" /> : <Undo2 />} 반려하기
                    </Button>
                  </div>
                </form>
              )}
            </div>
          ) : (
            <p className="text-sm text-muted-foreground">녹화 당시 발주사가 여기서 반영 여부를 정했어요.</p>
          )}
        </div>
      </Card>
    </div>
  );
}
