import { FileCheck2, GitPullRequestArrow, LoaderCircle, Play, Scale } from "lucide-react";
import { useState } from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Notice } from "@/components/ui/notice";
import type { ComplaintDecision, ComplaintItem } from "../../api";
import { withSubject } from "../../lib/labels";
import { plainAcceptance, type Label } from "../../lib/summarize";
import { RefId, useView } from "../../ui/view";
import WorkingRow from "../WorkingRow";
import { SaidBubble } from "./ChangeCard";
import { CP_NO, formatAt } from "./model";
import { Term } from "../../ui/Term";

const COPY = {
  "합의 위반": {
    title: "확정한 내용과 결과물이 달라요",
    lead: "말씀하신 것은 이미 확정한 약속이에요. 결과물이 약속을 지키지 못한 거라, 팀이 확정본대로 고쳐야 해요.",
    badge: "danger" as const,
  },
  "새 변경 요청": {
    title: "확정한 것과 다른 걸 원하세요",
    lead: "확정 기록에는 다르게 적혀 있어요. 약속을 어긴 게 아니라 새로 바꾸는 요청이라, 변경 요청으로 바꿔 영향부터 볼 수 있어요.",
    badge: "warning" as const,
  },
};

const PERCENT = (p: number) => `${Math.round(p * 100)}%`;

// Liner Decisions: the probability of each reading. A spread-out answer (or none) goes to a person.
function DecisionLine({ decision, needsHuman, team }: { decision: ComplaintDecision; needsHuman: boolean; team: boolean }) {
  const probs = decision.probabilities;
  const parts = [["violation", "합의 위반"], ["new_change", "새 변경 요청"]]
    .filter(([key]) => typeof probs[key] === "number")
    .map(([key, name]) => `${name} ${PERCENT(probs[key])}`);
  return (
    <div className="mt-4 flex flex-col gap-2">
      {parts.length > 0 && (
        <p className="text-sm break-keep text-muted-foreground">
          Liner 판정 확률 · {parts.join(" · ")}
          {decision.confidence != null && ` · 확신도 ${PERCENT(decision.confidence)}`}
          {team && decision.model && ` · ${decision.model}`}
        </p>
      )}
      {needsHuman && (
        <Notice kind="info" title="사람 판단 필요 — 판정을 그대로 믿기 어려워요" defaultOpen>
          <p className="text-sm break-keep text-soft">
            {decision.error
              ? decision.error
              : `확신도가 기준(${PERCENT(decision.threshold)})보다 낮아요. 아래 확정 기록을 직접 읽고 정해 주세요.`}
          </p>
        </Notice>
      )}
    </div>
  );
}

// FR-22: 「아 이거 아닌데?」 — the complaint compared with the latest confirmed version, with the record.
export default function ComplaintCard({ item, label, convertible, onConvert, onContinue }: {
  item: ComplaintItem;
  label: Label;
  convertible: boolean;
  onConvert?: () => Promise<void>;
  onContinue?: () => Promise<void>;
}) {
  const team = useView() === "team";
  const [busy, setBusy] = useState(false);
  const run = async (fn: () => Promise<void>) => {
    setBusy(true);
    try {
      await fn();
    } finally {
      setBusy(false);
    }
  };
  const said = <SaidBubble intent="이거 아닌데요" text={item.text} />;

  if (item.status === "checking") {
    return (
      <div className="flex flex-col gap-1">
        {said}
        <WorkingRow agent="qa" text={`${withSubject(label("qa"))} 확정 기록(${item.against})과 맞춰 보고 있어요`} />
      </div>
    );
  }
  if (item.status !== "classified" || !item.classification) {
    return (
      <div className="flex flex-col gap-2">
        {said}
        <Notice kind={item.limit ? "reason" : "info"} title={item.status === "unrelated" ? "확정한 요구와 관련 없는 말씀이에요" : "확정 기록과 맞춰 보지 못했어요"} defaultOpen>
          <p className="text-sm break-keep text-soft">{item.error}</p>
          {item.limit && onContinue && (
            <Button className="mt-3" size="sm" disabled={busy} onClick={() => run(onContinue)}>
              {busy ? <LoaderCircle className="animate-spin" /> : <Play />} 계속하고 다시 보내기
            </Button>
          )}
        </Notice>
      </div>
    );
  }

  const copy = COPY[item.classification];
  return (
    <div className="flex flex-col gap-3">
      {said}
      <Card className="animate-rise px-8 pt-7 pb-7" aria-labelledby={`cmp-${item.id}`}>
        <p className="flex flex-wrap items-center gap-2 text-sm font-semibold text-primary-text">
          <Scale className="size-4" aria-hidden="true" /> 「아 이거 아닌데?」 대조 · 확정본 {item.against} 기준
          {team && <RefId id={item.id} />}
        </p>
        <div className="mt-3 flex flex-wrap items-center gap-3">
          <h2 id={`cmp-${item.id}`} className="text-title font-bold tracking-[-0.02em] text-balance break-keep text-foreground">
            {copy.title}
          </h2>
          <Badge variant={copy.badge} className="text-sm">{item.classification}</Badge>
          {item.needs_human && <Badge variant="warning" className="text-sm">사람 판단 필요</Badge>}
        </div>
        <p className="mt-2 text-base break-keep text-muted-foreground">{copy.lead}</p>
        {item.reason && !(item.guard?.applied && item.model_classification !== item.classification) && (
          <p className="mt-1 text-sm break-keep text-faint">{label("qa")}: {item.reason}</p>
        )}

        {item.decision && <DecisionLine decision={item.decision} needsHuman={Boolean(item.needs_human)} team={team} />}

        <section aria-label="근거" className="mt-6 flex flex-col gap-3">
          <h3 className="flex items-center gap-2 text-base font-semibold text-foreground">
            <FileCheck2 className="size-4 text-cyan" aria-hidden="true" /> 근거 — 확정된 기록
          </h3>
          {(item.evidence ?? []).map((ev) => (
            <div key={ev.requirement.id} className="rounded-2xl border border-border bg-white/[0.025] p-4">
              <p className="flex items-center gap-2 text-sm font-semibold text-foreground">
                {ev.requirement.title} <RefId id={ev.requirement.id} />
              </p>
              <blockquote className="mt-2 border-l-2 border-cyan/60 pl-3 text-base break-keep text-soft">
                {ev.requirement.statement}
              </blockquote>
              {team && ev.requirement.acceptance && (
                <p className="mt-1.5 text-sm break-keep text-muted-foreground"><Term name="인수 조건" />: {plainAcceptance(ev.requirement.acceptance)}</p>
              )}
              {ev.confirmation ? (
                <p className="mt-3 flex flex-wrap items-center gap-x-2 gap-y-1 text-sm text-muted-foreground">
                  <span className="font-medium text-soft">
                    확인 {CP_NO[ev.confirmation.cp] ?? ev.confirmation.cp}에서 {withSubject(ev.confirmation.who)} 승인
                  </span>
                  <span aria-hidden="true">·</span>
                  <time dateTime={ev.confirmation.at}>{formatAt(ev.confirmation.at)}</time>
                  <span aria-hidden="true">·</span>
                  <span>버전 {ev.confirmation.version}</span>
                  {team && <RefId id={[ev.confirmation.id, ev.confirmation.cp]} />}
                </p>
              ) : (
                <p className="mt-3 text-sm text-faint">승인 기록을 찾지 못했어요(녹화 재생에서는 스냅샷이 없어요).</p>
              )}
            </div>
          ))}
        </section>

        {item.guard?.applied && (
          <div className="mt-4">
            <Notice kind="info" title="원하신 것이 확정된 문장에 이미 있어요 — 그래서 합의 위반으로 판정했어요">
              <p className="text-sm break-keep text-soft">{item.guard.detail}</p>
              {team && item.model_classification !== item.classification && (
                <p className="mt-1 text-xs text-muted-foreground">
                  에이전트는 「{item.model_classification}」로 봤지만 코드 검사가 바로잡았어요.
                </p>
              )}
            </Notice>
          </div>
        )}

        {item.classification === "새 변경 요청" && (
          <div className="mt-6 flex flex-wrap items-center gap-3 border-t border-border pt-6">
            {convertible && onConvert ? (
              <Button size="lg" disabled={busy} onClick={() => run(onConvert)}>
                {busy ? <LoaderCircle className="animate-spin" /> : <GitPullRequestArrow />} 변경 요청으로 바꾸기
              </Button>
            ) : (
              <p className="text-sm text-muted-foreground">
                {convertible ? "실제 모드에서는 여기서 변경 요청으로 바꿀 수 있어요." : "변경 요청으로 바꿨어요. 아래에서 영향을 확인해 주세요."}
              </p>
            )}
          </div>
        )}
        {item.classification === "합의 위반" && (
          <p className="mt-6 border-t border-border pt-6 text-sm break-keep text-muted-foreground">
            확정본은 그대로예요. 결과물을 확정본에 맞게 고치는 재작업 배정은 다음 단계에서 이어져요.
          </p>
        )}
      </Card>
    </div>
  );
}
