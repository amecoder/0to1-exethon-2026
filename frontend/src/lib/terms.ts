import { GLOSSARY, PREFIXES } from "./refCatalog";

// 「용어 사전」: every word the service shows that a newcomer may not know, in plain Korean with one example
// from this service. Steps, checks and code prefixes reuse the tooltip catalog so both always say the same.

export type TermGroup = "docs" | "flow" | "codes" | "team" | "tech";

export interface Term {
  term: string;
  group: TermGroup;
  plain: string; // what it is, in one or two plain sentences
  example: string; // where you meet it in 0to1
  aka?: string; // other spellings people search for
}

export const GROUPS: [TermGroup, string][] = [
  ["docs", "문서와 결과물"],
  ["flow", "진행 단계와 안전장치"],
  ["codes", "코드 번호"],
  ["team", "AI 에이전트 팀"],
  ["tech", "쓰는 기술"],
];

const DOCS: Term[] = [
  { term: "공유 원본", group: "docs", aka: "source.json", plain: "요구사항·화면·테스트·결정·원문을 번호로 서로 이어 놓은 하나의 데이터예요. 모든 문서는 이것에서 만들어져요.", example: "문서 4종이 서로 다른 말을 하지 않는 이유예요. 내려받기 zip 의 source.json 이 바로 이것이에요." },
  { term: "BRD", group: "docs", aka: "사업 요구사항 문서", plain: "왜 만드는지 적은 문서예요. 누가 무엇이 불편하고, 무엇이 되면 성공인지를 담아요.", example: "「배송 지연 문의가 하루 80건이라 CS 담당이 같은 답을 반복한다」 같은 배경과 목표가 들어가요." },
  { term: "PRD", group: "docs", aka: "제품 요구사항 문서", plain: "무엇을 만드는지 적은 문서예요. 요구사항마다 다 됐다고 볼 기준이 붙어요.", example: "REQ-02 「출고 후 48시간이 지나도 배송 완료가 아니면 지연으로 판정한다」 같은 문장이 모여 있어요." },
  { term: "화면설계서", group: "docs", plain: "화면마다 무엇이 어떤 순서로 있는지, 비었을 때·불러올 때·오류일 때 어떻게 보이는지 적은 문서예요.", example: "SCR-01 「지연 안내 템플릿 등록」 화면의 입력 칸, 버튼, 오류 문구가 차례로 적혀요." },
  { term: "테스트 케이스", group: "docs", aka: "TC", plain: "다 만들었는지 확인하는 시험 항목이에요. 준비 상태, 해 볼 일, 기대 결과로 이루어져요.", example: "TC-26 「금지어가 들어간 템플릿은 등록 거부」 — 「쿠폰」이 들어간 문구를 넣으면 등록이 막혀야 통과예요." },
  { term: "인수 조건", group: "docs", aka: "완료 기준 · Given/When/Then", plain: "다 됐다고 볼 수 있는 기준이에요. 「이런 상황에서(Given) 이렇게 하면(When) 이렇게 된다(Then)」 세 마디로 써요.", example: "Given 출고 후 48시간이 지난 주문 / When 수집 직후 판정하면 / Then 「지연」으로 표시된다." },
  { term: "성공 기준", group: "docs", aka: "무엇이 되면 끝인지 · 완료 조건", plain: "이 프로젝트가 끝났다고 볼 수 있는 상태예요. 요구사항 하나하나의 인수 조건과 달리 프로젝트 전체에 하나 있어요.", example: "「고객이 앱에서 배송 요일을 골라 구독을 신청하고, 사장님이 주문 목록을 볼 수 있으면 끝」이에요." },
  { term: "체크포인트", group: "flow", aka: "CP · 확인 단계 · 승인 단계", plain: "팀이 다음으로 넘어가기 전에 발주사가 결과를 보고 승인하는 지점이에요. 승인하지 않으면 그 단계를 다시 해요.", example: "CP1 문제·범위, CP2 요구사항, CP3 문서 4종, CP4 프로토타입 — 기본 4번이고, 확정 뒤에 바꿀 때마다 CP5 를 한 번 거쳐요." },
  { term: "와이어프레임", group: "docs", plain: "회색 상자로 간단히 그린 화면 뼈대예요. 색이나 그림 없이 무엇이 어디 있는지만 보여 줘요.", example: "화면설계서 안의 회색 그림이에요. 구성 요소 순서대로 시스템이 그려요." },
  { term: "프로토타입", group: "docs", plain: "실제처럼 눌러 볼 수 있는 시험용 화면이에요. 데이터는 지어낸 가짜예요.", example: "CP4 에서 폰·태블릿·데스크톱 크기를 골라 직접 눌러 보고 받을지 정해요." },
  { term: "커버리지", group: "docs", plain: "빠진 곳 없이 확인했는지 보는 연결표예요. 요구사항마다 확인할 테스트가 있는지 봐요.", example: "테스트 케이스 문서의 「커버리지 표」에서 테스트가 없는 요구사항은 「없음」으로 보여요." },
  { term: "운영 확인 항목", group: "docs", aka: "OPS", plain: "화면을 눌러 보는 대신 사람이 업무나 데이터로 확인할 것이에요.", example: "OPS-01 「출시 4주 뒤 CS 담당이 문의 태그 집계로 일평균을 본다」." },
  { term: "AI 작업 지시서", group: "docs", aka: "AGENTS.md", plain: "코딩 AI(Claude Code, Codex 등)에게 그대로 넘기는 작업 순서표예요. 할 일, 완료 기준, 통과할 테스트, 하지 말 것이 들어 있어요.", example: "내려받기 zip 의 AGENTS.md 예요. TASK-01 부터 먼저 끝나야 하는 순서대로 늘어서 있어요." },
  { term: "제안 요약", group: "docs", plain: "결재권자나 고객에게 보여 줄 한 장 요약이에요. 문제, 범위, 규모, 기대 효과, 위험, 결정할 것이 들어 있어요.", example: "내려받기 zip 의 제안요약.md 예요. 규모는 요구사항·화면 수로 「작음·보통·큼」만 정하고 금액은 추정하지 않아요." },
  { term: "작업본과 확정본", group: "docs", plain: "확정본은 프로토타입까지 승인(CP4)된 묶음이고, 작업본은 아직 확인 중인 상태의 묶음이에요.", example: "중간에 내려받으면 파일 맨 위에 「[작업본]」 표시가 붙어요." },
  { term: "확정 · 가정 · 미결 · 미확인", group: "docs", plain: "확정은 원문이나 발주사 답에 근거한 것, 가정은 근거 없이 기본값으로 채운 것, 미결은 아직 정하지 못한 것, 미확인은 인용이 원문과 글자 그대로 맞지 않은 것이에요.", example: "「잘 모르겠어요」로 답한 질문은 기본값이 들어가서 그 요구사항이 「가정」으로 표시돼요." },
  { term: "범위 (하는 것 · 하지 않는 것)", group: "docs", plain: "이번에 만드는 것과 일부러 만들지 않는 것을 나눈 목록이에요.", example: "「실시간 배송 상태 안내는 하지 않는다 — 택배사 정보가 하루 2회만 갱신된다」." },
  { term: "우리 시스템 목록", group: "docs", aka: "SYS", plain: "회사가 이미 운영하는 시스템을 한 줄씩 적은 목록이에요. 새로 만들지, 기존 시스템에 기능을 더할지, 연계할지 판단하는 데 써요.", example: "「주문관리 시스템: 주문 상태와 도착 예정일을 갖고 있어요」라고 적으면 SYS-01 이 돼요." },
];

const TEAM: Term[] = [
  { term: "AI 에이전트", group: "team", aka: "agent", plain: "역할과 권한이 정해진 AI 작업자예요. 자기 몫의 글만 쓰고, 정해진 상대하고만 이야기해요.", example: "0to1 팀은 조율자, FDE 리드, 리서처, PM, QA, 디자이너, 개발자 7명이에요. 팀 밖에서 고객 역할을 하는 소비자도 있어요." },
  { term: "발주사", group: "team", plain: "만들어 달라고 요청한 사람이에요. 화면에서 질문에 답하고 확인 단계에서 승인해요.", example: "메모를 붙여 넣고 질문 카드에 답하는 자기 자신이에요." },
  { term: "조율자", group: "team", plain: "단계 진행표대로 팀에 일을 나눠 주고 결과를 모으는 역할이에요. 발주사와 이야기하는 창구예요.", example: "QA 가 찾은 빈틈을 질문 카드로 바꿔 발주사에게 보여 줘요." },
  { term: "FDE 리드", group: "team", aka: "Forward Deployed Engineer", plain: "고객 현장에 붙어 문제를 정리하는 엔지니어 역할이에요. 원문에서 누가, 무엇이 불편한지, 무엇이 완료인지를 뽑아요.", example: "CP1 「팀이 이해한 문제가 맞는지 봐 주세요」 카드의 내용을 만들어요." },
  { term: "리서처", group: "team", plain: "Liner 검색으로 업계 관행·규정·이미 있는 제품의 근거를 찾아 출처(EV)로 남겨요.", example: "「구독 결제가 실패하면 보통 3일 안에 다시 결제한다」 같은 근거와 링크를 붙여요." },
  { term: "PM", group: "team", aka: "기획자", plain: "요구사항과 BRD·PRD 를 쓰고 우선순위를 정하는 역할이에요.", example: "발주사가 고른 답을 요구사항 문장에 그대로 넣어 확정해요." },
  { term: "QA", group: "team", aka: "품질 보증", plain: "요구사항끼리 부딪히는 곳, 빠진 예외, 확인할 수 없는 기준을 찾고 테스트 케이스를 쓰는 역할이에요.", example: "「결제가 실패하면 어떻게 할지 없어요」를 찾아 질문 카드가 생기게 해요." },
  { term: "디자이너", group: "team", plain: "요구사항을 화면설계서로 옮기고 앱인지 웹인지, 어떤 분위기로 보일지 정해요.", example: "「꽃잎이 천천히 떠다니는 3D 장면 위에 큰 제목」 같은 시각 방향을 적어요." },
  { term: "개발자", group: "team", plain: "확정된 화면설계서로 눌러 볼 수 있는 프로토타입 HTML 을 만들어요.", example: "CP4 에서 기기를 바꿔 가며 보는 화면이 개발자 에이전트가 만든 거예요." },
  { term: "소비자", group: "team", plain: "실제 고객 입장에서 화면을 보고 헷갈리거나 불편한 곳을 남기는 역할이에요.", example: "「결제가 실패했다는데 언제 다시 빠져나가는지 몰라서 불안해요」 같은 의견을 남겨요." },
];

const TECH: Term[] = [
  { term: "Liner Model API", group: "tech", plain: "라이너의 AI 모델을 부르는 통로예요. 에이전트들이 생각하고 글을 쓰는 두뇌 역할을 해요.", example: "PM 이 요구사항을 쓰거나 QA 가 빈틈을 찾을 때마다 이 API 를 한 번씩 불러요." },
  { term: "라우터 모델", group: "tech", aka: "liner-claude-router", plain: "질문마다 알맞은 모델을 골라 대신 답하게 하는 모델이에요. 비용과 품질 중 무엇을 우선할지 고를 수 있어요.", example: "에이전트마다 「비용 우선」·「품질 우선」을 따로 정해 두었어요." },
  { term: "Liner Search · AI Search", group: "tech", plain: "웹과 학술 자료를 검색해 제목, 본문 일부, 출처 주소, 날짜를 정리해 돌려주는 API 예요.", example: "리서처가 「꽃 정기구독 결제 실패 처리 관행」을 찾아 근거로 남길 때 써요." },
  { term: "Liner Decisions", group: "tech", aka: "근거 판정", plain: "어떤 문장이 인용한 근거로 정말 뒷받침되는지 확률로 판정하는 API 예요.", example: "확률이 낮으면 「근거가 문장을 잘 뒷받침하는지 확률이 낮아요」 참고 표시가 붙어요." },
  { term: "Liner 시각화 · 이미지 · 음성 받아쓰기", group: "tech", plain: "흐름도를 그리고, 상품 사진을 만들고, 회의 녹음을 글로 받아 적는 Liner 기능들이에요.", example: "회의 녹음을 올리면 받아 적은 글이 원문(SRC)으로 들어가요." },
  { term: "LLM", group: "tech", aka: "대규모 언어 모델", plain: "많은 글을 배워 사람처럼 글을 이해하고 쓰는 AI 모델이에요.", example: "Liner Model API 뒤에서 실제로 답을 쓰는 것이 LLM 이에요." },
  { term: "툴 콜링", group: "tech", aka: "tool calling", plain: "AI 가 필요할 때 검색 같은 도구를 스스로 불러 쓰는 방식이에요.", example: "FDE 리드가 「이미 있는 제품이 있나요?」 검색을 요청하면 리서처가 Liner Search 를 불러요." },
  { term: "JSON 출력 형식", group: "tech", aka: "JSON Schema", plain: "AI 의 답을 정해진 칸에 맞춰 받는 방식이에요. 칸이 정해져 있어서 코드가 그대로 검사할 수 있어요.", example: "요구사항은 제목·진술·인수 조건·상태 칸이 정해진 형식으로만 받아요." },
  { term: "격리 미리보기", group: "tech", aka: "sandbox · CSP", plain: "프로토타입을 바깥 인터넷과 통신할 수 없는 칸 안에서만 여는 방식이에요. 만든 화면이 몰래 정보를 내보내지 못해요.", example: "프로토타입 위에 「안전한 칸 안에서 열려요」라고 적힌 이유예요(안전장치 G6)." },
  { term: "민감정보 가리기", group: "tech", aka: "G3", plain: "주민번호·카드번호·전화번호·키 같은 값을 저장하거나 AI 에 보내기 전에 찾아 막거나 가리는 장치예요.", example: "메모에 카드번호가 있으면 「민감 정보가 있어서 아직 보내지 않았어요」가 떠요." },
  { term: "three.js", group: "tech", plain: "웹 화면에 3D 장면을 그리는 공개 라이브러리(MIT 라이선스)예요.", example: "프로토타입 첫 화면에 떠 있는 빛나는 구나 카드가 three.js 로 그린 거예요." },
  { term: "FastAPI · React · SQLite", group: "tech", plain: "FastAPI 는 서버, React 는 화면, SQLite 는 파일 하나로 된 데이터베이스예요. 별도 DB 서버 없이 바로 실행돼요.", example: "프로젝트는 지우지 않고 SQLite 파일에 모두 보관해요. 시작 화면의 「전체 보기」가 그 목록이에요." },
];

export const TERMS: Term[] = [
  ...DOCS,
  ...GLOSSARY.map(([code, kind, title, about]): Term => ({ term: `${code} ${title}`, group: "flow", aka: kind, plain: about, example: `화면 곳곳에 「${code}」로 줄여 써요.` })),
  ...Object.entries(PREFIXES)
    .filter(([prefix]) => !["CP", "S", "G"].includes(prefix))
    .map(([prefix, [kind, about]]): Term => ({ term: `${prefix}- ${kind}`, group: "codes", plain: about, example: `예: ${prefix}-01. 화면에서 이 번호에 마우스를 올리면 무엇인지 보여요.` })),
  ...TEAM,
  ...TECH,
];

// Search over the word, other spellings, explanation and example; an empty query keeps everything.
export function searchTerms(query: string, group: TermGroup | "all" = "all", terms: Term[] = TERMS): Term[] {
  const q = query.trim().toLowerCase();
  return terms.filter((t) => (group === "all" || t.group === group)
    && (!q || [t.term, t.aka ?? "", t.plain, t.example].some((s) => s.toLowerCase().includes(q))));
}

// The entry for a word shown on screen (11-22: technical words with a tooltip). Matches the term itself or one
// of its other spellings (aka, separated by 「 · 」).
export function findTerm(name: string, terms: Term[] = TERMS): Term | undefined {
  const key = name.trim();
  return terms.find((t) => t.term === key) ?? terms.find((t) => (t.aka ?? "").split(" · ").includes(key));
}
