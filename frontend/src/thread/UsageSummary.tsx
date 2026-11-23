import type { AppEvent } from "../api";
import { cn } from "@/lib/utils";
import { BUDGET_TONE, budgetModeOn, budgetView, formatUsd } from "../lib/credits";
import { linerUsage, tokenText } from "../lib/usage";

// Liner calls and cost per API kind, read from this project's event log (header cost chip → popover).
export default function UsageSummary({ events, spent, budget }: { events: AppEvent[]; spent: number | null; budget?: number | null }) {
  const rows = linerUsage(events);
  const view = budgetView(spent, budget);
  const calls = rows.reduce((n, r) => n + r.calls, 0);
  return (
    <div className="flex flex-col gap-3 text-sm">
      <p className="font-semibold text-foreground">
        Liner 사용 · 호출 {calls}회{spent != null && ` · 쓴 비용 ${formatUsd(spent)}`}
      </p>
      <p className={cn("text-sm", view ? BUDGET_TONE[view.level].text : "text-muted-foreground")}>
        {view ? view.line : budget == null ? "예산 없음" : "아직 쓴 비용을 읽지 못했어요"}
      </p>
      {budgetModeOn(events) && <p className="text-sm text-warning">예산 모드: 켜짐(싼 모델)</p>}
      {rows.length === 0 ? (
        <p className="text-muted-foreground">아직 Liner 를 부르지 않았어요.</p>
      ) : (
        <table className="w-full text-left">
          <thead className="text-xs text-muted-foreground">
            <tr>
              <th className="py-1 pr-3 font-medium">API</th>
              <th className="py-1 pr-3 text-right font-medium">호출</th>
              <th className="py-1 pr-3 text-right font-medium">토큰</th>
              <th className="py-1 text-right font-medium">비용</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.kind} className="border-t border-white/[0.06] align-top">
                <td className="py-1.5 pr-3">
                  <span className="text-soft">{r.label}</span>
                  {r.models.length > 0 && (
                    <span className="block text-xs break-all text-faint">
                      {r.kind === "chat" ? "답한 모델 " : "모델 "}
                      {r.models.join(", ")}
                    </span>
                  )}
                </td>
                <td className="py-1.5 pr-3 text-right tabular-nums text-soft">{r.calls}</td>
                <td className="py-1.5 pr-3 text-right text-xs tabular-nums text-soft">{tokenText(r)}</td>
                <td className="py-1.5 text-right tabular-nums text-soft">{r.cost == null ? "—" : formatUsd(r.cost)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      <p className="text-xs break-keep text-faint">
        호출 수는 활동 기록에서 셌어요. 토큰·비용은 Liner 가 호출마다 알려 준 값의 합(— 는 알려 주지 않음)이고, 위의 쓴 비용은 크레딧 잔액 차이예요.
      </p>
    </div>
  );
}
