import type { Requirement } from "../../api";
import { plainAcceptance } from "../../lib/summarize";
import { RefId, useView } from "../../ui/view";
import { StatusChip } from "../StatusChip";
import { useRefs } from "../../ui/refs";
import { ChangeBadge } from "./SystemFit";
import { Term } from "../../ui/Term";

// CP2: the requirement list that will be fixed. Client view: title, sentence, "done when" in plain words.
// Team view adds category · priority, Given/When/Then, dependencies and every source link.
export default function RequirementSection({ requirements }: { requirements: Requirement[] }) {
  const assumed = requirements.filter((r) => r.status === "가정");
  return (
    <section className="flex flex-col gap-3" aria-label="요구사항">
      <h3 className="flex items-baseline gap-2 text-base font-semibold text-foreground">
        요구사항 {requirements.length}건
        {assumed.length > 0 && (
          <span className="text-sm font-normal text-muted-foreground">· 기본값으로 채운 것 {assumed.length}건은 「가정」으로 표시했어요</span>
        )}
      </h3>
      <ul className="flex flex-col gap-2">
        {requirements.map((r) => (
          <li key={r.id} className="rounded-2xl border border-border bg-white/[0.025] px-4 py-3.5">
            <RequirementBody r={r} />
          </li>
        ))}
      </ul>
    </section>
  );
}

// One requirement as the client reads it (list row and CP2 deck card share it). In the deck the client's own
// 확정 button is the verdict, so the requirement's 「확정」 basis chip would read as the same word: only
// 가정·미결 chips are shown there (`quietConfirmed`).
export function RequirementBody({ r, quietConfirmed = false }: { r: Requirement; quietConfirmed?: boolean }) {
  const team = useView() === "team";
  const { catalog } = useRefs();
  const systemNames = (r.system_refs ?? []).map((id) => catalog[id]?.title ?? id);
  return (
    <>
      <p className="flex flex-wrap items-center gap-2">
        <RefId id={r.id} />
        <span className="text-base font-semibold break-keep text-foreground">{r.title}</span>
        {!(quietConfirmed && r.status === "확정") && <StatusChip status={r.status} />}
        <ChangeBadge change={r.change} names={systemNames} />
        {team && (
          <span className="text-xs text-muted-foreground">
            {r.category} · 중요도 {r.priority}
            {r.depends_on.length > 0 && ` · 관련 ${r.depends_on.join(", ")}`}
          </span>
        )}
      </p>
      <p className="mt-1 text-sm break-keep text-soft">{r.statement}</p>
      {team ? (
        <p className="mt-2 grid gap-0.5 text-sm break-keep text-muted-foreground">
          <span><b className="font-semibold text-soft">Given</b> {r.acceptance.given}</span>
          <span><b className="font-semibold text-soft">When</b> {r.acceptance.when}</span>
          <span><b className="font-semibold text-soft">Then</b> {r.acceptance.then}</span>
        </p>
      ) : (
        <p className="mt-2 text-sm break-keep text-muted-foreground">
          <span className="text-faint"><Term name="인수 조건" /> · </span>
          {plainAcceptance(r.acceptance)}
        </p>
      )}
      {r.exceptions.length > 0 && (
        <p className="mt-1 text-sm break-keep text-muted-foreground">
          <span className="text-faint">예외 · </span>
          {r.exceptions.join(" / ")}
        </p>
      )}
      {team && (
        <p className="mt-2 flex flex-wrap items-center gap-1 text-xs text-muted-foreground">
          근거 {[...r.source_refs, ...r.evidence_refs, ...r.decision_refs].length === 0 && "없음"}
          {[...r.source_refs, ...r.evidence_refs, ...r.decision_refs].map((id) => (
            <RefId key={id} id={id} />
          ))}
        </p>
      )}
    </>
  );
}
