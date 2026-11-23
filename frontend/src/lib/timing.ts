// How long the current stage has been running, and an honest "usually" hint for it.
import type { AppEvent } from "../api";

// Typical lower bound per stage = Liner calls the stage makes × median single-call latency.
// Median 4.2 s: liner-claude-router, 10 calls, 2026-11-16 Korean smoke (eval/results/smoke-20261116-161603.jsonl).
// Calls per stage counted from a full pipeline run (demo recording). Long answers (documents, HTML) take longer,
// so this is shown as "at least", not as a promise.
export const MEDIAN_CALL_S = 4.2;
export const MEASURED_ON = "2026-11-16";
const STAGE_CALLS: Record<string, number> = { S2: 4, S3: 3, S4: 1, S5: 10, S6: 4 };

export interface StageTiming {
  elapsedS: number;
  typical: { calls: number; atLeastS: number } | null;
}

export function stageTiming(events: AppEvent[], stage: string, now: number): StageTiming | null {
  let started: string | null = null;
  for (const e of events) if (e.type === "stage_started" && e.data?.stage === stage) started = e.ts;
  if (!started) return null;
  const elapsedS = Math.max(0, Math.round((now - Date.parse(started)) / 1000));
  const calls = STAGE_CALLS[stage];
  return { elapsedS, typical: calls ? { calls, atLeastS: Math.round(calls * MEDIAN_CALL_S) } : null };
}

export function formatDuration(seconds: number): string {
  const s = Math.max(0, Math.round(seconds));
  if (s < 60) return `${s}초`;
  const rest = s % 60;
  return rest ? `${Math.floor(s / 60)}분 ${rest}초` : `${Math.floor(s / 60)}분`;
}
