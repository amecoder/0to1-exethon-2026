// Money spent on Liner for one project, from the system's credit balance readings (`credits` events):
// the first recorded balance minus the latest one. Same rule as app/limits.py spent_usd.
import type { AppEvent } from "../api";

export function spentUsd(events: AppEvent[]): number | null {
  const readings = events
    .filter((e) => e.type === "credits" && typeof e.data?.balance_usd === "number")
    .map((e) => e.data.balance_usd as number);
  if (readings.length === 0) return null;
  return Math.max(0, readings[0] - readings[readings.length - 1]);
}

// "$0.0123" — four decimals because single calls cost fractions of a cent.
export function formatUsd(value: number): string {
  if (value > 0 && value < 0.0001) return "<$0.0001";
  return `$${value.toFixed(value >= 1 ? 2 : 4)}`;
}

export type BudgetLevel = "normal" | "caution" | "warning";

// Design-token classes per level (text + bar fill).
export const BUDGET_TONE: Record<BudgetLevel, { text: string; bar: string }> = {
  normal: { text: "text-cyan", bar: "bg-cyan" },
  caution: { text: "text-warning", bar: "bg-warning" },
  warning: { text: "text-destructive", bar: "bg-destructive" },
};

export interface BudgetView {
  budget: number;
  ratio: number; // spent / budget, not clamped (G7 checks at stage end, so a run can pass the budget)
  level: BudgetLevel; // <60% normal, 60–85% caution, ≥85% warning
  over: number | null; // dollars past the budget
  chip: string; // "$3.20 / $5.00"
  line: string; // "예산 $5.00 중 $3.20 사용 (64%)" (+ " · 예산 초과 $2.60")
}

// Spent against the G7 budget (EXETHON_MAX_COST_USD). Null when either side is unknown.
export function budgetView(spent: number | null, budget: number | null | undefined): BudgetView | null {
  if (spent == null || budget == null || budget <= 0) return null;
  const ratio = spent / budget;
  const level: BudgetLevel = ratio >= 0.85 ? "warning" : ratio >= 0.6 ? "caution" : "normal";
  const over = spent > budget ? spent - budget : null;
  const base = `예산 ${formatUsd(budget)} 중 ${formatUsd(spent)} 사용 (${Math.round(ratio * 100)}%)`;
  return {
    budget,
    ratio,
    level,
    over,
    chip: `${formatUsd(spent)} / ${formatUsd(budget)}`,
    line: over != null ? `${base} · 예산 초과 ${formatUsd(over)}` : base,
  };
}

// Budget mode (app/limits.py): from 60% of the G7 budget the router answers with the cheap model.
// On once the system's one G7 `flagged` switch event is in the log.
export function budgetModeOn(events: AppEvent[]): boolean {
  return events.some(
    (e) => e.type === "guardrail" && e.data?.id === "G7" && e.data?.outcome === "flagged" && e.data?.limit === "budget_mode",
  );
}
