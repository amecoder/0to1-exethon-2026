import { Network, PanelRight, Users } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import type { AppEvent, Team } from "../api";
import type { Label } from "../lib/summarize";
import { relationCounters } from "../lib/usage";
import { exchanges, packetsSince, pairCounts, pairKey, relationName, type Exchange } from "../teamwatch/model";
import { AGENT_ICON } from "./AgentAvatar";

const W = 760;
const H = 460;
const CX = W / 2;
const CY = H / 2 + 6;
const RX = 290;
const RY = 172;
const FLY_MS = 2400; // slow enough to read the words riding on the packet
const GAP_MS = 1700;
const RIPPLE_MS = 700;
const REPLAY = 6; // on first look the last few messages fly again, so a finished project still shows its traffic
const BURST = 8;

type Point = { x: number; y: number };
type Curve = { a: Point; c: Point; b: Point };

// Coordinator in the middle, everyone else on an ellipse around it (fixed order: same picture every time).
function positions(team: Team): Record<string, Point> {
  const around = [...team.members.filter((m) => m !== team.coordinator), ...team.external.map((e) => e.id)];
  const out: Record<string, Point> = { [team.coordinator]: { x: CX, y: CY } };
  around.forEach((id, i) => {
    const t = (i / around.length) * Math.PI * 2 - Math.PI / 2;
    out[id] = { x: CX + Math.cos(t) * RX, y: CY + Math.sin(t) * RY };
  });
  return out;
}

function radius(volume: number): number {
  return 15 + Math.min(11, Math.sqrt(volume) * 1.4);
}

// A quadratic curve from a to b, bowed sideways (straight for the coordinator's spokes), trimmed so it
// starts and ends at the node rims instead of their centres.
function curve(a: Point, b: Point, ra: number, rb: number, bend: number): Curve {
  const mx = (a.x + b.x) / 2;
  const my = (a.y + b.y) / 2;
  const dx = b.x - a.x;
  const dy = b.y - a.y;
  const len = Math.hypot(dx, dy) || 1;
  // Bow away from the coordinator in the middle, so side relations do not cross its label.
  const c1 = { x: mx - (dy / len) * bend, y: my + (dx / len) * bend };
  const c2 = { x: mx + (dy / len) * bend, y: my - (dx / len) * bend };
  const c = Math.hypot(c1.x - CX, c1.y - CY) >= Math.hypot(c2.x - CX, c2.y - CY) ? c1 : c2;
  const toward = (p: Point, q: Point, r: number) => {
    const l = Math.hypot(q.x - p.x, q.y - p.y) || 1;
    return { x: p.x + ((q.x - p.x) / l) * r, y: p.y + ((q.y - p.y) / l) * r };
  };
  return { a: toward(a, c, ra + 3), c, b: toward(b, c, rb + 6) };
}

function at(k: Curve, t: number): Point {
  const u = 1 - t;
  return { x: u * u * k.a.x + 2 * u * t * k.c.x + t * t * k.b.x, y: u * u * k.a.y + 2 * u * t * k.c.y + t * t * k.b.y };
}

function reversed(k: Curve): Curve {
  return { a: k.b, c: k.c, b: k.a };
}

function reducedMotion(): boolean {
  return typeof window !== "undefined" && Boolean(window.matchMedia?.("(prefers-reduced-motion: reduce)").matches);
}

type Flying = Exchange & { delay: number };

// 팀 관계도, drawn like an APM topology view: agents are nodes sized by how much they talk, relations are
// labelled arrows (what flows along them, from teams/default.json, with how many messages did), and every
// message travels its relation as a packet carrying its first words. The line under the map spells out the
// message in flight.
export default function TeamGraph({ team, events, label, onOpen, onPick, picked, className }: {
  team: Team;
  events: AppEvent[];
  label: Label;
  onOpen?: () => void; // open the team pane beside the thread
  onPick?: (id: string) => void; // a node was chosen (the pane filters its feed)
  picked?: string | null;
  className?: string;
}) {
  const pos = useMemo(() => positions(team), [team]);
  const counters = relationCounters(events);
  const all = useMemo(() => exchanges(events).filter((x) => pos[x.from] && pos[x.to]), [events, pos]);
  const counts = useMemo(() => pairCounts(all), [all]);
  const volume = useMemo(() => {
    const v: Record<string, number> = {};
    for (const x of all) {
      v[x.from] = (v[x.from] ?? 0) + 1;
      v[x.to] = (v[x.to] ?? 0) + 1;
    }
    return v;
  }, [all]);
  const r = (id: string) => radius(volume[id] ?? 0);
  // One curve per relation, in the relation's own direction; messages the other way ride it backwards.
  const curves = useMemo(() => {
    const out = new Map<string, Curve>();
    for (const rel of team.relations) {
      const a = pos[rel.from];
      const b = pos[rel.to];
      if (!a || !b) continue;
      const spoke = rel.from === team.coordinator || rel.to === team.coordinator;
      out.set(`${rel.from}>${rel.to}`, curve(a, b, radius(volume[rel.from] ?? 0), radius(volume[rel.to] ?? 0), spoke ? 0 : 44));
    }
    return out;
  }, [team, pos, volume]);
  const route = (from: string, to: string): Curve =>
    curves.get(`${from}>${to}`) ?? (curves.has(`${to}>${from}`) ? reversed(curves.get(`${to}>${from}`)!) : curve(pos[from], pos[to], r(from), r(to), 0));

  const last = useRef<number | null>(null);
  const [flying, setFlying] = useState<Flying[]>([]);
  const [now, setNow] = useState<Exchange | null>(null);
  useEffect(() => {
    const first = last.current === null;
    const batch = packetsSince(all, last.current, first ? REPLAY : BURST);
    if (all.length) last.current = all[all.length - 1].seq;
    if (!batch.length) return;
    if (reducedMotion()) {
      setNow(batch[batch.length - 1]);
      return;
    }
    setFlying((f) => [...f, ...batch.filter((x) => !f.some((y) => y.seq === x.seq)).map((x, i) => ({ ...x, delay: i * GAP_MS }))]);
  }, [all]);
  const land = (seq: number) => setFlying((f) => f.filter((x) => x.seq !== seq));
  const shown = now ?? all[all.length - 1] ?? null;
  const busy = new Set(flying.flatMap((p) => [p.from, p.to]));
  const hotPair = (a: string, b: string) => flying.some((p) => pairKey(p.from, p.to) === pairKey(a, b));
  const max = Math.max(1, ...counts.values());

  return (
    <section className={className ?? "glass flex animate-rise flex-col gap-2 rounded-3xl px-5 pt-4 pb-3"} aria-labelledby="team-graph-title">
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
        <h2 id="team-graph-title" className="flex items-center gap-1.5 text-sm font-semibold text-foreground">
          <Network className="size-4 text-cyan" aria-hidden="true" /> 팀 관계도
        </h2>
        <p className="text-sm text-muted-foreground">
          메시지 <b className="font-semibold text-foreground tabular-nums">{all.length}</b>건 · 관계 밖 메시지 차단{" "}
          <b className="font-semibold text-foreground tabular-nums">{counters.rerouted}</b>건 · 쓰기 거부{" "}
          <b className="font-semibold text-foreground tabular-nums">{counters.rejected}</b>건
        </p>
        {onOpen && (
          <Button variant="ghost" size="sm" className="ml-auto" onClick={onOpen}>
            <PanelRight aria-hidden="true" /> 옆에서 보기
          </Button>
        )}
      </div>
      <svg viewBox={`0 0 ${W} ${H}`} className="h-auto w-full overflow-visible" role="img" aria-label={`팀 관계선 ${team.relations.length}개와 오간 메시지 ${all.length}건. 선 위 이름표는 그 관계로 오가는 내용과 횟수예요`}>
        <defs>
          <filter id="team-glow" x="-50%" y="-50%" width="200%" height="200%">
            <feGaussianBlur stdDeviation="3.2" result="b" />
            <feMerge>
              <feMergeNode in="b" />
              <feMergeNode in="SourceGraphic" />
            </feMerge>
          </filter>
          <filter id="team-haze" x="-50%" y="-50%" width="200%" height="200%">
            <feGaussianBlur stdDeviation="5" />
          </filter>
          <pattern id="team-grid" width="22" height="22" patternUnits="userSpaceOnUse">
            <circle cx="1" cy="1" r="0.9" fill="rgb(127 227 240 / 0.16)" />
          </pattern>
          <radialGradient id="team-grid-fade" cx="50%" cy="50%" r="60%">
            <stop offset="0%" stopColor="white" stopOpacity="1" />
            <stop offset="100%" stopColor="white" stopOpacity="0" />
          </radialGradient>
          <mask id="team-grid-mask">
            <rect width={W} height={H} fill="url(#team-grid-fade)" />
          </mask>
          <marker id="team-arrow" viewBox="0 0 10 10" refX="8" refY="5" markerUnits="userSpaceOnUse" markerWidth="11" markerHeight="11" orient="auto-start-reverse">
            <path d="M0,1 L9,5 L0,9 z" fill="rgb(255 255 255 / 0.4)" />
          </marker>
          <marker id="team-arrow-hot" viewBox="0 0 10 10" refX="8" refY="5" markerUnits="userSpaceOnUse" markerWidth="11" markerHeight="11" orient="auto-start-reverse">
            <path d="M0,1 L9,5 L0,9 z" fill="var(--cyan)" />
          </marker>
        </defs>
        <rect width={W} height={H} fill="url(#team-grid)" mask="url(#team-grid-mask)" />
        {team.relations.map((rel) => {
          const k = curves.get(`${rel.from}>${rel.to}`);
          if (!k) return null;
          const n = counts.get(pairKey(rel.from, rel.to)) ?? 0;
          const hot = hotPair(rel.from, rel.to);
          const back = hot && !flying.some((p) => p.from === rel.from && p.to === rel.to); // traffic runs against the arrow
          const d = `M${k.a.x},${k.a.y} Q${k.c.x},${k.c.y} ${k.b.x},${k.b.y}`;
          const w = 1 + (n / max) * 3;
          const grad = `team-edge-${rel.from}-${rel.to}`;
          const spoke = rel.from === team.coordinator || rel.to === team.coordinator;
          // Spoke labels sit toward the outer node, clear of the crowded middle.
          const mid = at(k, spoke ? (rel.from === team.coordinator ? 0.62 : 0.38) : 0.5);
          const full = relationName(rel.carries);
          const name = full.length > 12 ? `${full.slice(0, 11)}…` : full;
          return (
            <g key={`${rel.from}-${rel.to}`}>
              <linearGradient id={grad} gradientUnits="userSpaceOnUse" x1={k.a.x} y1={k.a.y} x2={k.b.x} y2={k.b.y}>
                <stop offset="0%" stopColor="#7fe3f0" />
                <stop offset="100%" stopColor="#8b7bff" />
              </linearGradient>
              {/* Neon: a blurred halo under a thin gradient core, and a light streak running along the line. */}
              {n > 0 && <path d={d} fill="none" stroke={`url(#${grad})`} strokeWidth={w + 5} opacity={hot ? 0.55 : 0.14} filter="url(#team-haze)" />}
              <path
                d={d}
                fill="none"
                stroke={n ? `url(#${grad})` : "rgb(255 255 255 / 0.14)"}
                strokeWidth={hot ? w + 0.6 : w}
                opacity={hot ? 1 : n ? 0.5 : 1}
                markerEnd={`url(#${hot ? "team-arrow-hot" : "team-arrow"})`}
              >
                <title>{`${label(rel.from)} → ${label(rel.to)}: ${rel.carries} · 메시지 ${n}건`}</title>
              </path>
              {n > 0 && (
                <path
                  d={d}
                  pathLength={100}
                  fill="none"
                  stroke={hot ? "#e9fdff" : "#7fe3f0"}
                  strokeWidth={hot ? 2.6 : 1.6}
                  strokeLinecap="round"
                  strokeDasharray={hot ? "9 91" : "5 95"}
                  opacity={hot ? 1 : 0.45}
                  filter="url(#team-glow)"
                  className={hot ? (back ? "team-streak-back" : "team-streak") : "team-streak-idle"}
                  style={hot ? undefined : { animationDelay: `${-((n * 0.77) % 5)}s` }}
                  data-streak={hot ? "hot" : "idle"}
                />
              )}
              <text x={mid.x} y={mid.y - 4} textAnchor="middle" fontSize="10.5" fill={hot ? "var(--foreground)" : "var(--muted-foreground)"} stroke="var(--background)" strokeWidth={3.5} paintOrder="stroke" data-edge={pairKey(rel.from, rel.to)} data-count={n}>
                {name}
                <tspan fill={hot ? "var(--cyan)" : "var(--faint)"} fontWeight={600}>{` ${n}`}</tspan>
              </text>
            </g>
          );
        })}
        {flying.map((p) => (
          <Packet key={p.seq} packet={p} path={route(p.from, p.to)} human={isHuman(team, p.from) || isHuman(team, p.to)} onStart={() => setNow(p)} onDone={() => land(p.seq)} />
        ))}
        {Object.entries(pos).map(([id, p]) => (
          <Node
            key={id}
            id={id}
            at={p}
            r={r(id)}
            name={label(id)}
            tag={id === team.coordinator ? "조율" : isHuman(team, id) ? "사람" : team.external.some((e) => e.id === id) ? "외부 에이전트" : "에이전트"}
            human={isHuman(team, id)}
            hot={busy.has(id)}
            chosen={picked === id}
            onPick={onPick ? () => onPick(id) : undefined}
          />
        ))}
      </svg>
      <p className="flex min-h-5 items-baseline gap-2 text-sm" aria-live="polite">
        {shown ? (
          <>
            <span className="shrink-0 font-semibold text-cyan">
              {label(shown.from)} → {label(shown.to)}
            </span>
            <span className="min-w-0 truncate text-soft" title={shown.text}>{shown.text}</span>
          </>
        ) : (
          <span className="text-faint">아직 오간 말이 없어요</span>
        )}
      </p>
      <p className="text-xs break-keep text-faint">공 하나가 메시지 하나예요. 선 이름표는 그 관계로 오가는 내용과 지금까지 오간 횟수이고, 많이 오간 선일수록 굵어요. 선이 없는 사이의 말은 조율자를 거쳐 가요(차단).</p>
    </section>
  );
}

function isHuman(team: Team, id: string): boolean {
  return team.external.some((e) => e.id === id && e.kind === "human");
}

function Node({ id, at: p, r, name, tag, human, hot, chosen, onPick }: {
  id: string;
  at: Point;
  r: number;
  name: string;
  tag: string;
  human: boolean;
  hot: boolean;
  chosen: boolean;
  onPick?: () => void;
}) {
  const Icon = AGENT_ICON[id] ?? Users;
  const accent = human ? "var(--warning)" : "var(--cyan)";
  return (
    <g
      data-node={id}
      data-x={p.x}
      data-y={p.y}
      role={onPick ? "button" : undefined}
      tabIndex={onPick ? 0 : undefined}
      aria-label={onPick ? `${name} 관련만 보기` : undefined}
      aria-pressed={onPick ? chosen : undefined}
      onClick={onPick}
      onKeyDown={onPick ? (e) => (e.key === "Enter" || e.key === " ") && (e.preventDefault(), onPick()) : undefined}
      className={onPick ? "cursor-pointer outline-none [&:focus-visible>circle:first-child]:stroke-primary-ring" : undefined}
    >
      <circle cx={p.x} cy={p.y} r={r + 5} fill="none" stroke={chosen ? "var(--cyan)" : "transparent"} strokeWidth={2} />
      <circle
        cx={p.x}
        cy={p.y}
        r={r}
        fill={hot ? "rgb(127 227 240 / 0.22)" : "rgb(255 255 255 / 0.06)"}
        stroke={hot ? accent : human ? "var(--warning)" : "rgb(255 255 255 / 0.28)"}
        strokeWidth={hot ? 2 : 1.2}
        style={hot ? { filter: `drop-shadow(0 0 8px ${accent})` } : undefined}
      />
      <Icon x={p.x - 9} y={p.y - 9} width={18} height={18} strokeWidth={1.75} color={hot ? "var(--foreground)" : "var(--soft)"} aria-hidden="true" />
      <text x={p.x} y={p.y + r + 15} textAnchor="middle" fontSize="13" fontWeight={600} fill="var(--foreground)">
        {name}
      </text>
      <text x={p.x} y={p.y + r + 28} textAnchor="middle" fontSize="10" fill="var(--faint)">
        {tag}
      </text>
    </g>
  );
}

// One message in flight, driven frame by frame along its relation's curve: fades in, glides, fades out,
// then a ripple at the receiver. Removed when done.
function Packet({ packet, path, human, onStart, onDone }: { packet: Flying; path: Curve; human: boolean; onStart: () => void; onDone: () => void }) {
  const dot = useRef<SVGGElement>(null);
  const tail = useRef<SVGPolylineElement>(null);
  const words = useRef<SVGTextElement>(null);
  const ring = useRef<SVGCircleElement>(null);
  const calls = useRef({ onStart, onDone });
  calls.current = { onStart, onDone };
  const route = useRef(path).current; // fixed at launch: parent re-renders build new curve objects
  useEffect(() => {
    const path = route;
    const g = dot.current;
    const rg = ring.current;
    if (!g || !rg || typeof requestAnimationFrame === "undefined") {
      calls.current.onDone();
      return;
    }
    const t0 = performance.now() + packet.delay;
    let started = false;
    let raf = 0;
    const step = (time: number) => {
      const t = (time - t0) / FLY_MS;
      if (t >= 0 && !started) {
        started = true;
        calls.current.onStart();
      }
      if (t >= 0) {
        const k = Math.min(1, t);
        const eased = k < 0.5 ? 2 * k * k : 1 - (-2 * k + 2) ** 2 / 2;
        const p = at(path, eased);
        g.setAttribute("transform", `translate(${p.x} ${p.y})`);
        const fade = k < 0.08 ? k / 0.08 : k > 0.94 ? Math.max(0, (1 - k) / 0.06) : 1;
        g.style.opacity = String(fade);
        // The tail: the last stretch of the path behind the packet.
        const pts = [0.12, 0.08, 0.04, 0].map((dt) => at(path, Math.max(0, eased - dt)));
        tail.current?.setAttribute("points", pts.map((q) => `${q.x},${q.y}`).join(" "));
        if (tail.current) tail.current.style.opacity = String(fade * 0.85);
        // Words only mid-flight, so packets leaving and arriving at one node do not print over each other.
        if (words.current) words.current.style.opacity = String(Math.max(0, Math.min(1, (k - 0.12) / 0.08, (0.88 - k) / 0.08)));
        const after = (time - t0 - FLY_MS) / RIPPLE_MS;
        if (after > 0) {
          rg.setAttribute("r", String(7 + after * 18));
          rg.style.opacity = String(Math.max(0, 0.9 * (1 - after)));
        }
        if (after >= 1) {
          calls.current.onDone();
          return;
        }
      }
      raf = requestAnimationFrame(step);
    };
    raf = requestAnimationFrame(step);
    return () => cancelAnimationFrame(raf);
  }, [packet.delay, route]);
  const color = human ? "var(--warning)" : "var(--cyan)";
  const short = packet.text.length > 18 ? `${packet.text.slice(0, 17)}…` : packet.text;
  return (
    <g aria-hidden="true" pointerEvents="none">
      <polyline ref={tail} fill="none" stroke={color} strokeWidth={3.5} strokeLinecap="round" strokeLinejoin="round" filter="url(#team-glow)" style={{ opacity: 0 }} />
      <g ref={dot} data-packet={packet.seq} style={{ opacity: 0 }} transform={`translate(${path.a.x} ${path.a.y})`}>
        <circle r={11} fill={color} opacity={0.16} />
        <circle r={5.5} fill={color} style={{ filter: `drop-shadow(0 0 6px ${color})` }} />
        <circle r={2.2} fill="#ffffff" />
        <text ref={words} y={-14} style={{ opacity: 0 }} textAnchor="middle" fontSize="11.5" fontWeight={600} fill="var(--foreground)" stroke="var(--background)" strokeWidth={3.5} paintOrder="stroke">
          {short}
        </text>
      </g>
      <circle ref={ring} cx={path.b.x} cy={path.b.y} r={7} fill="none" stroke={color} strokeWidth={1.5} style={{ opacity: 0 }} />
    </g>
  );
}
