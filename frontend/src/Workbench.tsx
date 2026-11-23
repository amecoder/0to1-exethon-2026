import { useCallback, useEffect, useMemo, useState } from "react";
import { BellRing } from "lucide-react";
import { Button } from "@/components/ui/button";
import { TooltipProvider } from "@/components/ui/tooltip";
import { useOsNotice } from "./ui/useOsNotice";
import { api, urls, type Project } from "./api";
import { spentUsd } from "./lib/credits";
import type { View } from "./lib/labels";
import ArtifactPanel from "./panel/ArtifactPanel";
import { openPopout } from "./panel/popout";
import { useDocuments } from "./panel/useDocuments";
import { titlesOf, usePanel } from "./panel/usePanel";
import { activityLine, sourceProgress } from "./thread/model";
import AgentLogDrawer from "./agentlog/AgentLogDrawer";
import TeamAvatars from "./thread/TeamAvatars";
import ThreadView from "./thread/ThreadView";
import TopBar from "./thread/TopBar";
import { useTeam } from "./ui/useTeam";
import { TitlesProvider, ViewProvider } from "./ui/view";
import { RefsProvider } from "./ui/refs";
import { refCatalog } from "./lib/refCatalog";

const POLL_MS = 1500;

// Real mode: the work thread, with the artifact panel (documents · prototype · trace map) beside it.
// Starts in the client view (발주사 보기); the switch moves to the team view.
export default function Workbench({ project: initial, onExit }: { project: Project; onExit: () => void }) {
  const [project, setProject] = useState<Project>(initial);
  const [error, setError] = useState<string | null>(null);
  const [view, setView] = useState<View>("client");
  const team = useTeam();
  const panel = usePanel(project);
  const [logAgent, setLogAgent] = useState<string | null>(null);
  const titles = useMemo(() => titlesOf(project), [project]);
  const refs = useMemo(() => refCatalog(project?.source), [project]);
  const docs = useDocuments(project);
  const os = useOsNotice(project);

  const refresh = useCallback(async () => {
    try {
      setProject(await api.project(initial.id));
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }, [initial.id]);

  const pipeline = project.source.meta?.pipeline;
  const running = pipeline?.status === "running" || Boolean(project.lane?.busy);
  useEffect(() => {
    refresh();
  }, [refresh]);
  useEffect(() => {
    if (!running) return;
    const timer = window.setInterval(refresh, POLL_MS);
    return () => window.clearInterval(timer);
  }, [running, refresh]);

  const activity = pipeline?.status === "running" ? activityLine(pipeline, project.source.events, team.label) : null;
  const delivery = project.delivery;
  const downloadUrl = delivery?.ready ? urls.download(project.id) : null;

  return (
    <ViewProvider view={view}>
      <TitlesProvider titles={titles}>
        <RefsProvider catalog={refs}>
        <TooltipProvider>
          <div className="ds cosmos min-h-screen font-sans text-foreground">
            <TopBar
              projectName={project.name}
              onRename={async (name) => {
                await api.renameProject(project.id, name);
                await refresh();
              }}
              progress={sourceProgress(project.source)}
              view={view}
              onView={setView}
              onExit={onExit}
              panel={project.source.sources.length > 0 ? { open: panel.open, onToggle: panel.toggle } : undefined}
              spentUsd={spentUsd(project.source.events)}
              budgetUsd={project.budget_usd ?? null}
              events={project.source.events}
              download={downloadUrl && delivery ? { url: downloadUrl, final: delivery.final, note: delivery.note, projectId: project.id } : null}
              team={<TeamAvatars team={team} active={running ? pipeline?.active_agent : null} activity={activity?.text ?? null} onAgent={setLogAgent} />}
              extra={
                <>
                  {os.permission === "default" && (
                    <Button variant="ghost" size="sm" onClick={os.enable} title="다른 창을 보고 있어도 처리할 것이 생기면 화면 구석에 알려 드려요">
                      <BellRing aria-hidden="true" /> 알림 켜기
                    </Button>
                  )}
                  {error && (
                    <span className="text-sm text-destructive" role="alert">
                      {error}
                    </span>
                  )}
                </>
              }
            />
            <main className="flex min-h-[calc(100vh-4rem)] items-start">
              <div className="min-w-0 flex-1">
                <ThreadView
                  project={project}
                  view={view}
                  team={team}
                  docs={docs}
                  downloadUrl={downloadUrl}
                  onChanged={refresh}
                  onOpen={panel.show}
                  onAgent={setLogAgent}
                />
              </div>
              {panel.open && (
                <ArtifactPanel
                  project={project}
                  docs={docs}
                  target={panel.target}
                  onTarget={panel.setTarget}
                  width={panel.width}
                  onWidth={panel.setWidth}
                  px={panel.px}
                  onPx={panel.setPx}
                  onClose={panel.close}
                  previewUrl={urls.preview(project.id)}
                  flowUrl={urls.flow(project.id)}
                  lanesUrl={urls.lanes(project.id)}
                  downloadUrl={downloadUrl}
                  docUrl={(doc, kind) => urls.doc(project.id, doc, kind)}
                  team={team}
                  onAgent={setLogAgent}
                  onPopout={() => openPopout(project.id, panel.target, view)}
                />
              )}
            </main>
            {logAgent && (
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
