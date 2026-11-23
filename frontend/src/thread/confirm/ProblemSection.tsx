import { Check, Minus } from "lucide-react";
import { Notice } from "@/components/ui/notice";
import type { Claim, SharedSourceData } from "../../api";
import { Codes } from "../../ui/refs";
import { RefId, useView } from "../../ui/view";
import { StatusChip } from "../StatusChip";
import { AlternativeList } from "./Alternatives";
import { SystemFitList } from "./SystemFit";
import { Term } from "../../ui/Term";

// CP1: the problem as the team understood it (who · what hurts · what "done" means) and the scope.
export default function ProblemSection({ source, onUseExisting, onBuildGap }: {
  source: SharedSourceData;
  onUseExisting?: (alternativeId: string) => Promise<void>;
  onBuildGap?: (alternativeId: string) => Promise<void>;
}) {
  const view = useView();
  const ps = source.problem_statement[0];
  const scope = source.scope[0];
  if (!ps) return <p className="text-sm text-muted-foreground">팀이 정리한 문제가 아직 없어요.</p>;
  const all = [...ps.claims, ...ps.interpretations, ...(scope?.in ?? []), ...(scope?.out ?? [])];
  const unverified = all.some((c) => c.status === "미확인");
  const weak = all.filter((c) => c.support_note).length;
  return (
    <div className="flex flex-col gap-5">
      <AlternativeList items={source.alternatives ?? []} onUse={onUseExisting} onGap={onBuildGap} />
      <SystemFitList systems={source.systems ?? []} fits={scope?.systems ?? []} />
      <dl className="grid gap-px overflow-hidden rounded-2xl border border-border bg-border">
        {(
          [
            ["누가", ps.who],
            ["무엇이 불편한가요", ps.pain],
            ["성공 기준", ps.done],
          ] as const
        ).map(([term, value]) => (
          <div key={term} className="grid gap-1 bg-raised px-4 py-3 sm:grid-cols-[9rem_1fr] sm:gap-4">
            <dt className="text-sm text-muted-foreground"><Term name={term} /></dt>
            <dd className="text-base font-medium break-keep text-foreground"><Codes text={value} /></dd>
          </div>
        ))}
      </dl>

      {scope && (
        <div className="grid gap-3 sm:grid-cols-2">
          <ScopeList title="이번에 하는 것" items={scope.in} positive />
          <ScopeList title="이번에 하지 않는 것" items={scope.out} />
        </div>
      )}

      {(ps.claims.length > 0 || ps.interpretations.length > 0) && (
        <div className="flex flex-col gap-3">
          <ClaimList title="메모에서 확인한 사실" items={ps.claims} />
          <ClaimList title="메모를 이렇게 이해했어요" items={ps.interpretations} />
        </div>
      )}
      {weak > 0 && (
        <Notice kind="info" title={`근거가 문장을 잘 뒷받침하는지 확률이 낮은 문장이 ${weak}개 있어요`}>
          <p className="text-sm break-keep text-soft">
            글자는 메모·출처와 그대로 맞아서 「확인」으로 두었어요. Liner 판정이 뜻까지 맞는지는 낮게 봤으니 한 번 더 읽어 보세요.
          </p>
        </Notice>
      )}
      {unverified && view === "client" && (
        <p className="text-sm text-muted-foreground">
          「미확인」은 메모·출처와 글자가 그대로 맞지 않아서 아직 사실로 굳히지 않은 문장이에요.
        </p>
      )}
    </div>
  );
}

function ScopeList({ title, items, positive }: { title: string; items: Claim[]; positive?: boolean }) {
  const Icon = positive ? Check : Minus;
  return (
    <section className="rounded-2xl border border-border bg-white/[0.025] p-4" aria-label={title}>
      <h3 className="text-sm font-semibold text-muted-foreground">{title}</h3>
      <ul className="mt-2 flex flex-col gap-1.5">
        {items.length === 0 && <li className="text-sm text-faint">없어요</li>}
        {items.map((c, i) => (
          <li key={i} className="flex items-start gap-2 text-base break-keep text-foreground">
            <Icon className={positive ? "mt-1 size-4 shrink-0 text-cyan" : "mt-1 size-4 shrink-0 text-faint"} aria-hidden="true" />
            <span className="min-w-0">
              {c.text} {c.status === "미확인" && <StatusChip status="미확인" />} <RefId id={c.refs} />
              <SupportNote claim={c} />
            </span>
          </li>
        ))}
      </ul>
    </section>
  );
}

function ClaimList({ title, items }: { title: string; items: Claim[] }) {
  const team = useView() === "team";
  if (items.length === 0) return null;
  return (
    <section aria-label={title}>
      <h3 className="text-sm font-semibold text-muted-foreground">{title}</h3>
      <ul className="mt-1.5 flex flex-col gap-1">
        {items.map((c, i) => (
          <li key={i} className="text-sm break-keep text-soft">
            {c.text} {c.status === "미확인" && <StatusChip status="미확인" />} <RefId id={c.refs} />
            {team && c.quote && <span className="ml-1 text-faint">— 인용 “{c.quote}”</span>}
            <SupportNote claim={c} />
          </li>
        ))}
      </ul>
    </section>
  );
}

function SupportNote({ claim }: { claim: Claim }) {
  if (!claim.support_note) return null;
  return <span className="mt-0.5 block text-xs break-keep text-muted-foreground">{claim.support_note}</span>;
}
