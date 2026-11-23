import { Bot, CircleAlert, Download, FileText, MonitorPlay, PackageCheck, RotateCcw, Braces, LoaderCircle, Presentation, Workflow } from "lucide-react";
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import type { Pipeline, Todo } from "../api";
import { CONFIRM_RULE } from "../brand";
import { Codes } from "../ui/refs";
import { STAGE_TITLE } from "../lib/labels";
import { bundleContents, type BundleKind } from "../lib/bundle";
import type { PanelTarget } from "../panel/types";
import { useView } from "../ui/view";

const ICONS: Record<BundleKind, typeof FileText> = {
  prototype: MonitorPlay, docs: FileText, lanes: Workflow, agents: Bot, proposal: Presentation, source: Braces,
};

// CP1 build-or-buy: the client took an existing product, so the team stops before writing requirements.
export function ClosedCard({ todo }: { todo: Extract<Todo, { kind: "closed" }> }) {
  const alt = todo.alternative;
  return (
    <Card className="animate-rise px-8 pt-7 pb-7" aria-labelledby="closed-title">
      <p className="flex items-center gap-2 text-sm font-semibold text-cyan">
        <PackageCheck className="size-4" aria-hidden="true" /> 새로 만들지 않기로 했어요
      </p>
      <h2 id="closed-title" className="mt-3 text-title font-bold tracking-[-0.02em] break-keep text-foreground">
        「{todo.chosen ?? "기존 제품"}」을 쓰기로 하고 여기서 마쳤어요
      </h2>
      <p className="mt-2 text-base break-keep text-muted-foreground">
        요구사항과 문서는 만들지 않았어요. 이 결정은 기록에 남아 있어서, 나중에 모자란 점이 생기면 새 프로젝트로 다시 시작하면 돼요.
      </p>
      {alt && (
        <dl className="mt-5 grid gap-1 rounded-2xl border border-border bg-white/[0.025] p-4 text-sm break-keep sm:grid-cols-[6rem_1fr]">
          <dt className="text-cyan">되는 것</dt>
          <dd className="text-soft">{alt.covers || "—"}</dd>
          <dt className="text-warning">안 되는 것</dt>
          <dd className="text-soft">{alt.lacks || "확인한 빈틈이 없어요"}</dd>
        </dl>
      )}
      {alt?.url && (
        <Button className="mt-5" variant="outline" size="lg" asChild>
          <a href={alt.url} target="_blank" rel="noreferrer noopener">출처 열어 보기</a>
        </Button>
      )}
    </Card>
  );
}

// After CP4: everything in one zip. In demo replay the zip is rebuilt from the recording (marked as such).
export function DownloadCard({ downloadUrl, demo, onOpen, platform, hasLanes }: {
  downloadUrl: string | null; demo?: boolean; onOpen: (t: PanelTarget) => void; platform?: string; hasLanes: boolean;
}) {
  return (
    <Card className="animate-rise overflow-hidden px-8 pt-7 pb-7" aria-labelledby="done-title">
      <p className="flex items-center gap-2 text-sm font-semibold text-cyan">
        <PackageCheck className="size-4" aria-hidden="true" /> 체크포인트 4개를 모두 마쳤어요
      </p>
      <h2 id="done-title" className="mt-3 text-title font-bold tracking-[-0.02em] break-keep text-foreground">
        결과물을 내려받으세요
      </h2>
      <p className="mt-2 text-base break-keep text-muted-foreground">
        zip 하나에 모두 들어 있어요. 기본값으로 채운 것과 아직 정하지 않은 것은 문서마다 맨 위에 적어 두었어요.
      </p>
      <p className="mt-1 text-sm break-keep text-faint"><Codes text={CONFIRM_RULE} /> — 바꾸고 싶으면 아래 입력창에 적어 주세요.</p>
      <ul className="mt-5 flex flex-col gap-2">
        {bundleContents(platform, hasLanes).map(({ kind, text }) => {
          const Icon = ICONS[kind];
          return (
          <li key={kind} className="flex items-center gap-3 rounded-2xl border border-border bg-white/[0.025] px-4 py-3 text-base break-keep text-soft">
            <Icon className="size-5 shrink-0 text-primary-text" aria-hidden="true" />
            {text}
          </li>
          );
        })}
      </ul>
      <div className="mt-6 flex flex-wrap items-center gap-3">
        {downloadUrl ? (
          <Button size="lg" asChild>
            <a href={downloadUrl} download>
              <Download /> {demo ? "시연 녹화본 내려받기 (zip)" : "내려받기 (zip)"}
            </a>
          </Button>
        ) : (
          <p className="text-sm text-muted-foreground">실제 모드에서는 여기서 zip을 내려받아요.</p>
        )}
        {demo && downloadUrl && <p className="w-full text-xs break-keep text-faint">녹화된 기록으로 다시 묶은 시연용 zip 이에요 — 키 없이 인쇄용 문서를 볼 수 있어요.</p>}
        <Button variant="outline" size="lg" onClick={() => onOpen({ tab: "prototype" })}>
          <MonitorPlay /> 프로토타입 다시 보기
        </Button>
        <Button variant="ghost" size="lg" onClick={() => onOpen({ tab: "graph" })}>
          추적 지도 보기
        </Button>
      </div>
    </Card>
  );
}

// 「작업이 멈췄어요」: what stopped, and one button to pick up from that stage.
export function FailedCard({ pipeline, onRetry }: { pipeline: Pipeline | undefined; onRetry?: () => Promise<void> }) {
  const team = useView() === "team";
  const [busy, setBusy] = useState(false);
  const stage = STAGE_TITLE[pipeline?.stage ?? ""] ?? "지금 단계";
  return (
    <Card className="animate-rise border-[rgb(255_138_138/0.28)] px-8 pt-7 pb-7" role="alert" aria-labelledby="failed-title">
      <p className="flex items-center gap-2 text-sm font-semibold text-destructive">
        <CircleAlert className="size-4" aria-hidden="true" /> {stage}에서 멈췄어요
      </p>
      <h2 id="failed-title" className="mt-3 text-title font-bold tracking-[-0.02em] text-foreground">
        작업이 멈췄어요
      </h2>
      <p className="mt-2 text-base break-keep text-muted-foreground">
        지금까지 한 일은 그대로 남아 있어요. 다시 시도하면 멈춘 단계부터 이어서 해요.
      </p>
      {team && pipeline?.error && (
        <p className="mt-4 rounded-2xl border border-border bg-white/[0.03] px-4 py-3 text-sm break-keep text-soft">
          <span className="mr-1.5 text-xs font-semibold text-muted-foreground">오류 · {pipeline.stage}</span>
          {pipeline.error}
        </p>
      )}
      {onRetry && (
        <Button
          size="lg"
          className="mt-6"
          disabled={busy}
          onClick={async () => {
            setBusy(true);
            try {
              await onRetry();
            } finally {
              setBusy(false);
            }
          }}
        >
          {busy ? <LoaderCircle className="animate-spin" /> : <RotateCcw />} 다시 시도
        </Button>
      )}
    </Card>
  );
}
