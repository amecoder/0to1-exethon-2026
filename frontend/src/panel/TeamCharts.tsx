import { useMemo, useState } from "react";
import { cn } from "@/lib/utils";
import type { LinerCall } from "../teamwatch/model";

const W = 640;
const H = 220;
const L = 44; // room for the y labels
const B = 26; // room for the x labels
const T = 10;
const R = 12;
const TICKS = [1000, 10_000, 60_000, 300_000];
const tickText = (ms: number) => (ms >= 60_000 ? `${ms / 60_000}분` : `${ms / 1000}초`);

function clock(t: number): string {
  return new Date(t).toLocaleTimeString("ko-KR", { hour: "2-digit", minute: "2-digit", hour12: false });
}

// X-View (as in APM tools such as JENNIFER or WhaTap): one dot per Liner call when it ended, by how long it
// took (log scale, so 1-second and 5-minute calls both stay readable). Failed calls are red crosses. Picking
// an agent dims everyone else.
export function CallScatter({ calls, label, picked }: { calls: LinerCall[]; label: (id: string) => string; picked: string | null }) {
  const [hover, setHover] = useState<LinerCall | null>(null);
  const geo = useMemo(() => {
    const times = calls.map((c) => new Date(c.ts).getTime()).filter(Number.isFinite);
    const t0 = Math.min(...times);
    const t1 = Math.max(...times);
    const span = t1 - t0 || 60_000;
    const top = Math.max(60_000, ...calls.map((c) => c.ms)) * 1.3;
    const lo = Math.log10(300);
    const hi = Math.log10(top);
    const x = (ts: string) => L + ((new Date(ts).getTime() - t0) / span) * (W - L - R);
    const y = (ms: number) => T + (1 - (Math.log10(Math.max(300, ms)) - lo) / (hi - lo)) * (H - T - B);
    return { x, y, t0, t1: t0 + span, top };
  }, [calls]);
  if (calls.length === 0) return <p className="py-6 text-center text-sm text-muted-foreground">아직 시간이 기록된 Liner 호출이 없어요</p>;
  const failed = calls.filter((c) => c.failed).length;
  const xTicks = [0, 0.5, 1].map((f) => geo.t0 + f * (geo.t1 - geo.t0));
  return (
    <div className="flex flex-col gap-1.5">
      <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-muted-foreground">
        <span className="flex items-center gap-1.5">
          <svg width="10" height="10" aria-hidden="true"><circle cx="5" cy="5" r="4" fill="var(--cyan)" /></svg>
          정상 {calls.length - failed}건
        </span>
        <span className="flex items-center gap-1.5">
          <svg width="10" height="10" aria-hidden="true"><path d="M1,1 L9,9 M9,1 L1,9" stroke="var(--destructive)" strokeWidth="2" /></svg>
          실패 {failed}건
        </span>
        <span className="text-faint">위로 갈수록 오래 걸린 호출이에요</span>
      </div>
      <div className="relative">
        <svg viewBox={`0 0 ${W} ${H}`} className="h-auto w-full" role="img" aria-label={`Liner 호출 ${calls.length}건, 실패 ${failed}건. 가로는 시각, 세로는 걸린 시간`} onMouseLeave={() => setHover(null)}>
          {TICKS.filter((ms) => ms < geo.top).map((ms) => (
            <g key={ms}>
              <line x1={L} x2={W - R} y1={geo.y(ms)} y2={geo.y(ms)} stroke="rgb(255 255 255 / 0.08)" />
              <text x={L - 6} y={geo.y(ms) + 4} textAnchor="end" fontSize="11" fill="var(--faint)">{tickText(ms)}</text>
            </g>
          ))}
          <line x1={L} x2={W - R} y1={H - B} y2={H - B} stroke="rgb(255 255 255 / 0.18)" />
          {xTicks.map((t, i) => (
            <text key={t} x={L + (i / 2) * (W - L - R)} y={H - 8} textAnchor={i === 0 ? "start" : i === 2 ? "end" : "middle"} fontSize="11" fill="var(--faint)">{clock(t)}</text>
          ))}
          {calls.map((c) => {
            const cx = geo.x(c.ts);
            const cy = geo.y(c.ms);
            const dim = picked !== null && picked !== c.actor;
            return (
              <g key={c.seq} data-call={c.seq} opacity={dim ? 0.15 : 1} onMouseEnter={() => setHover(c)}>
                <circle cx={cx} cy={cy} r={10} fill="transparent" />
                {c.failed ? (
                  <path d={`M${cx - 4},${cy - 4} L${cx + 4},${cy + 4} M${cx + 4},${cy - 4} L${cx - 4},${cy + 4}`} stroke="var(--destructive)" strokeWidth={2} />
                ) : (
                  <circle cx={cx} cy={cy} r={4} fill="var(--cyan)" fillOpacity={0.75} stroke="var(--background)" strokeWidth={1} />
                )}
              </g>
            );
          })}
        </svg>
        {hover && (
          <div
            role="status"
            className="pointer-events-none absolute z-10 -translate-x-1/2 -translate-y-full rounded-lg border border-border bg-popover px-2.5 py-1.5 text-xs whitespace-nowrap text-popover-foreground shadow-lg"
            style={{ left: `${(geo.x(hover.ts) / W) * 100}%`, top: `calc(${(geo.y(hover.ms) / H) * 100}% - 8px)` }}
          >
            <b className="font-semibold">{label(hover.actor)}</b> · {hover.kind} · {(hover.ms / 1000).toFixed(1)}초{hover.failed ? " · 실패" : ""}
            <span className="ml-1 text-muted-foreground">{clock(new Date(hover.ts).getTime())}</span>
          </div>
        )}
      </div>
    </div>
  );
}

// Who sent how many messages to whom: rows send, columns receive; darker cyan = more. Numbers are always
// printed, so the colour is never the only cue.
export function TalkMatrix({ ids, cells, max, label, picked }: {
  ids: string[];
  cells: number[][];
  max: number;
  label: (id: string) => string;
  picked: string | null;
}) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full border-separate border-spacing-0.5 text-xs tabular-nums">
        <caption className="sr-only">보낸 사람(행)이 받은 사람(열)에게 보낸 메시지 수</caption>
        <thead>
          <tr>
            <th scope="col" className="px-1 text-left font-normal text-faint">보냄 ＼ 받음</th>
            {ids.map((id) => (
              <th key={id} scope="col" className={cn("px-1 py-1 font-semibold whitespace-nowrap", picked === id ? "text-cyan" : "text-muted-foreground")}>{label(id)}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {ids.map((from, r) => (
            <tr key={from}>
              <th scope="row" className={cn("px-1 text-left font-semibold whitespace-nowrap", picked === from ? "text-cyan" : "text-muted-foreground")}>{label(from)}</th>
              {cells[r].map((n, c) => (
                <td
                  key={ids[c]}
                  title={`${label(from)} → ${label(ids[c])}: ${n}건`}
                  className={cn("h-7 min-w-9 rounded-md text-center", n ? "font-semibold text-foreground" : "text-faint")}
                  style={n ? { backgroundColor: `rgb(127 227 240 / ${(0.1 + (n / Math.max(1, max)) * 0.55).toFixed(2)})` } : { backgroundColor: "rgb(255 255 255 / 0.03)" }}
                >
                  {n || "·"}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
