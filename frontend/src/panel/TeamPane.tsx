import { ArrowRight, CircleAlert, CircleCheck, Route, ScrollText, ShieldAlert, ShieldCheck } from "lucide-react";
import { useMemo, useState, type ReactNode } from "react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import type { Project } from "../api";
import { STAGE_TITLE, type View } from "../lib/labels";
import { AgentAvatar } from "../thread/AgentAvatar";
import TeamGraph from "../thread/TeamGraph";
import { agentScores, exchanges, linerCalls, scoreVerdict, talkMatrix, teamFeed, type AgentScore, type FeedEntry, type Tone } from "../teamwatch/model";
import { CallScatter, TalkMatrix } from "./TeamCharts";
import type { TeamInfo } from "../ui/useTeam";

const TONE_TEXT: Record<Tone, string> = {
  ok: "text-success",
  warn: "text-warning",
  bad: "text-destructive",
  idle: "text-faint",
  info: "text-muted-foreground",
};
const LONG = 140;

// 팀 통신: beside the thread, the team at work — messages flying on the relation graph, how each agent is
// doing (from what the system recorded, not what the agents say about themselves), and the conversation
// with the checks and guardrails that fired on it, newest first. Picking an agent narrows the feed to it.
export default function TeamPane({ project, team, view, onAgent }: {
  project: Project;
  team: TeamInfo;
  view: View;
  onAgent?: (agent: string) => void;
}) {
  const [picked, setPicked] = useState<string | null>(null);
  const events = project.source.events;
  const pipeline = project.source.meta?.pipeline;
  const active = pipeline?.status === "running" ? pipeline.active_agent : null;
  const t = team.team;
  const ids = useMemo(() => (t ? [t.coordinator, ...t.members.filter((m) => m !== t.coordinator), ...t.external.filter((e) => e.kind !== "human").map((e) => e.id)] : []), [t]);
  const scores = useMemo(() => agentScores(events, ids), [events, ids]);
  const feed = useMemo(() => teamFeed(events, team.label, view).reverse(), [events, team.label, view]);
  const calls = useMemo(() => linerCalls(events), [events]);
  const matrix = useMemo(() => talkMatrix(exchanges(events), t ? [t.coordinator, ...t.members.filter((m) => m !== t.coordinator), ...t.external.map((e) => e.id)] : []), [events, t]);
  const shown = picked ? feed.filter((f) => f.from === picked || f.to === picked || f.actor === picked) : feed;
  const pick = (id: string) => setPicked((p) => (p === id ? null : id));

  if (!t) {
    return <p className="py-10 text-center text-sm text-muted-foreground">{team.error ? `팀 정보를 불러오지 못했어요: ${team.error}` : "팀 정보를 불러오고 있어요…"}</p>;
  }
  return (
    <div className="flex flex-col gap-5">
      <TeamGraph team={t} events={events} label={team.label} onPick={pick} picked={picked} className="flex flex-col gap-2" />

      <section aria-labelledby="team-calls-title" className="flex flex-col gap-2">
        <div className="flex flex-wrap items-baseline gap-x-2 gap-y-0.5">
          <h3 id="team-calls-title" className="shrink-0 text-sm font-semibold text-foreground">Liner 호출 흐름</h3>
          <p className="text-xs text-faint">점 하나가 에이전트의 Liner 호출 한 번이에요. 끝난 시각에 찍히고, 오래 걸릴수록 위에 있어요</p>
        </div>
        <CallScatter calls={calls} label={team.label} picked={picked} />
      </section>

      <section aria-labelledby="team-score-title" className="flex flex-col gap-2">
        <div className="flex flex-wrap items-baseline gap-x-2 gap-y-0.5">
          <h3 id="team-score-title" className="shrink-0 text-sm font-semibold text-foreground">에이전트별 상태</h3>
          <p className="text-xs text-faint">시스템이 남긴 기록으로 셌어요. 에이전트가 스스로 한 말은 넣지 않았어요</p>
        </div>
        <ul className="grid gap-2 [grid-template-columns:repeat(auto-fill,minmax(15rem,1fr))]">
          {scores.map((s) => (
            <li key={s.id}>
              <ScoreCard score={s} name={team.label(s.id)} working={active === s.id} chosen={picked === s.id} onPick={() => pick(s.id)} onLog={onAgent ? () => onAgent(s.id) : undefined} />
            </li>
          ))}
        </ul>
      </section>

      <section aria-labelledby="team-matrix-title" className="flex flex-col gap-2">
        <div className="flex flex-wrap items-baseline gap-x-2 gap-y-0.5">
          <h3 id="team-matrix-title" className="shrink-0 text-sm font-semibold text-foreground">누가 누구에게 몇 번</h3>
          <p className="text-xs text-faint">행이 보낸 쪽, 열이 받은 쪽이에요. 진할수록 많이 주고받았어요</p>
        </div>
        <TalkMatrix {...matrix} label={team.label} picked={picked} />
      </section>

      <section aria-labelledby="team-feed-title" className="flex flex-col gap-2">
        <div className="flex flex-wrap items-center gap-2">
          <h3 id="team-feed-title" className="text-sm font-semibold text-foreground">주고받은 말</h3>
          <p className="text-xs text-faint">
            최신 순 · {shown.length}건{picked ? ` · ${team.label(picked)} 관련만` : ""}
          </p>
          {picked && (
            <Button variant="ghost" size="sm" className="ml-auto" onClick={() => setPicked(null)}>
              전체 보기
            </Button>
          )}
        </div>
        {shown.length === 0 ? (
          <p className="py-6 text-center text-sm text-muted-foreground">아직 주고받은 말이 없어요</p>
        ) : (
          <ol className="flex flex-col gap-1.5" aria-label="팀이 주고받은 말과 점검 기록">
            {shown.map((f) => (
              <li key={`${f.kind}-${f.seq}`}>
                <FeedRow entry={f} label={team.label} />
              </li>
            ))}
          </ol>
        )}
      </section>
    </div>
  );
}

function ScoreCard({ score: s, name, working, chosen, onPick, onLog }: {
  score: AgentScore;
  name: string;
  working: boolean;
  chosen: boolean;
  onPick: () => void;
  onLog?: () => void;
}) {
  const verdict = scoreVerdict(s);
  const sec = s.avgMs === null ? null : (s.avgMs / 1000).toFixed(1);
  return (
    <div className={cn("flex h-full flex-col gap-1.5 rounded-2xl border bg-white/[0.03] px-3 py-2.5", chosen ? "border-cyan" : "border-border")}>
      <button type="button" onClick={onPick} aria-pressed={chosen} className="flex cursor-pointer items-center gap-2 rounded-lg text-left outline-none focus-visible:ring-[3px] focus-visible:ring-primary-ring">
        <AgentAvatar id={s.id} active={working} size="sm" />
        <span className="min-w-0 flex-1 truncate text-sm font-semibold text-foreground">{name}</span>
        {working ? (
          <span className="text-xs font-semibold text-cyan">일하는 중</span>
        ) : s.holding ? (
          <span className="text-xs text-muted-foreground">받은 일 있음</span>
        ) : null}
      </button>
      <p className={cn("flex items-center gap-1 text-xs font-semibold", TONE_TEXT[verdict.tone])}>
        {verdict.tone === "ok" ? <CircleCheck className="size-3.5" aria-hidden="true" /> : verdict.tone === "idle" ? null : <CircleAlert className="size-3.5" aria-hidden="true" />}
        {verdict.text}
      </p>
      <dl className="grid grid-cols-[auto_1fr] gap-x-2 text-xs text-muted-foreground tabular-nums">
        <dt>메시지</dt>
        <dd>받음 {s.received} · 보냄 {s.sent}</dd>
        <dt>Liner</dt>
        <dd>
          {s.liner}회{sec !== null ? ` · 평균 ${sec}초` : ""}
          {s.linerFailed ? <span className="text-destructive"> · 실패 {s.linerFailed}</span> : null}
        </dd>
        <dt>기록</dt>
        <dd>
          {s.written}건{s.masked ? ` · 민감 정보 가림 ${s.masked}` : ""}
        </dd>
      </dl>
      {onLog && (
        <Button variant="ghost" size="sm" className="-ml-2 self-start" onClick={onLog}>
          <ScrollText aria-hidden="true" /> 자세한 기록
        </Button>
      )}
    </div>
  );
}

function time(ts: string): string {
  const d = new Date(ts);
  return Number.isNaN(d.getTime()) ? "" : d.toLocaleTimeString("ko-KR", { hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: false });
}

const KIND_ICON: Record<Exclude<FeedEntry["kind"], "message">, ReactNode> = {
  check: <ShieldCheck className="size-3.5" aria-hidden="true" />,
  guard: <ShieldAlert className="size-3.5" aria-hidden="true" />,
  reroute: <Route className="size-3.5" aria-hidden="true" />,
  reject: <ShieldAlert className="size-3.5" aria-hidden="true" />,
};

function FeedRow({ entry: f, label }: { entry: FeedEntry; label: (id: string) => string }) {
  const meta = (
    <span className="ml-auto shrink-0 text-[11px] text-faint tabular-nums">
      {STAGE_TITLE[f.stage] ?? f.stage} · {time(f.ts)}
    </span>
  );
  if (f.kind !== "message") {
    return (
      <div className={cn("flex items-start gap-2 rounded-xl px-3 py-1.5 text-xs", TONE_TEXT[f.tone])}>
        <span className="mt-0.5 shrink-0">{KIND_ICON[f.kind]}</span>
        <p className="min-w-0 flex-1 break-keep">{f.text}</p>
        {meta}
      </div>
    );
  }
  return (
    <div className="flex flex-col gap-1 rounded-xl border border-border bg-white/[0.03] px-3 py-2">
      <div className="flex items-center gap-1.5 text-xs">
        <AgentAvatar id={f.from!} size="sm" />
        <span className="font-semibold text-foreground">{label(f.from!)}</span>
        <ArrowRight className="size-3 text-faint" aria-label="에게" />
        <AgentAvatar id={f.to!} size="sm" />
        <span className="font-semibold text-foreground">{label(f.to!)}</span>
        {meta}
      </div>
      {f.text.length > LONG ? (
        <details className="group text-sm text-soft">
          <summary className="cursor-pointer list-none break-keep">
            <span className="group-open:hidden">
              {f.text.slice(0, LONG)}… <span className="text-xs text-cyan">전체 보기</span>
            </span>
            <span className="hidden text-xs text-cyan group-open:inline">접기</span>
          </summary>
          <p className="mt-1 break-keep whitespace-pre-wrap">{f.text}</p>
        </details>
      ) : (
        <p className="text-sm break-keep whitespace-pre-wrap text-soft">{f.text}</p>
      )}
    </div>
  );
}
