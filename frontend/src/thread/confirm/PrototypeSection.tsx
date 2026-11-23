import { Check, CircleDashed, MinusCircle, MonitorPlay, ShieldCheck } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Notice, NoticeList } from "@/components/ui/notice";
import type { ChecklistRow, Prototype } from "../../api";
import type { PanelTarget } from "../../panel/types";
import { RefId, useTitles, useView } from "../../ui/view";
import { prototypeLabel } from "../../lib/bundle";

// CP4 / download: the prototype tile (opens the sandboxed preview in the side panel) + QA's checklist.
export default function PrototypeSection({ prototype, checklist, onOpen }: {
  prototype: Prototype | undefined;
  checklist: ChecklistRow[];
  onOpen: (t: PanelTarget) => void;
}) {
  const team = useView() === "team";
  if (!prototype) return <p className="text-sm text-muted-foreground">프로토타입을 아직 받지 못했어요.</p>;
  const stripped = prototype.violations.filter((v) => v.action === "stripped");
  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center gap-4 rounded-2xl border border-primary-text/30 bg-[linear-gradient(135deg,rgb(101_83_245/0.18),rgb(63_166_216/0.08))] p-4">
        <span className="grid size-12 shrink-0 place-items-center rounded-2xl bg-white/10 text-cyan" aria-hidden="true">
          <MonitorPlay className="size-6" />
        </span>
        <div className="min-w-0 flex-1">
          <p className="text-base font-semibold text-foreground">
            {prototype.origin === "template" ? "화면설계서로 만든 대체본" : `개발자 에이전트가 만든 ${prototypeLabel(prototype.platform)}`}
          </p>
          <p className="text-sm break-keep text-muted-foreground">
            안전한 칸 안에서 열려요 — 바깥으로 나가는 요청은 막혀 있어요
            {team && ` · 원본 ${prototype.based_on} · 시도 ${prototype.attempts}회`}
          </p>
        </div>
        <Button onClick={() => onOpen({ tab: "prototype" })}>직접 눌러 보기</Button>
      </div>
      {prototype.origin === "template" && (
        <Notice kind="info" title="개발자 에이전트의 응답이 두 번 모두 맞지 않아서 대체본을 보여 드려요">
          <p className="text-sm text-soft">화면설계서의 화면과 항목으로 자동으로 만든 페이지예요.</p>
        </Notice>
      )}
      {team && stripped.length > 0 && (
        <p className="flex items-center gap-1.5 text-sm text-muted-foreground">
          <ShieldCheck className="size-4 text-cyan" aria-hidden="true" />
          가드레일 G6: 외부 자원을 부르는 코드 {stripped.length}곳을 지웠어요 ({[...new Set(stripped.map((v) => v.code))].join(", ")})
        </p>
      )}
      <Checklist rows={checklist} missing={prototype.missing_screens} />
    </div>
  );
}

export function Checklist({ rows, missing }: { rows: ChecklistRow[]; missing: string[] }) {
  const titles = useTitles();
  const team = useView() === "team";
  // Tests with a screen are matched against the prototype; the rest (automation, measures…) have nothing
  // to click and are checked another way — listed apart so they do not read as defects.
  const onScreen = rows.filter((r) => r.screens.length > 0);
  const offScreen = rows.filter((r) => r.screens.length === 0);
  const ok = onScreen.filter((r) => r.result === "확인 가능").length;
  const name = (id: string) => (team ? id : titles[id] ?? "화면");
  return (
    <section aria-label="QA 체크리스트" className="rounded-2xl border border-border bg-white/[0.025] p-4">
      <h3 className="flex flex-wrap items-baseline gap-x-2 text-base font-semibold text-foreground">
        QA 체크리스트
        <span className="text-sm font-normal text-muted-foreground">
          화면에서 확인할 테스트 {onScreen.length}건 중 <b className="font-semibold text-cyan">{ok}건</b> 준비됐어요
          {offScreen.length > 0 && ` · 화면 없이 확인 ${offScreen.length}건`}
        </span>
      </h3>
      <p className="mt-0.5 text-xs text-faint">화면이 있는지만 맞춰 봤어요. 실제로 실행해 보는 건 다음 단계예요.</p>
      <ul className="mt-3 flex flex-col gap-1.5">
        {onScreen.map((r) => {
          const good = r.result === "확인 가능";
          return (
            <li key={r.tc_id} className="flex items-start gap-2.5 text-sm break-keep">
              {good ? (
                <Check className="mt-0.5 size-4 shrink-0 text-success" aria-label="확인 가능" />
              ) : (
                <CircleDashed className="mt-0.5 size-4 shrink-0 text-warning" aria-label={r.result} />
              )}
              <span className="min-w-0 text-soft">
                <RefId id={r.tc_id} /> {r.title}
                <span className="text-muted-foreground">
                  {" "}
                  · {r.screens.map((s) => `${name(s.id)}${s.present ? "" : " 빠짐"}`).join(", ")}
                  {!good && ` · ${r.result}`}
                </span>
              </span>
            </li>
          );
        })}
      </ul>
      {offScreen.length > 0 && (
        <details className="group mt-3 rounded-xl bg-white/[0.03] px-3 py-2">
          <summary className="flex cursor-pointer list-none items-center gap-2 text-sm font-medium text-soft">
            <MinusCircle className="size-4 shrink-0 text-faint" aria-hidden="true" />
            화면 없이 확인하는 테스트 {offScreen.length}건
            <span className="text-xs font-normal text-faint">자동 처리·문자 발송처럼 눌러 볼 화면이 없는 것 · 펼치기</span>
          </summary>
          <ul className="mt-2 flex flex-col gap-1.5">
            {offScreen.map((r) => (
              <li key={r.tc_id} className="text-sm break-keep text-soft">
                <RefId id={r.tc_id} /> {r.title}
                {r.reason && <span className="block text-xs text-muted-foreground">화면이 없는 이유 · {r.reason}</span>}
              </li>
            ))}
          </ul>
        </details>
      )}
      {missing.length > 0 && (
        <div className="mt-3">
          <Notice kind="info" title={`프로토타입에 없는 화면 ${missing.length}개`}>
            <NoticeList items={missing.map(name)} />
          </Notice>
        </div>
      )}
    </section>
  );
}
