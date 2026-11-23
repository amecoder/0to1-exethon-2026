import { ArrowRight, FolderOpen, Play, Sparkles, type LucideIcon } from "lucide-react";
import { useEffect, useState } from "react";
import { cn } from "@/lib/utils";
import { api, type CompanySummary, type Mode, type Project, type ProjectSummary } from "./api";
import CompanyPanel from "./CompanyPanel";
import { chooseCompany, listFilter, rememberCompany, rememberedCompany } from "./lib/company";
import { Codes } from "./ui/refs";
import { CONFIRM_RULE, PROBLEM_HEADLINE, PROBLEM_LINE, PRODUCT_TAGLINE } from "./brand";
import { STAGE_TITLE, STATUS_KO } from "./lib/labels";
import { ProductMark } from "./thread/TopBar";
import GlossaryButton from "./ui/GlossaryDialog";

type KeyState = "loading" | "present" | "absent" | "error";

const KEY_LABEL: Record<KeyState, string> = {
  loading: "Liner API 키를 확인하고 있어요",
  present: "Liner API 키가 준비되어 있어요",
  absent: "Liner API 키가 없어요 — 실제 모드는 .env 에 LINER_API_KEY 를 넣어야 쓸 수 있어요",
  error: "서버에 연결할 수 없어요",
};

const KEY_DOT: Record<KeyState, string> = {
  loading: "bg-faint",
  present: "bg-success",
  absent: "bg-warning",
  error: "bg-destructive",
};

const FLOW = ["요구 붙여 넣기", "질문에 답하기", "문서 확인", "프로토타입 받기", "변경·불만을 기록과 대조"];

export default function StartScreen({ onStart, onDemo }: { onStart: (p: Project) => void; onDemo: () => void }) {
  const [keyState, setKeyState] = useState<KeyState>("loading");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [recent, setRecent] = useState<ProjectSummary[]>([]);
  const [total, setTotal] = useState(0);
  const [companies, setCompanies] = useState<CompanySummary[]>([]);
  const [company, setCompany] = useState<string | null>(null);
  const [companyOn, setCompanyOn] = useState(false); // the workspace shows only with EXETHON_COMPANY=on

  useEffect(() => {
    api
      .keyStatus()
      .then((s) => setKeyState(s.present ? "present" : "absent"))
      .catch(() => setKeyState("error"));
    api
      .features()
      .then((f) => setCompanyOn(f.company))
      .catch(() => setCompanyOn(false));
    api
      .companies()
      .then((list) => {
        setCompanies(list);
        setCompany(chooseCompany(list, rememberedCompany()));
      })
      .catch(() => setCompanies([]));
  }, []);

  // The list below is the chosen company's projects (every project with the workspace switched off).
  const filter = listFilter(companyOn, company);
  useEffect(() => {
    if (filter === null) return;
    let live = true;
    api
      .projects(20, filter)
      .then((r) => {
        if (!live) return;
        setRecent(r.projects);
        setTotal(r.total);
      })
      .catch(() => live && setRecent([]));
    return () => {
      live = false;
    };
  }, [filter]);

  const selectCompany = (id: string) => {
    setCompany(id);
    rememberCompany(id);
  };

  const reopen = async (id: string) => {
    setBusy(true);
    setError(null);
    try {
      onStart(await api.project(id));
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  const start = async (mode: Mode) => {
    setBusy(true);
    setError(null);
    try {
      onStart(await api.createProject("새 프로젝트", mode, companyOn ? (company ?? undefined) : undefined));
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="ds cosmos flex min-h-screen flex-col font-sans text-foreground">
      <header className="flex h-16 items-center px-6">
        <ProductMark />
        <GlossaryButton className="ml-auto" />
      </header>
      <main className="mx-auto flex w-full max-w-[46rem] flex-1 flex-col justify-center px-6 pb-24">
        <div className="animate-rise">
          <p className="inline-flex items-center gap-1.5 rounded-full border border-primary-ring/40 bg-primary-soft px-3 py-1 text-xs font-semibold text-primary-text">
            <Sparkles className="size-3.5" aria-hidden="true" /> 에이전트 7명 · Liner 검색으로 근거 확인
          </p>
          <h1 className="mt-5 text-hero font-bold tracking-[-0.03em] text-balance break-keep">{PROBLEM_HEADLINE}</h1>
          <p className="mt-4 text-lg break-keep text-muted-foreground">{PROBLEM_LINE}</p>
          <p className="mt-2 text-sm break-keep text-faint">
            {PRODUCT_TAGLINE} · 확인은 <Codes text={CONFIRM_RULE} />
          </p>
          <ol className="mt-5 flex flex-wrap items-center gap-x-2 gap-y-1 text-sm text-muted-foreground" aria-label="흐름">
            {FLOW.map((step, i) => (
              <li key={step} className="inline-flex items-center gap-2">
                {i > 0 && <ArrowRight className="size-3.5 text-white/25" aria-hidden="true" />}
                {i === FLOW.length - 1 ? (
                  <span className="rounded-full border border-cyan/40 bg-cyan-soft px-2.5 py-0.5 font-semibold text-cyan">{step}</span>
                ) : (
                  step
                )}
              </li>
            ))}
          </ol>
        </div>

        {companyOn && companies.length > 0 && (
          <CompanyPanel
            companies={companies}
            selected={company}
            onSelect={selectCompany}
            onCreated={(c) => {
              setCompanies((list) => [...list, c]);
              selectCompany(c.id);
            }}
          />
        )}

        <div className="mt-4 flex animate-rise flex-col gap-3 [animation-delay:80ms]">
          <ModeButton
            icon={Sparkles}
            title="실제 모드"
            body="요구를 직접 붙여 넣고 팀과 함께 진행해요 · Liner API 키 필요"
            primary
            disabled={busy}
            onClick={() => start("real")}
          />
          <ModeButton icon={Play} title="시연 모드" body="실제 실행 기록을 장면별로 다시 봐요 · 키 없이 볼 수 있어요" disabled={busy} onClick={onDemo} />
        </div>

        {recent.length > 0 && filter !== null && (
          <RecentProjects key={filter ?? "all"} items={recent} total={total} companyId={filter} disabled={busy} onOpen={reopen} />
        )}

        <p className="mt-6 inline-flex items-center gap-2 text-sm text-muted-foreground" role="status">
          <span className={cn("size-2 rounded-full", KEY_DOT[keyState])} aria-hidden="true" />
          {KEY_LABEL[keyState]}
        </p>
        {error && (
          <p className="mt-2 text-sm text-destructive" role="alert">
            {error}
          </p>
        )}
      </main>
    </div>
  );
}

function stateText(p: ProjectSummary): string {
  if (p.completed) return "완료";
  const stage = p.stage ? STAGE_TITLE[p.stage] ?? p.stage : "요구 입력";
  return p.status ? `${stage} · ${STATUS_KO[p.status] ?? p.status}` : stage;
}

// Real-mode projects saved in SQLite, newest first — reopen one to continue or to download again.
// Five show at first; 「전체 N개 보기」 loads every project (none is ever deleted) with a name filter.
const FIRST_SHOWN = 5;
const ALL = 1000;
const FILTER_FROM = 8;

function RecentProjects({ items, total, companyId, disabled, onOpen }: {
  items: ProjectSummary[];
  total: number;
  companyId?: string;
  disabled: boolean;
  onOpen: (id: string) => void;
}) {
  const [all, setAll] = useState<ProjectSummary[] | null>(null);
  const [query, setQuery] = useState("");
  const [loading, setLoading] = useState(false);
  const open = all !== null;
  const list = open ? all.filter((p) => p.name.toLowerCase().includes(query.trim().toLowerCase())) : items.slice(0, FIRST_SHOWN);
  const showAll = async () => {
    setLoading(true);
    try {
      setAll((await api.projects(ALL, companyId)).projects);
    } catch {
      setAll(items);
    } finally {
      setLoading(false);
    }
  };
  return (
    <section className="mt-8 animate-rise [animation-delay:120ms]" aria-labelledby="recent-title">
      <h2 id="recent-title" className="flex items-center gap-1.5 text-sm font-semibold text-muted-foreground">
        <FolderOpen className="size-4" aria-hidden="true" /> {open ? `전체 프로젝트 ${all.length}개` : "최근 프로젝트 다시 열기"}
      </h2>
      {open && all.length > FILTER_FROM && (
        <input
          type="search"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="프로젝트 이름으로 찾기"
          aria-label="프로젝트 이름으로 찾기"
          className="mt-2 w-full rounded-xl border border-border bg-white/[0.03] px-3.5 py-2 text-sm text-foreground outline-none placeholder:text-faint focus-visible:ring-[3px] focus-visible:ring-primary-ring"
        />
      )}
      <ul className={cn("mt-2 flex flex-col gap-1.5", open && "max-h-[26rem] overflow-y-auto pr-1")}>
        {list.map((p) => (
          <li key={p.id}>
            <button
              type="button"
              disabled={disabled}
              onClick={() => onOpen(p.id)}
              className="flex w-full cursor-pointer items-center gap-3 rounded-2xl border border-border bg-white/[0.025] px-4 py-2.5 text-left text-sm transition-colors hover:bg-white/[0.06] focus-visible:ring-[3px] focus-visible:ring-primary-ring focus-visible:outline-none disabled:cursor-wait"
            >
              <span className="min-w-0 flex-1 truncate font-medium text-foreground">{p.name}</span>
              <span className="shrink-0 text-muted-foreground">{stateText(p)}</span>
              <time className="shrink-0 tabular-nums text-faint" dateTime={p.created_at}>
                {new Date(p.created_at).toLocaleDateString("ko-KR")}
              </time>
            </button>
          </li>
        ))}
        {open && list.length === 0 && <li className="px-1 py-2 text-sm text-faint">이름이 맞는 프로젝트가 없어요.</li>}
      </ul>
      {total > FIRST_SHOWN && (
        <button
          type="button"
          onClick={() => (open ? (setAll(null), setQuery("")) : showAll())}
          disabled={loading}
          className="mt-2 cursor-pointer text-sm font-semibold text-primary-text hover:underline disabled:cursor-wait"
        >
          {open ? "접기" : loading ? "불러오는 중…" : `전체 ${total}개 보기`}
        </button>
      )}
    </section>
  );
}

function ModeButton({ icon: Icon, title, body, primary, disabled, onClick }: {
  icon: LucideIcon;
  title: string;
  body: string;
  primary?: boolean;
  disabled: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      disabled={disabled}
      onClick={onClick}
      className={cn(
        "group flex w-full cursor-pointer items-center gap-4 rounded-3xl border px-6 py-5 text-left transition-[background-color,border-color,transform] duration-150 active:scale-[0.99] disabled:cursor-wait disabled:opacity-60",
        "focus-visible:ring-[3px] focus-visible:ring-primary-ring focus-visible:outline-none",
        primary ? "border-transparent bg-[linear-gradient(135deg,#6553f5_0%,#4a5ff0_100%)] text-primary-foreground shadow-glow hover:brightness-110" : "glass hover:bg-white/[0.07]",
      )}
    >
      <span
        className={cn("grid size-11 shrink-0 place-items-center rounded-2xl", primary ? "bg-white/15" : "bg-secondary text-cyan")}
        aria-hidden="true"
      >
        <Icon className="size-5" />
      </span>
      <span className="flex min-w-0 flex-1 flex-col">
        <span className="text-lg font-semibold">{title}</span>
        <span className={cn("text-sm break-keep", primary ? "text-white/85" : "text-muted-foreground")}>{body}</span>
      </span>
      <ArrowRight
        className={cn("size-5 shrink-0 transition-transform group-hover:translate-x-0.5", primary ? "text-white" : "text-faint")}
        aria-hidden="true"
      />
    </button>
  );
}
