// What the download zip carries, in words for the client. Mirrors app/export.py bundle_files():
// the role flow chart is only there when the designer drew one (screen_spec.swimlane).

export type BundleKind = "prototype" | "docs" | "lanes" | "agents" | "proposal" | "source";

export function prototypeLabel(platform: string | undefined): string {
  return platform === "web" ? "웹 프로토타입" : "앱 프로토타입";
}

export function bundleContents(platform: string | undefined, hasLanes: boolean): { kind: BundleKind; text: string }[] {
  const all: { kind: BundleKind; text: string }[] = [
    { kind: "prototype", text: `${prototypeLabel(platform)} (HTML 한 파일)` },
    { kind: "docs", text: "문서 4종 — BRD · PRD · 화면설계서 · 테스트 케이스 (마크다운)" },
    { kind: "lanes", text: "역할별 흐름도 — 누가 언제 무엇을 하는지, 예외 갈림까지 (HTML)" },
    { kind: "agents", text: "AGENTS.md — 코딩 AI에게 그대로 맡기는 작업 지시서" },
    { kind: "proposal", text: "제안요약.md — 결정하는 사람이 한 장으로 보는 사업 제안 요약" },
    { kind: "source", text: "공유 원본 (JSON) — 다른 에이전트가 이어서 쓸 수 있어요" },
  ];
  return all.filter((c) => hasLanes || c.kind !== "lanes");
}
