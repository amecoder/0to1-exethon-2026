import { CircleCheck, CircleDashed } from "lucide-react";
import { Card } from "@/components/ui/card";
import { cn } from "@/lib/utils";
import type { DecisionStatus } from "../api";
import { RefLink } from "../ui/refs";
import { useView } from "../ui/view";
import { decisionHeadline, remainingItems } from "./decisionStatus";

const COUNTS: [keyof DecisionStatus["counts"], string, string][] = [
  ["confirmed", "확정", "text-cyan"],
  ["assumed", "가정 (기본값으로 정한 것, 확인 필요)", "text-warning"],
  ["open", "미결", "text-foreground"],
];

// 결정 현황: how much is settled, which completion level is reached, and what is left (each opens its ref card).
export default function DecisionStatusCard({ status }: { status: DecisionStatus }) {
  const team = useView() === "team";
  const head = decisionHeadline(status);
  const rest = remainingItems(status);
  const Icon = status.decision_done ? CircleCheck : CircleDashed;
  return (
    <Card className="animate-rise px-8 pt-6 pb-6" aria-labelledby="decision-status-title">
      <p className="text-sm font-semibold text-muted-foreground">결정 현황</p>
      <h2 id="decision-status-title" className={cn("mt-2 flex items-center gap-2 text-lg font-bold break-keep", status.decision_done ? "text-cyan" : "text-foreground")}>
        <Icon className="size-5 shrink-0" aria-hidden="true" /> {head.title}
      </h2>
      <p className="mt-1 text-sm break-keep text-muted-foreground">{head.note}</p>
      <ul className="mt-4 flex flex-wrap gap-x-5 gap-y-1 text-sm text-soft">
        {COUNTS.map(([key, label, tone]) => (
          <li key={key}>
            {label} <b className={tone}>{status.counts[key]}</b>
          </li>
        ))}
      </ul>
      <ol className="mt-3 flex flex-wrap gap-x-3 gap-y-1 text-sm text-muted-foreground" aria-label="완료 단계">
        <li className={status.planning_done ? "text-cyan" : undefined}>1. 기획 완료 — 프로토타입 인수(확인 4)</li>
        <li className={status.decision_done ? "text-cyan" : undefined}>2. 결정 완료 — 가정·미결 0건</li>
      </ol>
      {rest.length > 0 && (
        <div className="mt-4 rounded-2xl border border-border bg-white/[0.025] px-4 py-3">
          <p className="text-sm font-medium text-soft">남은 것 {rest.length}건 — 누르면 무엇인지 볼 수 있어요</p>
          <ul className="mt-2 flex flex-wrap gap-x-3 gap-y-1.5 text-sm">
            {rest.map((r) => (
              <li key={r.id} className="flex items-center gap-1 break-keep">
                <span className={r.label === "가정" ? "text-xs text-warning" : "text-xs text-muted-foreground"}>{r.label}</span>
                <RefLink id={r.id} label={team ? undefined : r.title || r.id} />
              </li>
            ))}
          </ul>
        </div>
      )}
    </Card>
  );
}
