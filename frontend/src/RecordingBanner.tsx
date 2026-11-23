import { TriangleAlert } from "lucide-react";
import type { DemoMeta } from "./api";
import { formatUsd } from "./lib/credits";
import { formatDuration } from "./lib/timing";

// Recording time is stored in UTC; show the viewer's local date (KST for the contest).
function localDate(iso: string): string {
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? iso.slice(0, 10) : d.toLocaleDateString("ko-KR");
}

// Always visible while replaying: this is a recording, from when, and (for the stand-in) that it is fake.
export default function RecordingBanner({ meta }: { meta: DemoMeta | null }) {
  return (
    <div
      className="sticky top-16 z-20 flex min-h-10 flex-wrap items-center gap-x-3 gap-y-1 border-b border-white/[0.07] bg-deep/85 px-5 py-2 text-sm backdrop-blur-md"
      role="status"
    >
      <span className="inline-flex items-center gap-2 font-semibold text-foreground">
        <span className="size-2 rounded-full bg-destructive shadow-[0_0_8px_rgb(255_138_138/0.8)]" aria-hidden="true" />
        실제 실행 기록 재생
      </span>
      <span className="text-muted-foreground">녹화일 {meta ? localDate(meta.recorded_at) : "…"}</span>
      {meta?.kind === "fake" && (
        <span className="inline-flex items-center gap-1.5 rounded-full bg-warning-soft px-2.5 py-0.5 font-medium text-warning">
          <TriangleAlert className="size-3.5" aria-hidden="true" /> 주의: {meta.notice}
        </span>
      )}
      {meta?.kind === "real" && <RealRunFacts meta={meta} />}
      {meta?.kind === "real" && meta.operator_note && (
        <span className="rounded-full bg-white/[0.06] px-2.5 py-0.5 text-muted-foreground">{meta.operator_note}</span>
      )}
      <span className="ml-auto text-muted-foreground">
        재생은 Liner API를 호출하지 않아요{meta?.kind !== "real" && meta?.model ? ` · 녹화 모델 ${meta.model}` : ""}
      </span>
    </div>
  );
}

// A recording exported from a real web run: which models answered, what it cost, how long it took.
function RealRunFacts({ meta }: { meta: DemoMeta }) {
  const models = meta.models?.length ? meta.models.join(", ") : meta.model;
  const facts = [
    models ? `답한 모델 ${models}` : null,
    meta.total_cost_usd != null ? `총 비용 ${formatUsd(meta.total_cost_usd)}` : null,
    meta.duration_seconds != null ? `걸린 시간 ${formatDuration(meta.duration_seconds)}` : null,
  ].filter(Boolean);
  return (
    <span className="inline-flex flex-wrap items-center gap-x-2 rounded-full bg-cyan-soft px-2.5 py-0.5 font-medium text-cyan">
      실제 실행 기록
      {facts.map((f) => (
        <span key={f}>· {f}</span>
      ))}
    </span>
  );
}

