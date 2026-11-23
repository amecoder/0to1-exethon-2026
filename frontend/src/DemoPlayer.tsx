import { ChevronLeft, ChevronRight, Clapperboard, Pause, Play, SkipBack, SkipForward } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { TooltipProvider } from "@/components/ui/tooltip";
import { cn } from "@/lib/utils";
import { api, urls, type AppEvent, type DemoMeta, type DemoState, type Project } from "./api";
import { spentUsd } from "./lib/credits";
import type { View } from "./lib/labels";
import { extractScenes, nextSceneStep, prevSceneStep, sceneAt, type Scene } from "./lib/scenes";
import ArtifactPanel from "./panel/ArtifactPanel";
import { DEMO_ASK, DEMO_CHANNEL, DEMO_STEP, openPopout } from "./panel/popout";
import { titlesOf, usePanel } from "./panel/usePanel";
import { activityLine, compactProgress, sourceProgress } from "./thread/model";
import { openingMemo } from "./lib/opening";
import AgentLogDrawer from "./agentlog/AgentLogDrawer";
import TeamAvatars from "./thread/TeamAvatars";
import ThreadView from "./thread/ThreadView";
import TopBar from "./thread/TopBar";
import RecordingBanner from "./RecordingBanner";
import { useTeam } from "./ui/useTeam";
import { TitlesProvider, ViewProvider } from "./ui/view";
import { RefsProvider } from "./ui/refs";
import { refCatalog } from "./lib/refCatalog";

const BASE_MS = 800;
const SPEEDS = [1, 2, 4, 8];

// FR-16: replays a recorded run event by event, in the same thread + panel as real mode. The server
// rebuilds the shared source from the events; nothing here (or there) calls Liner. The recording banner
// stays visible for the whole replay, and the trace map grows as the events come in.
export default function DemoPlayer({ onExit }: { onExit: () => void }) {
  const [meta, setMeta] = useState<DemoMeta | null>(null);
  const [state, setState] = useState<DemoState | null>(null);
  const [allEvents, setAllEvents] = useState<AppEvent[]>([]);
  const [step, setStep] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [speed, setSpeed] = useState(2);
  const [view, setView] = useState<View>("client");
  const [error, setError] = useState<string | null>(null);
  const team = useTeam();
  const latest = useRef(0);

  useEffect(() => {
    api
      .demoMeta()
      .then((m) => {
        setMeta(m);
        // The last step's state carries every event; scenes are found from it once.
        return api.demoState(m.total).then((s) => setAllEvents(s.source.events));
      })
      .catch((e: unknown) => setError(e instanceof Error ? e.message : String(e)));
  }, []);
  useEffect(() => {
    latest.current = step;
    api
      .demoState(step)
      .then((s) => latest.current === s.step && setState(s))
      .catch((e: unknown) => setError(e instanceof Error ? e.message : String(e)));
  }, [step]);
  useEffect(() => {
    if (!playing || !meta) return;
    if (step >= meta.total) {
      setPlaying(false);
      return;
    }
    const timer = window.setTimeout(() => setStep((s) => Math.min(s + 1, meta.total)), BASE_MS / speed);
    return () => window.clearTimeout(timer);
  }, [playing, step, speed, meta]);

  // Tell a pop-out window which step is on screen (and answer when a new one asks).
  const channel = useRef<BroadcastChannel | null>(null);
  useEffect(() => {
    if (typeof BroadcastChannel === "undefined") return;
    const ch = new BroadcastChannel(DEMO_CHANNEL);
    channel.current = ch;
    ch.onmessage = (e: MessageEvent) => {
      if (e.data?.type === DEMO_ASK) ch.postMessage({ type: DEMO_STEP, step: latest.current });
    };
    return () => {
      channel.current = null;
      ch.close();
    };
  }, []);
  useEffect(() => {
    channel.current?.postMessage({ type: DEMO_STEP, step });
  }, [step]);

  const total = meta?.total ?? 0;
  const scenes = useMemo(() => extractScenes(allEvents), [allEvents]);
  const scene = sceneAt(scenes, step);
  // Opening scene: until the team starts, show the whole recorded memo with its conflicting sentences.
  const memo = useMemo(() => openingMemo(allEvents), [allEvents]);
  const teamStep = scenes.find((s) => s.kind === "team")?.step ?? 0;
  const opening = step < teamStep && memo.bubbles.length > 0 ? memo : null;
  // The playback dock overlays the bottom of the page; keep that much room under the content.
  const dock = useRef<HTMLElement>(null);
  const [dockH, setDockH] = useState(140);
  useEffect(() => {
    const el = dock.current;
    if (!el) return;
    const measure = () => setDockH(Math.ceil(el.getBoundingClientRect().height) + 16);
    measure();
    const observer = new ResizeObserver(measure);
    observer.observe(el);
    return () => observer.disconnect();
  }, []);
  useEffect(() => {
    document.documentElement.style.scrollPaddingBottom = `${dockH}px`;
    return () => {
      document.documentElement.style.scrollPaddingBottom = "";
    };
  }, [dockH]);
  const go = (n: number) => setStep(Math.max(0, Math.min(n, total)));
  const project: Project | null = useMemo(
    () =>
      meta && state
        ? { id: "demo", name: meta.project_name, mode: "demo", created_at: meta.recorded_at, source: state.source, todo: state.todo }
        : null,
    [meta, state],
  );
  const panel = usePanel(project);
  const [logAgent, setLogAgent] = useState<string | null>(null);
  const titles = useMemo(() => titlesOf(project), [project]);
  const refs = useMemo(() => refCatalog(project?.source), [project]);
  const pipeline = state?.source.meta?.pipeline;
  const running = pipeline?.status === "running";
  const activity = project && running ? activityLine(pipeline, project.source.events, team.label) : null;

  // Keyboard for recording: space = play/pause, [ ] = previous / next scene.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const el = e.target as HTMLElement;
      if (el.closest("input, textarea, select, button, [role=tab], [role=radio]")) return;
      if (e.key === " ") setPlaying((p) => !p);
      else if (e.key === "[") go(prevSceneStep(scenes, step) ?? step);
      else if (e.key === "]") go(nextSceneStep(scenes, step) ?? step);
      else return;
      e.preventDefault();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  });

  return (
    <ViewProvider view={view}>
      <TitlesProvider titles={titles}>
        <RefsProvider catalog={refs}>
        <TooltipProvider>
          <div className="ds cosmos min-h-screen font-sans text-foreground">
            <TopBar
              projectName={meta?.project_name ?? "시연 모드"}
              progress={state ? sourceProgress(state.source) : compactProgress(undefined, undefined)}
              view={view}
              onView={setView}
              onExit={onExit}
              badge={
                <Badge variant="cyan" className="ml-1">
                  <Clapperboard /> 시연 모드
                </Badge>
              }
              panel={project && project.source.sources.length > 0 ? { open: panel.open, onToggle: panel.toggle } : undefined}
              spentUsd={meta?.total_cost_usd ?? (project ? spentUsd(project.source.events) : null)}
              budgetUsd={meta?.max_cost_usd ?? null}
              events={project?.source.events}
              team={<TeamAvatars team={team} active={running ? pipeline?.active_agent : null} activity={activity?.text ?? null} onAgent={setLogAgent} />}
              extra={
                error && (
                  <span className="text-sm text-destructive" role="alert">
                    {error}
                  </span>
                )
              }
            />
            <RecordingBanner meta={meta} />
            <main className="flex items-start" style={{ ["--dock-h" as string]: `${dockH}px` }}>
              <div className="min-w-0 flex-1" style={{ paddingBottom: dockH }}>
                {project ? (
                  <ThreadView
                    project={project}
                    view={view}
                    team={team}
                    docs={state?.documents ?? null}
                    downloadUrl={state?.todo.kind === "download" ? urls.demoDownload() : null}
                    onOpen={panel.show}
                    onAgent={setLogAgent}
                    opening={opening}
                  />
                ) : (
                  <p className="px-6 pt-16 text-center text-muted-foreground">녹화 기록을 불러오고 있어요…</p>
                )}
              </div>
              {project && panel.open && (
                <ArtifactPanel
                  className="top-[6.5rem] h-[calc(100vh-6.5rem-var(--dock-h))]"
                  project={project}
                  docs={state?.documents ?? null}
                  target={panel.target}
                  onTarget={panel.setTarget}
                  width={panel.width}
                  onWidth={panel.setWidth}
                  px={panel.px}
                  onPx={panel.setPx}
                  onClose={panel.close}
                  previewUrl={urls.demoPreview(step)}
                  flowUrl={urls.demoFlow(step)}
                  lanesUrl={urls.demoLanes(step)}
                  downloadUrl={null}
                  docUrl={(doc, kind) => urls.demoDoc(step, doc, kind)}
                  team={team}
                  onAgent={setLogAgent}
                  onPopout={() => openPopout("demo", panel.target, view, step)}
                />
              )}
            </main>
            <PlayerDock
              dockRef={dock}
              step={step}
              total={total}
              scenes={scenes}
              scene={scene}
              playing={playing}
              speed={speed}
              ready={Boolean(meta)}
              onPlay={() => setPlaying(!playing)}
              onSpeed={setSpeed}
              onGo={go}
            />
            {project && logAgent && (
              <AgentLogDrawer
                agent={logAgent}
                events={project.source.events}
                source={project.source}
                label={team.label}
                view={view}
                titles={titles}
                onClose={() => setLogAgent(null)}
                onSelectItem={(id) => {
                  setLogAgent(null);
                  panel.show({ tab: "graph", focus: id });
                }}
              />
            )}
          </div>
        </TooltipProvider>
        </RefsProvider>
      </TitlesProvider>
    </ViewProvider>
  );
}

function PlayerDock({ dockRef, step, total, scenes, scene, playing, speed, ready, onPlay, onSpeed, onGo }: {
  dockRef: React.RefObject<HTMLElement>;
  step: number;
  total: number;
  scenes: Scene[];
  scene: Scene | null;
  playing: boolean;
  speed: number;
  ready: boolean;
  onPlay: () => void;
  onSpeed: (s: number) => void;
  onGo: (n: number) => void;
}) {
  const prev = prevSceneStep(scenes, step);
  const next = nextSceneStep(scenes, step);
  const pct = (n: number) => `${total ? (n / total) * 100 : 0}%`;
  return (
    <div className="pointer-events-none fixed inset-x-0 bottom-0 z-30 flex justify-center px-4 pb-4">
      <section
        ref={dockRef}
        className="pointer-events-auto relative flex w-full max-w-[64rem] flex-col gap-2.5 overflow-hidden rounded-3xl border border-cyan/40 bg-[#050c2e]/[0.97] px-5 pt-3.5 pb-4 shadow-[0_-12px_40px_-8px_rgb(0_0_0/0.75),0_0_28px_-6px_rgb(127_227_240/0.45)] backdrop-blur-xl before:pointer-events-none before:absolute before:inset-x-6 before:top-0 before:h-px before:bg-[linear-gradient(90deg,transparent,#7fe3f0,#8b7bff,transparent)]"
        aria-label="재생 조절"
      >
        <p className="flex min-h-7 items-center gap-2.5 text-base break-keep" aria-live="polite">
          {scene ? (
            <>
              <span
                className={cn(
                  "shrink-0 rounded-full px-2.5 py-0.5 text-xs font-semibold",
                  scene.kind.startsWith("CP") ? "bg-primary-soft text-primary-text" : "bg-cyan-soft text-cyan",
                )}
              >
                {scene.label}
              </span>
              <span className="min-w-0 truncate text-foreground">{scene.caption}</span>
            </>
          ) : (
            <span className="text-muted-foreground">재생을 누르거나 다음 장면으로 녹화된 실행을 처음부터 봐요</span>
          )}
        </p>
        <div className="flex items-center gap-2">
          <Button variant="ghost" size="icon" aria-label="이전 장면" title="이전 장면 ( [ )" disabled={prev === null} onClick={() => prev !== null && onGo(prev)}>
            <SkipBack />
          </Button>
          <Button size="icon" className="size-11 rounded-full" aria-label={playing ? "일시정지" : "재생"} title="재생 / 일시정지 (스페이스)" disabled={!ready || step >= total} onClick={onPlay}>
            {playing ? <Pause className="size-5" /> : <Play className="size-5 translate-x-px" />}
          </Button>
          <Button variant="ghost" size="icon" aria-label="다음 장면" title="다음 장면 ( ] )" disabled={next === null} onClick={() => next !== null && onGo(next)}>
            <SkipForward />
          </Button>
          <Button variant="ghost" size="icon" className="size-8" aria-label="한 단계 뒤로" disabled={step === 0} onClick={() => onGo(step - 1)}>
            <ChevronLeft />
          </Button>
          <Button variant="ghost" size="icon" className="size-8" aria-label="한 단계 앞으로" disabled={step >= total} onClick={() => onGo(step + 1)}>
            <ChevronRight />
          </Button>

          <div className="relative mx-2 flex h-9 min-w-0 flex-1 items-center">
            <input
              type="range"
              min={0}
              max={total}
              value={step}
              aria-label="재생 위치"
              aria-valuetext={`${step} / ${total}${scene ? ` · ${scene.label}` : ""}`}
              onChange={(e) => onGo(Number(e.target.value))}
              className="peer absolute inset-0 z-0 h-9 w-full cursor-pointer opacity-0"
            />
            <div
              className="pointer-events-none absolute inset-x-0 h-1 rounded-full bg-white/25 peer-focus-visible:ring-[3px] peer-focus-visible:ring-primary-ring"
              aria-hidden="true"
            >
              <div className="h-full rounded-full bg-[linear-gradient(90deg,#8b7cff,#7fe3f0)]" style={{ width: pct(step) }} />
              <span
                className="absolute top-1/2 size-3.5 -translate-x-1/2 -translate-y-1/2 rounded-full bg-white shadow-[0_0_10px_rgb(127_227_240/0.8)]"
                style={{ left: pct(step) }}
              />
            </div>
            {/* Scene dots are a pointer shortcut only (they sit too close together to be proper targets);
                keyboard and screen-reader users pick a scene from the list next to the counter. */}
            <div className="pointer-events-none absolute inset-x-0 top-1/2 z-10" aria-hidden="true">
              {scenes.map((s) => (
                <span
                  key={`${s.kind}-${s.step}`}
                  title={s.label}
                  onClick={() => onGo(s.step)}
                  className={cn(
                    "pointer-events-auto absolute block size-2.5 -translate-x-1/2 -translate-y-[calc(50%+0.75rem)] cursor-pointer rounded-full ring-2 ring-deep transition-transform hover:scale-150",
                    s.kind.startsWith("CP") ? "bg-primary-text" : "bg-cyan",
                    scene === s && "scale-150",
                  )}
                  style={{ left: pct(s.step) }}
                />
              ))}
            </div>
          </div>
          <label className="sr-only" htmlFor="scene-pick">
            장면으로 이동
          </label>
          <select
            id="scene-pick"
            value={scene ? scene.step : ""}
            onChange={(e) => e.target.value !== "" && onGo(Number(e.target.value))}
            className="h-8 w-32 shrink-0 cursor-pointer rounded-lg border border-border bg-deep px-2 text-xs text-foreground"
          >
            {!scene && <option value="">장면 고르기</option>}
            {scenes.map((s) => (
              <option key={`${s.kind}-${s.step}`} value={s.step}>
                {s.label}
              </option>
            ))}
          </select>
          <span className="w-16 shrink-0 text-right text-xs tabular-nums text-muted-foreground">
            {step} / {total}
          </span>
          <div role="radiogroup" aria-label="재생 속도" className="ml-1 inline-flex h-8 items-center rounded-lg border border-border bg-white/[0.04] p-0.5">
            {SPEEDS.map((s) => (
              <button
                key={s}
                type="button"
                role="radio"
                aria-checked={speed === s}
                onClick={() => onSpeed(s)}
                className={cn(
                  "h-full cursor-pointer rounded-md px-2 text-xs font-semibold tabular-nums outline-none focus-visible:ring-[3px] focus-visible:ring-primary-ring",
                  speed === s ? "bg-white/[0.12] text-foreground" : "text-muted-foreground hover:text-foreground",
                )}
              >
                {s}×
              </button>
            ))}
          </div>
        </div>
      </section>
    </div>
  );
}
