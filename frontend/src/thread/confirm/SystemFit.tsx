import { Boxes, CircleCheck, Link2, SquarePlus } from "lucide-react";
import type { Fit, OurSystem, SystemFit } from "../../api";
import { RefId } from "../../ui/view";
import { StatusChip } from "../StatusChip";

const FIT_ICON = { "기능 추가": SquarePlus, 연계: Link2, 재사용: CircleCheck } as const;

// CP1: what the client's own systems already cover. Shown only when a 「우리 시스템 목록」 was given.
export function SystemFitList({ systems, fits }: { systems: OurSystem[]; fits: SystemFit[] }) {
  if (systems.length === 0) return null;
  const count = (fit: Fit) => fits.filter((f) => f.fit === fit).length;
  const [added, linked, reused] = [count("기능 추가"), count("연계"), count("재사용")];
  return (
    <section className="flex flex-col gap-2 rounded-2xl border border-cyan/40 bg-cyan-soft px-4 py-3.5" aria-label="우리 시스템으로 되는 것">
      <h3 className="flex items-center gap-1.5 text-sm font-semibold text-foreground">
        <Boxes className="size-4 text-cyan" aria-hidden="true" /> 만드는 방식 · 우리 시스템 {systems.length}개와 비교했어요
      </h3>
      {fits.length === 0 ? (
        <p className="text-sm break-keep text-soft">가진 시스템으로 되는 부분이 없어서 전부 새로 만들어요.</p>
      ) : (
        <>
          <p className="text-sm break-keep text-soft">
            {[added > 0 && `기존 시스템에 기능 추가 ${added}건`, linked > 0 && `기존 시스템과 연계 ${linked}건`,
              reused > 0 && `이미 있어 그대로 쓰는 것 ${reused}건`].filter(Boolean).join(", ")}. 나머지는 새로 만들어요.
          </p>
          <ul className="flex flex-col gap-1.5">
            {fits.map((f, i) => {
              const Icon = FIT_ICON[f.fit];
              return (
                <li key={i} className="flex items-start gap-2 text-base break-keep text-foreground">
                  <Icon className="mt-1 size-4 shrink-0 text-cyan" aria-hidden="true" />
                  <span className="min-w-0">
                    <b className="font-semibold">{f.name}</b>
                    <span className="mx-1 rounded-md bg-white/10 px-1.5 py-px text-xs font-semibold text-soft">{f.fit}</span>
                    {f.what} {f.status === "미확인" && <StatusChip status="미확인" />} <RefId id={[f.system_ref, ...f.refs]} />
                  </span>
                </li>
              );
            })}
          </ul>
        </>
      )}
    </section>
  );
}

// The requirement's build badge: 「기능 추가 · 주문관리 시스템」. Nothing for 신규 (the default without a list).
export function ChangeBadge({ change, names }: { change?: string; names: string[] }) {
  if (!change || change === "신규" || names.length === 0) return null;
  const Icon = FIT_ICON[change as Fit] ?? Link2;
  return (
    <span className="inline-flex items-center gap-1 rounded-full border border-cyan/40 bg-cyan-soft px-2 py-0.5 text-xs font-semibold break-keep text-foreground">
      <Icon className="size-3.5 text-cyan" aria-hidden="true" />
      {change} · {names.join(", ")}
    </span>
  );
}
