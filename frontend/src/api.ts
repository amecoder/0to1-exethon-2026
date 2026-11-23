// Typed wrappers around the FastAPI backend (/api/*).
import type { TeamDefault } from "./thread/teamDefaults";

export type Mode = "demo" | "real";

export interface Relation {
  from: string;
  to: string;
  carries: string;
}

export interface Team {
  id: string;
  name: string;
  members: string[];
  coordinator: string;
  external: { id: string; kind: "human" | "agent" }[];
  relations: Relation[];
}

export interface Agent {
  id: string;
  name: string;
  role: string;
  tools: string[];
  draft: boolean;
}

export type Status = "확정" | "가정" | "미결" | "미확인";

export interface Requirement {
  id: string;
  title: string;
  statement: string;
  category: string;
  priority: string;
  acceptance: { given: string; when: string; then: string };
  exceptions: string[];
  status: Status;
  source_refs: string[];
  evidence_refs: string[];
  decision_refs: string[];
  depends_on: string[];
  system_refs?: string[]; // 「우리 시스템 목록」 systems this requirement changes or connects to (SYS-)
  change?: Change;
  feature_refs?: string[]; // features of a service built with 0to1 this requirement builds on (SYS-03/REQ-02)
}

// How a requirement is built when the client listed its own systems: new, added to a system, connected to one,
// or already there and used as it is (재사용).
export type Change = "신규" | Fit;
export type Fit = "기능 추가" | "연계" | "재사용";

export interface OurSystem {
  id: string;
  name: string;
  about: string;
}

export interface SystemFit {
  system_ref: string;
  name: string;
  fit: Fit;
  what: string;
  refs: string[];
  quote: string;
  status: "확인" | "미확인";
}

export interface SourceSentence {
  id: string;
  text: string;
  // audio: transcribed from a recording (Liner speech-to-text); image/document: read from an attached file
  origin?: "audio" | "image" | "document";
  origin_note?: string;
  attachment_file?: string;
}

export interface Evidence {
  id: string;
  query: string;
  url: string;
  quote: string;
  fact: string;
  status: "확인" | "미확인";
  title?: string;
  date?: string;
  via?: "ai_search" | "search";
  support?: number;
  support_note?: string;
}

export interface QuestionCard {
  id: string;
  question: string;
  why: string;
  options: string[];
  unknown_option: string;
  default_option: string;
  allow_free_text?: boolean; // false: only the options (the server refuses a written answer)
  source_refs: string[];
  evidence_refs: string[];
  status?: "pending" | "answered";
  answer?: { kind: string; value: string; status: string } | null;
}

export interface Claim {
  text: string;
  refs: string[];
  quote: string;
  status: "확인" | "미확인";
  support?: number; // Liner Decisions: probability that the quote supports the sentence
  support_note?: string; // 참고 note when that probability is low (never blocks)
}

export interface ProblemStatement {
  who: string;
  pain: string;
  done: string;
  claims: Claim[];
  interpretations: Claim[];
}

// The team's answer to what the client asked at a confirmation instead of approving (answer desk).
export interface ClientReply {
  id: string;
  cp: string;
  question: string;
  answer: string;
  refs: string[];
  intent: "question" | "change" | "both";
  searched: boolean;
}

// An existing product that already does (part of) what the memo asks — build-or-buy at CP1.
export interface Alternative {
  id: string;
  name: string;
  covers: string;
  lacks: string;
  url: string;
  quote: string;
  evidence_refs: string[];
  status: "확인" | "미확인";
}

export interface Scope {
  in: Claim[];
  out: Claim[];
  systems?: SystemFit[];
}

export interface AppEvent {
  seq: number;
  ts: string;
  stage: string | null;
  type: string;
  actor: string;
  data: Record<string, any>;
}

export interface Pipeline {
  stage: string;
  status:
    | "awaiting_input"
    | "running"
    | "awaiting_answers"
    | "awaiting_scope"
    | "awaiting_confirmation"
    | "stopped"
    | "failed"
    | "completed"
    | "closed";
  active_agent: string | null;
  error: string | null;
}

// Set when a CP5 change made the delivered work stale; cleared by the next CP4 approval.
export interface Recheck {
  change_id: string;
  version: string;
  stage: string;
  kinds: string[];
  items: string[];
}

export interface SharedSourceData {
  meta: { pipeline?: Pipeline; recheck?: Recheck };
  sources: SourceSentence[];
  evidence: Evidence[];
  requirements: Requirement[];
  questions: QuestionCard[];
  problem_statement: ProblemStatement[];
  scope: Scope[];
  alternatives?: Alternative[];
  systems?: OurSystem[];
  replies?: ClientReply[];
  open_items: { id: string; title: string; reason: string }[];
  events: AppEvent[];
  [key: string]: unknown;
}

export interface CheckWarning {
  id: string;
  code: string;
  severity: "block" | "waivable" | "info";
  target: string;
  doc: string;
  message: string;
  explain?: string; // 11-22: a 빈칸 in plain words (app/waiver_help.py)
  suggested?: string; // 11-22: a reason filled in by the team; the client may edit it
}

export interface AnswerRow {
  question_id: string;
  question: string;
  answer: string;
  answer_kind: "choice" | "unknown" | "free_text";
  status: string;
  decision_id: string;
  answered_by?: string; // "company": settled by the company material at S3 (company_ref = CMP-xx), not a card answer
  company_ref?: string | null;
  requirements: { id: string; title: string; statement: string; status: string }[];
  consistent: boolean;
}

// FR-20: the consumer agent's opinion on one screen (info only — never blocks approval).
export interface FeedbackItem {
  id: string;
  cp: "CP3" | "CP4";
  target: "screens" | "prototype";
  screen_id: string;
  kind: "헷갈림" | "불편" | "포기 위험";
  comment: string;
}

export interface Review {
  cp: string;
  summary: string;
  answers: AnswerRow[];
  blocking: CheckWarning[];
  waivable: CheckWarning[];
  notices: CheckWarning[];
  can_approve: boolean;
  consumer_feedback?: FeedbackItem[];
}

export interface Impact {
  requirements: string[];
  screens: string[];
  tests: string[];
}

export interface Decided {
  confirmation_id: string;
  who: string;
  at: string;
  reason: string | null;
}

// FR-21: a change request and its CP5 decision.
export interface ChangeItem {
  id: string;
  utterance: string;
  status: "mapping" | "awaiting_cp5" | "approved" | "rejected" | "unmapped" | "unrelated" | "no_change" | "failed";
  created_at: string;
  based_on: string;
  complaint_ref: string | null;
  target?: string;
  title?: string;
  before?: string;
  after?: string;
  summary?: string;
  impact?: Impact;
  recheck?: { agent: string; items: string[] }[];
  version?: string;
  decided?: Decided;
  error?: string;
  limit?: boolean;
  candidates?: { id: string; title: string; score: number }[]; // Liner Rerank top 5 handed to the PM
  direct?: string[]; // the target and the requirements that depend on it directly (rest of the impact is transitive)
  revision?: ChangeRevision; // after CP5: what the PM rewrote so the requirements agree with the change
  history?: string[]; // earlier approved changes to the same requirement
  reverts_to?: string | null; // the fixed version whose statement this change brings back (a reversal)
}

export interface RequirementText {
  title: string;
  statement: string;
  acceptance: { given: string; when: string; then: string };
  exceptions: string[];
}

export interface ChangeRevision {
  requirements: { id: string; fields: string[]; before: RequirementText; after: RequirementText }[];
  scope: string[];
  before_keys: string[];
  after_key: string;
}

export interface ComplaintEvidence {
  requirement: { id: string; title: string; statement: string; acceptance?: { given: string; when: string; then: string }; status?: string };
  confirmation: { id: string; cp: string; who: string; at: string; version: string | null } | null;
}

// FR-22: 「아 이거 아닌데?」 compared with the latest confirmed version.
export interface ComplaintItem {
  id: string;
  text: string;
  status: "checking" | "classified" | "unmatched" | "unrelated" | "failed";
  created_at: string;
  against: string;
  classification?: "합의 위반" | "새 변경 요청";
  model_classification?: string;
  requirement_ids?: string[];
  requested?: string;
  reason?: string;
  evidence?: ComplaintEvidence[];
  guard?: { applied: boolean; detail: string | null; requirement_id?: string };
  decision?: ComplaintDecision;
  needs_human?: boolean;
  error?: string;
  limit?: boolean;
}

// Liner Decisions `choice` over violation / new_change (the code guard still has the final say).
export interface ComplaintDecision {
  choice: "violation" | "new_change" | null;
  label: "합의 위반" | "새 변경 요청" | null;
  probabilities: Record<string, number>;
  confidence: number | null;
  threshold: number;
  model?: string | null;
  error: string | null;
}

export interface FlowChart {
  id: string;
  html: string;
  description: string;
  based_on: string[];
  violations: { code: string; detail: string; action: "stripped" }[];
}

// S5 role swimlane (역할별 레인 흐름도) on the screen_spec item; drawn as an SVG by the server.
export interface SwimlaneStep {
  id: string;
  lane: string;
  label: string;
  screen_ref: string;
  after: string[];
  kind: "normal" | "exception";
  note: string;
}

export interface Swimlane {
  lanes: string[];
  steps: SwimlaneStep[];
}

export interface Lane {
  open: boolean;
  busy: boolean;
  reason: string | null;
}

export interface TableBlock {
  type: "table";
  columns: string[];
  rows: string[][];
}

export type Block =
  | TableBlock
  | { type: "paragraph"; text: string }
  | { type: "list"; items: string[] }
  | {
      type: "screen";
      id: string;
      title: string;
      purpose: string;
      svg: string;
      elements: TableBlock;
      states: TableBlock;
    };

export interface DocView {
  id: string;
  title: string;
  header: {
    owner_agent: string;
    owner_name: string;
    version: string;
    approvals: { id: string; cp: string; who: string; at: string; version: string }[];
  };
  summary: string[];
  sections: { id: string; title: string; blocks: Block[] }[];
  warnings: CheckWarning[];
}

export type DocId = "brd" | "prd" | "screens" | "tests";

export type Todo = (
  | { kind: "input" }
  | {
      kind: "confirmation";
      cp: "CP1" | "CP2" | "CP3" | "CP4";
      title: string;
      review?: Review;
      req_reviews?: ReqReviews;
      decision_status?: DecisionStatus; // CP4 only
    }
  | { kind: "download"; decision_status?: DecisionStatus }
  | { kind: "closed"; chosen: string | null; alternative: Alternative | null }
  | { kind: "question"; question: QuestionCard; remaining: number; total?: number; answered?: QuestionCard[]; sources: SourceSentence[]; evidence: Evidence[] }
  | { kind: "answers_review"; questions: QuestionCard[]; defaults?: TeamDefault[] }
  | { kind: "scope"; screens: { id: string; title: string; purpose: string; requirement_refs: string[] }[]; max: number }
  | { kind: "limit"; limit: "calls" | "time" | "cost" | null; used: number | null; max: number | null; stage: string; message: string | null }
  | { kind: "none"; status?: string }
) & { recheck?: Recheck };

export interface Prototype {
  id: string;
  html: string;
  origin: "agent" | "template";
  attempts: number;
  based_on: string;
  summary: string[];
  violations: { code: string; detail: string; action: "stripped" | "rejected" }[];
  missing_screens: string[];
  platform?: "app" | "web"; // app: phone frames · web: desktop to mobile (older prototypes: app)
}

export interface ChecklistRow {
  tc_id: string;
  title: string;
  screens: { id: string; present: boolean }[];
  result: string;
  reason?: string; // 「화면 없이 확인」: why the requirement has no screen (screen spec)
}

export interface DemoMeta {
  kind: "fake" | "real";
  notice: string;
  recorded_at: string;
  model: string | null;
  project_name: string;
  total: number;
  // Header of a recording exported from a real web run (scripts/export_demo.py); null on older files.
  models?: string[] | null;
  total_cost_usd?: number | null;
  duration_seconds?: number | null;
  max_cost_usd?: number | null; // the run's G7 budget, when the recording header has one
  operator_note?: string | null; // who played the client in the recorded run (e.g. the dev team as a stand-in)
}

export interface ProjectSummary {
  id: string;
  name: string;
  mode: Mode;
  created_at: string;
  stage: string | null;
  status: string | null;
  completed: boolean;
}

// 회사 작업 공간 (app/routes_company.py): no login — the start screen chooses one, projects are listed per company.
export interface CompanySummary {
  id: string;
  name: string;
  created_at: string;
  projects: number;
}

export interface PastDecision {
  project: string;
  project_id: string;
  decision_id: string;
  topic: string;
  chosen: string;
}

export interface CompanyDetail {
  id: string;
  name: string;
  created_at: string;
  systems: string; // 「우리 시스템 목록」, prefilled into each new request
  notes: string; // 회사 공통 자료: 용어·사내 규칙·이미 정한 것, one per line
  past_decisions?: PastDecision[];
  services?: BuiltService[]; // projects of this company confirmed at CP4 — added to each new request's systems list
}

export interface BuiltService {
  project_id: string;
  name: string;
  features: { id: string; title: string; statement: string; screens: string[] }[];
}

export interface DemoState {
  step: number;
  total: number;
  event: AppEvent | null;
  source: SharedSourceData;
  documents: Record<DocId, DocView> | null;
  todo: Todo;
}

export interface Project {
  id: string;
  name: string;
  mode: Mode;
  created_at: string;
  source: SharedSourceData;
  todo?: Todo;
  lane?: Lane;
  budget_usd?: number | null; // G7 EXETHON_MAX_COST_USD, read-only; null when unset
  delivery?: Delivery;
  company_id?: string;
}

// Whether a zip can be taken now: ready once the documents exist; final only while the latest CP4 is current.
export interface Delivery {
  ready: boolean;
  final: boolean;
  note: string;
}

export interface AudioResult {
  filename: string;
  text: string;
  chars: number;
}

export interface AttachmentResult {
  filename: string;
  kind: "image" | "document";
  text: string;
  chars: number;
}

export interface SystemsFromFile {
  filename: string;
  kind: "image" | "document";
  lines: string[];
}

export interface InputResult {
  blocked: boolean;
  message?: string;
  kinds?: string[];
  guard?: "G3" | "G9" | null; // G3: sensitive info, can be masked and sent · G9: harmful purpose, cannot
}

// S1 intake triage (POST /input/triage): judged before anything is sent to the team.
export type TriageSlot = "who" | "pain" | "done";
export type TriageSlots = Record<TriageSlot, string>;
export interface TriageQuestion {
  slot: TriageSlot;
  question: string;
}
export interface TriageAnswer extends TriageQuestion {
  answer: string;
}
export type TriageCase = "ok" | "cannot" | "garbled" | "insufficient";
export interface TriageVerdict {
  blocked: false;
  case: TriageCase;
  reason: string;
  slots: TriageSlots;
  questions: TriageQuestion[];
}
export interface TriageBlocked {
  blocked: true;
  message: string;
  kinds: string[];
  guard: "G3" | "G9"; // G9: harmful purpose (refused before more questions), no masking
}
export type TriageResult = TriageVerdict | TriageBlocked;

// CP2 card review: per requirement 확정 (ok) or 고칠 점 (fix + note); null = not looked at yet.
export interface ReqReviews {
  items: { id: string; verdict: "ok" | "fix" | null; note: string | null }[];
  ok: number;
  fix: number;
  open: number;
  total: number;
}

// 결정 현황 over requirements + decisions + open items. 기획 완료 = CP4 approved; 결정 완료 = also no 가정·미결.
export interface DecisionItem {
  id: string;
  title: string;
}

export interface DecisionStatus {
  counts: { confirmed: number; assumed: number; open: number };
  items: { confirmed: DecisionItem[]; assumed: DecisionItem[]; open: DecisionItem[] };
  planning_done: boolean;
  decision_done: boolean;
  level: "기획 완료" | "결정 완료" | null;
}

// GitHub 연동: this browser's sign-in state only (per-browser session cookie) — the token never reaches it.
export interface GitHubStatus {
  configured: boolean;
  connected: boolean;
  login: string | null;
  pending: { user_code: string; verification_uri: string; interval: number; expires_in: number } | null;
}

export interface GitHubPush {
  repo: string;
  url: string;
  branch: string;
  commit: string;
  commit_url: string;
  created: boolean;
  files: number;
  final: boolean;
  message: string;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...init,
  });
  const body = await response.json().catch(() => ({}));
  if (!response.ok) {
    const detail = typeof body.detail === "string" ? body.detail : `요청 실패 (HTTP ${response.status})`;
    throw new Error(detail);
  }
  return body as T;
}

export const api = {
  keyStatus: () => request<{ present: boolean }>("/api/liner/key-status"),
  agents: () => request<{ agents: Agent[] }>("/api/agents").then((r) => r.agents),
  team: (id: string) => request<Team>(`/api/teams/${encodeURIComponent(id)}`),
  createProject: (name: string, mode: Mode, companyId?: string) =>
    request<Project>("/api/projects", {
      method: "POST",
      body: JSON.stringify(companyId ? { name, mode, company_id: companyId } : { name, mode }),
    }),
  projects: (limit = 20, companyId?: string) =>
    request<{ projects: ProjectSummary[]; total: number }>(
      `/api/projects?limit=${limit}${companyId ? `&company=${encodeURIComponent(companyId)}` : ""}`,
    ),
  companies: () => request<{ companies: CompanySummary[] }>("/api/companies").then((r) => r.companies),
  createCompany: (name: string) =>
    request<CompanyDetail>("/api/companies", { method: "POST", body: JSON.stringify({ name }) }),
  company: (id: string) => request<CompanyDetail>(`/api/companies/${encodeURIComponent(id)}`),
  saveCompany: (id: string, systems: string, notes: string) =>
    request<CompanyDetail>(`/api/companies/${encodeURIComponent(id)}`, {
      method: "PUT",
      body: JSON.stringify({ systems, notes }),
    }),
  features: () => request<{ company: boolean }>("/api/features"),
  exampleMemo: () => request<{ name: string; text: string }>("/api/sample-memo"),
  project: (id: string) => request<Project>(`/api/projects/${encodeURIComponent(id)}`),
  renameProject: (id: string, name: string) =>
    request<{ name: string }>(`/api/projects/${encodeURIComponent(id)}/name`, { method: "PUT", body: JSON.stringify({ name }) }),
  submitInput: (id: string, chunks: string[], mask: boolean, audio = false, systems = "", attachments = false) =>
    request<InputResult>(`/api/projects/${encodeURIComponent(id)}/input`, {
      method: "POST",
      body: JSON.stringify({ chunks, mask, audio, systems, attachments }),
    }),
  triageInput: (id: string, chunks: string[], answers: TriageAnswer[], mask: boolean, audio = false, attachments = false) =>
    request<TriageResult>(`/api/projects/${encodeURIComponent(id)}/input/triage`, {
      method: "POST",
      body: JSON.stringify({ chunks, answers, mask, audio, attachments }),
    }),
  // Raw bytes like uploadAudio. memo: the text waits on the server until 「팀에게 보내기」.
  uploadAttachment: (id: string, file: File) =>
    request<AttachmentResult>(
      `/api/projects/${encodeURIComponent(id)}/input/attachment?purpose=memo&filename=${encodeURIComponent(file.name)}`,
      { method: "POST", headers: { "Content-Type": "application/octet-stream" }, body: file },
    ),
  removeAttachment: (id: string, filename: string) =>
    request<{ removed: boolean }>(
      `/api/projects/${encodeURIComponent(id)}/input/attachment?filename=${encodeURIComponent(filename)}`,
      { method: "DELETE" },
    ),
  // 「우리 시스템 목록」 from a file: returns 「이름: 하는 일」 lines; nothing is kept on the server.
  systemsFromFile: (id: string, file: File) =>
    request<SystemsFromFile>(
      `/api/projects/${encodeURIComponent(id)}/input/attachment?purpose=systems&filename=${encodeURIComponent(file.name)}`,
      { method: "POST", headers: { "Content-Type": "application/octet-stream" }, body: file },
    ),
  // Raw bytes in the body (the server checks size and format before calling Liner speech-to-text).
  uploadAudio: (id: string, file: File) =>
    request<AudioResult>(`/api/projects/${encodeURIComponent(id)}/input/audio?filename=${encodeURIComponent(file.name)}`, {
      method: "POST",
      headers: { "Content-Type": "application/octet-stream" },
      body: file,
    }),
  answer: (id: string, questionId: string, kind: "choice" | "unknown" | "free_text", value?: string) =>
    request<{ accepted: boolean }>(`/api/projects/${encodeURIComponent(id)}/answers`, {
      method: "POST",
      body: JSON.stringify({ question_id: questionId, kind, value }),
    }),
  reviewRequirement: (id: string, reqId: string, verdict: "ok" | "fix" | "clear", note?: string) =>
    request<{ accepted: boolean }>(`/api/projects/${encodeURIComponent(id)}/requirements/${encodeURIComponent(reqId)}/review`, {
      method: "POST",
      body: JSON.stringify({ verdict, note: note ?? null }),
    }),
  confirmRemainingRequirements: (id: string) =>
    request<{ accepted: boolean; count: number }>(`/api/projects/${encodeURIComponent(id)}/requirements/confirm-rest`, { method: "POST" }),
  sendRequirementFixes: (id: string) =>
    request<{ accepted: boolean }>(`/api/projects/${encodeURIComponent(id)}/requirements/fixes`, { method: "POST" }),
  submitAnswers: (id: string, defaults: Record<string, string> = {}) =>
    request<{ accepted: boolean }>(`/api/projects/${encodeURIComponent(id)}/answers/submit`, {
      method: "POST",
      body: JSON.stringify({ defaults }),
    }),
  confirm: (id: string, cp: string, approved: boolean, reason?: string, waivers?: Record<string, string>) =>
    request<{ accepted: boolean }>(`/api/projects/${encodeURIComponent(id)}/confirmations`, {
      method: "POST",
      body: JSON.stringify({ cp, approved, reason, waivers: waivers ?? {} }),
    }),
  githubStatus: () => request<GitHubStatus>("/api/github/status"),
  githubConnect: () => request<GitHubStatus>("/api/github/connect", { method: "POST" }),
  githubPoll: () => request<GitHubStatus>("/api/github/poll", { method: "POST" }),
  githubDisconnect: () => request<GitHubStatus>("/api/github/disconnect", { method: "POST" }),
  githubPush: (id: string, repo: string, isPrivate: boolean) =>
    request<GitHubPush>(`/api/github/projects/${encodeURIComponent(id)}/push`, {
      method: "POST",
      body: JSON.stringify({ repo, private: isPrivate }),
    }),
  useExisting: (id: string, alternativeId: string) =>
    request<{ accepted: boolean }>(`/api/projects/${encodeURIComponent(id)}/use-existing`, {
      method: "POST",
      body: JSON.stringify({ alternative_id: alternativeId }),
    }),
  buildGap: (id: string, alternativeId: string) =>
    request<{ accepted: boolean }>(
      `/api/projects/${encodeURIComponent(id)}/alternatives/${encodeURIComponent(alternativeId)}/gap`,
      { method: "POST" },
    ),
  retry: (id: string) =>
    request<{ accepted: boolean }>(`/api/projects/${encodeURIComponent(id)}/retry`, { method: "POST" }),
  narrowScope: (id: string, keep: string[], keepAll = false) =>
    request<{ accepted: boolean }>(`/api/projects/${encodeURIComponent(id)}/scope`, {
      method: "POST",
      body: JSON.stringify({ keep, keep_all: keepAll }),
    }),
  continueLimit: (id: string) =>
    request<{ accepted: boolean }>(`/api/projects/${encodeURIComponent(id)}/limits/continue`, { method: "POST" }),
  requestChange: (id: string, utterance: string, complaintRef?: string) =>
    request<{ id: string }>(`/api/projects/${encodeURIComponent(id)}/changes`, {
      method: "POST",
      body: JSON.stringify({ utterance, complaint_ref: complaintRef ?? null }),
    }),
  decideChange: (id: string, changeId: string, approved: boolean, reason?: string) =>
    request<{ accepted: boolean }>(
      `/api/projects/${encodeURIComponent(id)}/changes/${encodeURIComponent(changeId)}/decision`,
      { method: "POST", body: JSON.stringify({ approved, reason }) },
    ),
  complain: (id: string, text: string) =>
    request<{ id: string }>(`/api/projects/${encodeURIComponent(id)}/complaints`, {
      method: "POST",
      body: JSON.stringify({ text }),
    }),
  demoMeta: () => request<DemoMeta>("/api/demo"),
  demoState: (step: number) => request<DemoState>(`/api/demo/state?step=${step}`),
  documents: (id: string) =>
    request<{ documents: Record<DocId, DocView> }>(`/api/projects/${encodeURIComponent(id)}/documents`).then(
      (r) => r.documents,
    ),
};

export const urls = {
  preview: (id: string) => `/api/projects/${encodeURIComponent(id)}/prototype/preview`,
  download: (id: string) => `/api/projects/${encodeURIComponent(id)}/download`,
  demoPreview: (step: number) => `/api/demo/prototype/preview?step=${step}`,
  flow: (id: string) => `/api/projects/${encodeURIComponent(id)}/flow/preview`,
  demoFlow: (step: number) => `/api/demo/flow/preview?step=${step}`,
  lanes: (id: string) => `/api/projects/${encodeURIComponent(id)}/flow/lanes`,
  demoLanes: (step: number) => `/api/demo/flow/lanes?step=${step}`,
  demoDownload: () => "/api/demo/download",
  doc: (id: string, doc: DocId, kind: "pdf" | "docx" | "md") =>
    `/api/projects/${encodeURIComponent(id)}/documents/${doc}.${kind}`,
  demoDoc: (step: number, doc: DocId, kind: "pdf" | "docx" | "md") => `/api/demo/documents/${doc}.${kind}?step=${step}`,
};
