import type { DecisionItem, DecisionStatus } from "../api";

// Two-step completion: 기획 완료 = CP4 approved; 결정 완료 = also nothing left on a default (가정) or undecided (미결).
export function decisionHeadline(s: DecisionStatus): { title: string; note: string } {
  const left = s.counts.assumed + s.counts.open;
  if (s.level === "결정 완료") return { title: "결정 완료", note: "기본값으로 채운 것도, 아직 정하지 않은 것도 없어요. 바로 개발을 시작해도 돼요." };
  if (s.level === "기획 완료")
    return { title: "기획 완료 · 결정은 아직", note: `개발 전에 확인할 것이 ${left}건 남았어요. 정하면 결정 완료가 돼요.` };
  return { title: "아직 확인 중", note: `프로토타입을 인수하면 기획 완료예요. 개발 전에 확인할 것은 지금 ${left}건이에요.` };
}

export interface RemainingItem extends DecisionItem {
  label: "가정" | "미결";
}

export function remainingItems(s: DecisionStatus): RemainingItem[] {
  return [
    ...s.items.assumed.map((i) => ({ ...i, label: "가정" as const })),
    ...s.items.open.map((i) => ({ ...i, label: "미결" as const })),
  ];
}
