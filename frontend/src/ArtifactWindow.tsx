import { BellRing, X } from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import { TooltipProvider } from "@/components/ui/tooltip";
import { api, urls, type DemoMeta, type DocId, type DocView, type Project } from "./api";
import { PRODUCT_NAME } from "./brand";
import { refCatalog } from "./lib/refCatalog";
import ArtifactPanel from "./panel/ArtifactPanel";
import type { DocKind, DocUrl } from "./panel/docFiles";
import { GOTO_MESSAGE, pendingNotice, type Notice } from "./panel/notice";
import { DEMO_ASK, DEMO_CHANNEL, readDemoStep, type Popout } from "./panel/popout";
import type { PanelTarget } from "./panel/types";
import { useDocuments } from "./panel/useDocuments";
import { titlesOf } from "./panel/usePanel";
import { RefsProvider } from "./ui/refs";
import { useTeam } from "./ui/useTeam";
import { TitlesProvider, ViewProvider } from "./ui/view";

const POLL_MS = 1500;
const IDLE_POLL_MS = 4000; // waiting for the client: still check, so the next thing to handle shows up here

// The artifact panel alone in its own browser window (opened from the panel's 「새 창으로 보기」).
// It follows the project (fast while the team works, slower while it waits) and shows a banner when the
// client has something to handle; 「바로 가기」 brings the main window to that card.
export default function ArtifactWindow({ popout }: { popout: Popout }) {
  return popout.id === "demo" ? <DemoWindow popout={popout} /> : <RealWindow popout={popout} />;
}

function RealWindow({ popout }: { popout: Popout }) {
  const [project, setProject] = useState<Project | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [target, setTarget] = useState<PanelTarget>(popout.target);
  const team = useTeam();

  const refresh = useCallback(async () => {
    try {
      setProject(await api.project(popout.id));
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }, [popout.id]);

  useEffect(() => {
    refresh();
    window.addEventListener("focus", refresh);
    return () => window.removeEventListener("focus", refresh);
  }, [refresh]);
  const running = project?.source.meta?.pipeline?.status === "running" || Boolean(project?.lane?.busy);
  useEffect(() => {
    const timer = window.setInterval(refresh, running ? POLL_MS : IDLE_POLL_MS);
    return () => window.clearInterval(timer);
  }, [running, refresh]);
  useEffect(() => {
    if (project) document.title = `결과물 · ${project.name} · ${PRODUCT_NAME}`;
  }, [project]);

  if (!project) return <Waiting error={error} />;
  return <RealLoaded project={project} target={target} onTarget={setTarget} popout={popout} team={team} />;
}

function Waiting({ error }: { error: string | null }) {
  return (
    <div className="ds cosmos flex min-h-screen items-center justify-center font-sans text-sm text-muted-foreground">
      <p role={error ? "alert" : "status"}>{error ? `결과물을 불러오지 못했어요: ${error}` : "결과물을 불러오고 있어요…"}</p>
    </div>
  );
}

// The demo replay has no stored project: this window follows the player's step (BroadcastChannel) and
// loads that step's recorded state, the same way the player does.
function DemoWindow({ popout }: { popout: Popout }) {
  const [meta, setMeta] = useState<DemoMeta | null>(null);
  const [step, setStep] = useState(popout.step ?? 0);
  const [state, setState] = useState<Awaited<ReturnType<typeof api.demoState>> | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [target, setTarget] = useState<PanelTarget>(popout.target);
  const team = useTeam();
  const latest = useRef(step);
  useEffect(() => {
    api.demoMeta().then(setMeta, (e: unknown) => setError(e instanceof Error ? e.message : String(e)));
    if (typeof BroadcastChannel === "undefined") return;
    const ch = new BroadcastChannel(DEMO_CHANNEL);
    ch.onmessage = (e: MessageEvent) => {
      const next = readDemoStep(e.data);
      if (next !== null) setStep(next);
    };
    ch.postMessage({ type: DEMO_ASK });
    return () => ch.close();
  }, []);
  useEffect(() => {
    latest.current = step;
    api.demoState(step).then(
      (s) => latest.current === s.step && setState(s),
      (e: unknown) => setError(e instanceof Error ? e.message : String(e)),
    );
  }, [step]);
  const project: Project | null = useMemo(
    () => (meta && state ? { id: "demo", name: meta.project_name, mode: "demo", created_at: meta.recorded_at, source: state.source, todo: state.todo } : null),
    [meta, state],
  );
  useEffect(() => {
    if (project) document.title = `결과물 · ${project.name} (시연) · ${PRODUCT_NAME}`;
  }, [project]);
  if (!project) return <Waiting error={error} />;
  return (
    <Shell
      project={project}
      docs={state?.documents ?? null}
      links={{ preview: urls.demoPreview(step), flow: urls.demoFlow(step), lanes: urls.demoLanes(step), download: null,
        doc: (doc, kind) => urls.demoDoc(step, doc, kind) }}
      target={target}
      onTarget={setTarget}
      popout={popout}
      team={team}
    />
  );
}

function RealLoaded({ project, target, onTarget, popout, team }: {
  project: Project;
  target: PanelTarget;
  onTarget: (t: PanelTarget) => void;
  popout: Popout;
  team: ReturnType<typeof useTeam>;
}) {
  const docs = useDocuments(project);
  const delivery = project.delivery;
  const links = {
    preview: urls.preview(project.id),
    flow: urls.flow(project.id),
    lanes: urls.lanes(project.id),
    download: delivery?.ready ? urls.download(project.id) : null,
    doc: (doc: DocId, kind: DocKind) => urls.doc(project.id, doc, kind),
  };
  return <Shell project={project} docs={docs} links={links} target={target} onTarget={onTarget} popout={popout} team={team} />;
}

function Shell({ project, docs, links, target, onTarget, popout, team }: {
  project: Project;
  docs: Record<DocId, DocView> | null;
  links: { preview: string; flow: string; lanes: string; download: string | null; doc: DocUrl };
  target: PanelTarget;
  onTarget: (t: PanelTarget) => void;
  popout: Popout;
  team: ReturnType<typeof useTeam>;
}) {
  const titles = useMemo(() => titlesOf(project), [project]);
  const refs = useMemo(() => refCatalog(project.source), [project]);
  return (
    <ViewProvider view={popout.view}>
      <TitlesProvider titles={titles}>
        <RefsProvider catalog={refs}>
          <TooltipProvider>
            <div className="ds cosmos flex h-screen flex-col font-sans text-foreground">
              <NoticeBar notice={pendingNotice(project)} />
              <ArtifactPanel
                standalone
                project={project}
                docs={docs}
                target={target}
                onTarget={onTarget}
                width="wide"
                onWidth={() => {}}
                px={null}
                onPx={() => {}}
                onClose={() => window.close()}
                previewUrl={links.preview}
                flowUrl={links.flow}
                lanesUrl={links.lanes}
                downloadUrl={links.download}
                docUrl={links.doc}
                team={team}
                className="min-h-0 flex-1"
              />
            </div>
          </TooltipProvider>
        </RefsProvider>
      </TitlesProvider>
    </ViewProvider>
  );
}

// A banner for what waits on the client. Hidden per item once dismissed; the next item shows it again.
function NoticeBar({ notice }: { notice: Notice | null }) {
  const [hidden, setHidden] = useState<string | null>(null);
  const [lost, setLost] = useState(false);
  if (!notice || hidden === notice.key) return null;
  const go = () => {
    const main = window.opener as Window | null;
    if (!main || main.closed) {
      setLost(true);
      return;
    }
    main.postMessage({ type: GOTO_MESSAGE, target: notice.target }, window.location.origin);
    main.focus();
  };
  return (
    <div role="status" className="flex shrink-0 flex-wrap items-center gap-3 border-b border-warning/30 bg-warning-soft px-4 py-2.5 text-sm">
      <BellRing className="size-4 shrink-0 text-warning" aria-hidden="true" />
      <p className="min-w-0 flex-1 break-keep text-foreground">
        <span className="font-semibold text-warning">처리할 것이 있어요</span> · {notice.text}
        {lost && <span className="ml-2 text-muted-foreground">본 창이 닫혀 있어요. 처음 화면에서 이 프로젝트를 다시 열어 주세요.</span>}
      </p>
      <Button size="sm" onClick={go}>바로 가기</Button>
      <Button variant="ghost" size="icon" aria-label="알림 닫기" title="알림 닫기" onClick={() => setHidden(notice.key)}>
        <X />
      </Button>
    </div>
  );
}
