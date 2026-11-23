// The change lane (FR-21 change requests, FR-22 「아 이거 아닌데?」) as thread items. Pure, unit-tested.
import type { ChangeItem, ComplaintItem, Impact, Recheck, SharedSourceData } from "../../api";

export type LaneEntry = { kind: "change"; item: ChangeItem } | { kind: "complaint"; item: ComplaintItem };

export function laneEntries(source: SharedSourceData): LaneEntry[] {
  const changes = ((source.changes as ChangeItem[] | undefined) ?? []).map((item): LaneEntry => ({ kind: "change", item }));
  const complaints = ((source.complaints as ComplaintItem[] | undefined) ?? []).map(
    (item): LaneEntry => ({ kind: "complaint", item }),
  );
  return [...changes, ...complaints].sort((x, y) => x.item.created_at.localeCompare(y.item.created_at));
}

// A short signature that changes whenever an entry is added or moves to another status (drives scrolling).
export function laneSignature(entries: LaneEntry[]): string {
  return entries.map((e) => `${e.item.id}:${e.item.status}`).join("|");
}

export function laneBusy(entries: LaneEntry[]): boolean {
  return entries.some((e) => e.item.status === "mapping" || e.item.status === "checking");
}

export function pendingChange(entries: LaneEntry[]): ChangeItem | null {
  const hit = entries.find((e) => e.kind === "change" && (e.item.status === "mapping" || e.item.status === "awaiting_cp5"));
  return hit ? (hit.item as ChangeItem) : null;
}

export function impactIds(impact: Impact | undefined): string[] {
  return impact ? [...impact.requirements, ...impact.screens, ...impact.tests] : [];
}

// How a requirement in the impact set relates to the change: the target, a direct dependent, or further down.
export type ImpactLayer = "target" | "direct" | "transitive";

export function impactLayer(id: string, item: Pick<ChangeItem, "target" | "direct">): ImpactLayer {
  if (id === item.target) return "target";
  return item.direct === undefined || item.direct.includes(id) ? "direct" : "transitive";
}

// Requirements ordered target → direct → transitive (stable inside each layer).
export function layeredRequirements(item: Pick<ChangeItem, "target" | "direct" | "impact">): { id: string; layer: ImpactLayer }[] {
  const order: ImpactLayer[] = ["target", "direct", "transitive"];
  const rows = (item.impact?.requirements ?? []).map((id) => ({ id, layer: impactLayer(id, item) }));
  return order.flatMap((layer) => rows.filter((r) => r.layer === layer));
}

export function impactCount(impact: Impact | undefined): number {
  return impactIds(impact).length;
}

// Was the latest unanswered complaint a new change request? Then the composer can offer the conversion.
export function convertible(item: ComplaintItem, entries: LaneEntry[]): boolean {
  if (item.status !== "classified" || item.classification !== "새 변경 요청") return false;
  return !entries.some((e) => e.kind === "change" && e.item.complaint_ref === item.id);
}

// "11월 16일 01:20" in Korea time — when a confirmation was recorded.
export function formatAt(iso: string | undefined | null): string {
  if (!iso) return "";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  return new Intl.DateTimeFormat("ko-KR", {
    timeZone: "Asia/Seoul", month: "long", day: "numeric", hour: "2-digit", minute: "2-digit", hour12: false,
  }).format(d);
}

export const CP_NO: Record<string, number> = { CP1: 1, CP2: 2, CP3: 3, CP4: 4, CP5: 5 };

const REDO_LABEL: Record<string, string> = {
  documents: "문서 4종",
  screens: "화면설계",
  tests: "테스트 케이스",
  prototype: "프로토타입",
};

// After a CP5 change: why the zip is locked and the client's next step on the way back to CP4.
export function recheckView(recheck: Recheck, pipeline: { stage: string; status: string } | undefined) {
  const stage = pipeline?.stage ?? recheck.stage;
  const status = pipeline?.status ?? "running";
  let next = "PM이 어긋나는 요구사항을 고치고, 팀이 그 요구사항으로 문서를 다시 쓰고 있어요";
  if (status === "failed" || status === "stopped") next = "작업이 멈췄어요. 아래 카드에서 다시 시도해 주세요";
  else if (stage === "CP3") next = "다시 만든 문서 4종을 확인 3에서 승인해 주세요";
  else if (stage === "S6") next = "승인한 문서로 프로토타입을 다시 만들고 있어요";
  else if (stage === "CP4") next = "새 프로토타입을 확인 4에서 인수하면 내려받기가 다시 열려요";
  return {
    title: `변경 ${recheck.change_id} 반영(${recheck.version}) — 확인 4를 다시 받을 때까지 내려받기를 잠갔어요`,
    redo: recheck.kinds.map((k) => REDO_LABEL[k] ?? k),
    next,
  };
}
