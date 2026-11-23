import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import type { TeamInfo } from "../ui/useTeam";
import { AgentAvatar } from "./AgentAvatar";

// Header avatar stack: the 7 agents + the consumer persona. The active agent is lifted and highlighted.
// Each avatar opens that agent's activity log.
export default function TeamAvatars({ team, active, activity, onAgent }: {
  team: TeamInfo;
  active: string | null | undefined;
  activity: string | null;
  onAgent?: (agent: string) => void;
}) {
  if (!team.team) return null;
  const ids = [...team.team.members, ...team.team.external.filter((e) => e.kind === "agent").map((e) => e.id)];
  const summary = active ? `에이전트 팀 ${ids.length}명 · ${activity ?? `${team.label(active)} 작업 중`}` : `에이전트 팀 ${ids.length}명`;
  return (
    <div className="flex items-center" role="group" aria-label={summary}>
      {ids.map((id) => (
        <Tooltip key={id}>
          <TooltipTrigger asChild>
            <button
              type="button"
              onClick={() => onAgent?.(id)}
              aria-label={`${team.label(id)}${id === active && activity ? ` · ${activity}` : ""} — 활동 기록 열기`}
              className="-ml-1.5 cursor-pointer rounded-full outline-none first:ml-0 hover:-translate-y-0.5 focus-visible:ring-[3px] focus-visible:ring-primary-ring"
            >
              <AgentAvatar id={id} active={id === active} />
            </button>
          </TooltipTrigger>
          <TooltipContent>
            {team.label(id)}
            {id === active && activity ? ` · ${activity}` : ""}
            {onAgent ? " · 눌러서 활동 기록 보기" : ""}
          </TooltipContent>
        </Tooltip>
      ))}
    </div>
  );
}
