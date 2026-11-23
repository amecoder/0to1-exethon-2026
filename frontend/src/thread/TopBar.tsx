import { Codes } from "../ui/refs";
import { ChevronLeft, CircleDollarSign, Download, GitBranch, PanelRight, Users } from "lucide-react";
import { useState, type ReactNode } from "react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import type { AppEvent } from "../api";
import { PRODUCT_MARK, PRODUCT_NAME, PRODUCT_NAME_KO } from "../brand";
import { BUDGET_TONE, budgetView, formatUsd } from "../lib/credits";
import type { View } from "../lib/labels";
import { NAME_MAX, cleanName } from "../lib/naming";
import GitHubPanel from "./GitHubPanel";
import HeaderPopover from "./HeaderPopover";
import GlossaryButton from "../ui/GlossaryDialog";
import type { CompactProgress } from "./model";
import UsageSummary from "./UsageSummary";
import { Term } from "../ui/Term";

export function ProductMark({ className = "" }: { className?: string }) {
  return (
    <span className={`inline-flex shrink-0 items-center gap-2 ${className}`}>
      <span
        className="grid size-7 place-items-center rounded-[9px] bg-[linear-gradient(135deg,#6553f5,#3fa6d8)] text-[10px] font-extrabold tracking-[-0.04em] text-primary-foreground shadow-[0_0_16px_-2px_rgb(101_83_245/0.8)]"
        aria-hidden="true"
      >
        {PRODUCT_MARK}
      </span>
      <span className="text-[15px] font-bold tracking-[-0.01em] whitespace-nowrap text-foreground">
        {PRODUCT_NAME}
        <span className="ml-1.5 text-xs font-medium text-muted-foreground">{PRODUCT_NAME_KO}</span>
      </span>
    </span>
  );
}

// Quiet stage indicator: "4/9 질문·답 · 남은 체크포인트 3개" with a hairline bar.
function ProgressIndicator({ progress }: { progress: CompactProgress }) {
  const ratio = progress.done ? 1 : (progress.step - 1) / progress.total;
  const text = progress.done
    ? "모든 단계를 마쳤어요"
    : `${progress.step}/${progress.total}단계 ${progress.label} · 남은 체크포인트 ${progress.remaining}개`;
  return (
    <div className="flex shrink-0 items-center gap-3 whitespace-nowrap" role="status" aria-label={`진행 ${text}`}>
      <span className="hidden h-1 w-16 overflow-hidden rounded-full bg-white/10 min-[1440px]:block" aria-hidden="true">
        <span className="block h-full rounded-full bg-[linear-gradient(90deg,#8b7cff,#7fe3f0)] shadow-[0_0_8px_rgb(127_227_240/0.7)] transition-[width] duration-500" style={{ width: `${Math.max(ratio, 0.04) * 100}%` }} />
      </span>
      <span className="text-sm text-muted-foreground">
        {progress.done ? (
          text
        ) : (
          <>
            <span className="mr-1.5 tabular-nums text-muted-foreground">
              {progress.step}/{progress.total}
            </span>
            <b className="font-semibold text-foreground"><Codes text={progress.label} /></b>
            <span className="mx-1.5 text-white/25" aria-hidden="true">·</span>
            남은 <Term name="체크포인트" /> {progress.remaining}개
          </>
        )}
      </span>
    </div>
  );
}

// Money this project has spent on Liner, measured from the credit balance (system readings, not agents).
// Clicking it opens the usage summary per Liner API kind.
// With a G7 budget it reads "$3.20 / $5.00" over a thin bar (cyan <60%, warning 60–85%, destructive ≥85% or over).
function SpentChip({ usd, budget, events }: { usd: number | null; budget: number | null; events: AppEvent[] }) {
  const view = budgetView(usd, budget);
  const tone = view ? BUDGET_TONE[view.level] : null;
  const label = view
    ? `이 프로젝트에 쓴 Liner 비용 ${view.line} — 사용 내역 보기`
    : usd != null
      ? `이 프로젝트에 쓴 Liner 비용 ${formatUsd(usd)} — 사용 내역 보기`
      : "Liner 사용 내역 보기";
  return (
    <HeaderPopover
      label={label}
      panelClassName="w-[28rem]"
      trigger={
        <>
          <CircleDollarSign className={cn("size-4", tone?.text ?? "text-cyan")} aria-hidden="true" />
          {view ? (
            <span className="flex flex-col items-stretch gap-0.5">
              <span className={cn("tabular-nums", view.over != null && tone?.text)}>{view.chip}</span>
              <span className="block h-0.5 w-full overflow-hidden rounded-full bg-white/10" aria-hidden="true">
                <span className={cn("block h-full rounded-full", tone?.bar)} style={{ width: `${Math.min(view.ratio, 1) * 100}%` }} />
              </span>
            </span>
          ) : usd != null ? (
            formatUsd(usd)
          ) : (
            "사용 내역"
          )}
        </>
      }
    >
      <UsageSummary events={events} spent={usd} budget={budget} />
    </HeaderPopover>
  );
}

// Always-there zip button: the client can take the current state at any point of the talk.
// A draft (not yet confirmed at CP4, or a CP5 change under review) says so on the button.
function DownloadButton({ url, final, note }: { url: string; final: boolean; note: string }) {
  const label = final ? "내려받기" : "작업본 내려받기";
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <Button variant={final ? "default" : "outline"} size="sm" asChild>
          <a href={url} download aria-label={`${label} (zip) — ${note}`}>
            <Download /> {label}
          </a>
        </Button>
      </TooltipTrigger>
      <TooltipContent className="max-w-72 break-keep"><Codes text={note} /></TooltipContent>
    </Tooltip>
  );
}

export default function TopBar({ projectName, progress, view, onView, onExit, team, extra, badge, panel, spentUsd, budgetUsd, events, download, onRename }: {
  projectName: string;
  onRename?: (name: string) => Promise<void>; // D1: absent in the demo replay — the name is plain text there
  progress: CompactProgress;
  view: View;
  onView: (v: View) => void;
  onExit: () => void;
  team: ReactNode;
  extra?: ReactNode;
  badge?: ReactNode;
  panel?: { open: boolean; onToggle: () => void };
  spentUsd?: number | null;
  budgetUsd?: number | null;
  events?: AppEvent[];
  download?: { url: string; final: boolean; note: string; projectId?: string } | null;
}) {
  return (
    <header className="sticky top-0 z-30 flex h-16 shrink-0 items-center gap-4 border-b border-white/[0.07] bg-deep/75 px-5 backdrop-blur-md">
      <Tooltip>
        <TooltipTrigger asChild>
          <Button variant="ghost" size="icon" onClick={onExit} aria-label="처음으로">
            <ChevronLeft className="size-5" />
          </Button>
        </TooltipTrigger>
        <TooltipContent>처음으로</TooltipContent>
      </Tooltip>
      <ProductMark />
      <span className="text-white/25" aria-hidden="true">
        /
      </span>
      <ProjectName name={projectName} onRename={onRename} />
      {badge && <span className="shrink-0">{badge}</span>}
      <div className="ml-auto flex shrink-0 items-center gap-4">
        {extra}
        {events && (spentUsd != null || events.some((e) => e.type.startsWith("liner_"))) && <SpentChip usd={spentUsd ?? null} budget={budgetUsd ?? null} events={events} />}
        <ProgressIndicator progress={progress} />
        {/* The avatar row needs ~220px; below 1440px it moves into an overflow popover so nothing wraps. */}
        <div className="hidden min-[1440px]:flex">{team}</div>
        <HeaderPopover
          className="min-[1440px]:hidden"
          label="에이전트 팀 보기"
          trigger={
            <>
              <Users className="size-4 text-cyan" aria-hidden="true" /> 팀
            </>
          }
        >
          {team}
        </HeaderPopover>
        <GlossaryButton />
        <ViewSwitch view={view} onView={onView} />
        {download && <DownloadButton {...download} />}
        {download?.projectId && (
          <HeaderPopover
            label="GitHub에 올리기"
            panelClassName="w-[24rem]"
            trigger={
              <>
                <GitBranch className="size-4 text-cyan" aria-hidden="true" /> GitHub
              </>
            }
          >
            <GitHubPanel projectId={download.projectId} final={download.final} />
          </HeaderPopover>
        )}
        {panel && (
          <Tooltip>
            <TooltipTrigger asChild>
              <Button
                variant="ghost"
                size="icon"
                onClick={panel.onToggle}
                aria-label={panel.open ? "결과물 창 닫기" : "결과물 창 열기 — 문서·프로토타입·추적 지도"}
                aria-pressed={panel.open}
                className={cn(panel.open && "bg-white/[0.1] text-foreground")}
              >
                <PanelRight className="size-5" />
              </Button>
            </TooltipTrigger>
            <TooltipContent>{panel.open ? "결과물 창 닫기" : "문서 · 프로토타입 · 추적 지도"}</TooltipContent>
          </Tooltip>
        )}
      </div>
    </header>
  );
}

const VIEWS: [View, string][] = [
  ["client", "발주사 보기"],
  ["team", "팀 보기"],
];

// Segmented switch between the two densities of the same data (a radio group, not tabs: no panels).
function ViewSwitch({ view, onView }: { view: View; onView: (v: View) => void }) {
  return (
    <div role="radiogroup" aria-label="보기 전환" className="inline-flex h-9 items-center rounded-lg border border-border bg-white/[0.04] p-1">
      {VIEWS.map(([value, text]) => (
        <button
          key={value}
          type="button"
          role="radio"
          aria-checked={view === value}
          onClick={() => onView(value)}
          className={cn(
            "inline-flex h-full cursor-pointer items-center rounded-md px-3 text-xs font-semibold whitespace-nowrap transition-colors outline-none focus-visible:ring-[3px] focus-visible:ring-primary-ring",
            view === value ? "bg-white/[0.12] text-foreground" : "text-muted-foreground hover:text-foreground",
          )}
        >
          {text}
        </button>
      ))}
    </div>
  );
}

// D1: the project's name; click to rename (Enter saves, Esc cancels). The server keeps a client's name over the
// name the team proposed at S2.
function ProjectName({ name, onRename }: { name: string; onRename?: (name: string) => Promise<void> }) {
  const [draft, setDraft] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const title = <h1 className="min-w-0 truncate text-[15px] font-medium whitespace-nowrap text-muted-foreground">{name}</h1>;
  if (!onRename) return title;
  if (draft === null) {
    return (
      <button type="button" className="min-w-0 cursor-text truncate rounded text-left" title="눌러서 이름 바꾸기" onClick={() => setDraft(name)}>
        {title}
      </button>
    );
  }
  const save = async () => {
    const next = cleanName(draft);
    if (!next) return setError("이름에 글자를 적어 주세요");
    try {
      await onRename(next);
      setDraft(null);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  };
  return (
    <span className="flex min-w-0 flex-col">
      <input
        autoFocus
        aria-label="프로젝트 이름"
        value={draft}
        maxLength={NAME_MAX}
        onChange={(e) => setDraft(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Enter") void save();
          if (e.key === "Escape") {
            setDraft(null);
            setError(null);
          }
        }}
        onBlur={() => setDraft(null)}
        className="min-w-0 rounded-md border border-border bg-white/[0.04] px-2 py-0.5 text-[15px] text-foreground outline-none focus-visible:ring-[3px] focus-visible:ring-primary-ring"
      />
      {error && (
        <span className="text-xs text-destructive" role="alert">
          {error}
        </span>
      )}
    </span>
  );
}
