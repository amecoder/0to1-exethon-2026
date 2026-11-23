import { Building2, ChevronDown, LoaderCircle, Plus, Save } from "lucide-react";
import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { api, type CompanyDetail, type CompanySummary } from "./api";
import { noteCount } from "./lib/company";
import { countSystems } from "./thread/RequestComposer";

const FIELD =
  "mt-1.5 block w-full resize-y rounded-xl border border-border bg-white/[0.03] px-3 py-2.5 text-sm leading-relaxed text-foreground outline-none placeholder:text-faint focus-visible:ring-[3px] focus-visible:ring-primary-ring";
const NAME_MAX = 60;
const TEXT_MAX = 6000;

// 회사 작업 공간 on the start screen: choose a company (projects below are that company's), add one,
// and edit what every new project of the company starts from. No login — anyone on this server can switch.
export default function CompanyPanel({ companies, selected, onSelect, onCreated }: {
  companies: CompanySummary[];
  selected: string | null;
  onSelect: (id: string) => void;
  onCreated: (c: CompanySummary) => void;
}) {
  const [adding, setAdding] = useState(false);
  const [name, setName] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [open, setOpen] = useState(false);

  const create = async () => {
    if (!name.trim()) return;
    setError(null);
    try {
      const made = await api.createCompany(name.trim());
      onCreated({ id: made.id, name: made.name, created_at: made.created_at, projects: 0 });
      setName("");
      setAdding(false);
      setOpen(true);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  };

  return (
    <section aria-label="회사 작업 공간" className="glass mt-8 animate-rise rounded-3xl px-5 py-4 [animation-delay:40ms]">
      <div className="flex flex-wrap items-center gap-2">
        <label htmlFor="company" className="inline-flex items-center gap-1.5 text-sm font-semibold text-foreground">
          <Building2 className="size-4 text-cyan" aria-hidden="true" /> 회사
        </label>
        <select
          id="company"
          value={selected ?? ""}
          onChange={(e) => onSelect(e.target.value)}
          className="min-w-0 flex-1 cursor-pointer rounded-lg border border-border bg-[#0b1238] px-3 py-1.5 text-sm text-foreground outline-none focus-visible:ring-[3px] focus-visible:ring-primary-ring"
        >
          {companies.map((c) => (
            <option key={c.id} value={c.id}>
              {c.name} · 프로젝트 {c.projects}개
            </option>
          ))}
        </select>
        <Button variant="ghost" size="sm" onClick={() => setAdding((v) => !v)} aria-expanded={adding}>
          <Plus aria-hidden="true" /> 새 회사
        </Button>
        <Button variant="outline" size="sm" onClick={() => setOpen((v) => !v)} aria-expanded={open} disabled={!selected}>
          회사 자료 <ChevronDown className={cn("transition-transform", open && "rotate-180")} aria-hidden="true" />
        </Button>
      </div>
      {adding && (
        <form
          className="mt-3 flex gap-2"
          onSubmit={(e) => {
            e.preventDefault();
            void create();
          }}
        >
          <input
            value={name}
            maxLength={NAME_MAX}
            onChange={(e) => setName(e.target.value)}
            placeholder="회사 이름 (예: 동네 꽃집 체인)"
            aria-label="새 회사 이름"
            autoFocus
            className="min-w-0 flex-1 rounded-lg border border-border bg-white/[0.03] px-3 py-1.5 text-sm text-foreground outline-none placeholder:text-faint focus-visible:ring-[3px] focus-visible:ring-primary-ring"
          />
          <Button type="submit" size="sm" disabled={!name.trim()}>
            만들기
          </Button>
        </form>
      )}
      <p className="mt-2 text-xs break-keep text-muted-foreground">
        프로젝트와 회사 자료는 회사별로 따로 모여요. 새 프로젝트는 이 회사가 이미 정한 것을 알고 시작해서 같은 걸 다시 묻지 않아요.
      </p>
      {error && (
        <p className="mt-2 text-sm text-destructive" role="alert">
          {error}
        </p>
      )}
      {open && selected && <CompanyMaterial key={selected} companyId={selected} />}
    </section>
  );
}

function CompanyMaterial({ companyId }: { companyId: string }) {
  const [company, setCompany] = useState<CompanyDetail | null>(null);
  const [systems, setSystems] = useState("");
  const [notes, setNotes] = useState("");
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState<{ text: string; error: boolean } | null>(null);

  useEffect(() => {
    let live = true;
    api
      .company(companyId)
      .then((c) => {
        if (!live) return;
        setCompany(c);
        setSystems(c.systems);
        setNotes(c.notes);
      })
      .catch((e) => live && setMessage({ text: e instanceof Error ? e.message : String(e), error: true }));
    return () => {
      live = false;
    };
  }, [companyId]);

  const save = async () => {
    setSaving(true);
    setMessage(null);
    try {
      const saved = await api.saveCompany(companyId, systems, notes);
      setCompany((c) => (c ? { ...c, ...saved } : saved));
      setMessage({ text: "저장했어요. 이제부터 시작하는 프로젝트에 들어가요.", error: false });
    } catch (e) {
      setMessage({ text: e instanceof Error ? e.message : String(e), error: true });
    } finally {
      setSaving(false);
    }
  };

  if (!company) {
    return (
      <p className="mt-3 inline-flex items-center gap-2 text-sm text-muted-foreground">
        <LoaderCircle className="size-4 animate-spin" aria-hidden="true" /> 회사 자료를 불러오는 중…
      </p>
    );
  }
  const past = company.past_decisions ?? [];
  const services = company.services ?? [];
  const changed = systems !== company.systems || notes !== company.notes;
  return (
    <div className="mt-4 flex flex-col gap-4 border-t border-border pt-4">
      <div>
        <label htmlFor="company-notes" className="text-sm font-semibold text-foreground">
          회사 공통 자료 {noteCount(notes) > 0 && <span className="font-normal text-muted-foreground">· {noteCount(notes)}줄</span>}
        </label>
        <p className="mt-0.5 text-xs break-keep text-muted-foreground">
          용어, 사내 규칙, 이미 정한 것을 한 줄에 하나씩 적어 주세요. 질문 카드를 만들 때 팀이 먼저 여기서 답을 찾아요.
        </p>
        <textarea
          id="company-notes"
          rows={5}
          maxLength={TEXT_MAX}
          value={notes}
          onChange={(e) => setNotes(e.target.value)}
          placeholder={"예) 회원 등급은 일반·실버·골드 3단계다\n결제는 토스페이먼츠만 쓴다\n개인정보는 1년 지나면 지운다"}
          className={FIELD}
        />
      </div>
      <div>
        <label htmlFor="company-systems" className="text-sm font-semibold text-foreground">
          우리 시스템 목록 {countSystems(systems) > 0 && <span className="font-normal text-muted-foreground">· {countSystems(systems)}개</span>}
        </label>
        <p className="mt-0.5 text-xs break-keep text-muted-foreground">
          회사가 이미 쓰는 시스템을 한 줄에 하나씩 「이름: 하는 일」로 적어 주세요. 새 요청을 쓸 때 미리 채워져요.
        </p>
        <textarea
          id="company-systems"
          rows={3}
          maxLength={TEXT_MAX}
          value={systems}
          onChange={(e) => setSystems(e.target.value)}
          placeholder={"예) 주문관리 시스템: 주문 상태와 도착 예정일을 갖고 있어요"}
          className={FIELD}
        />
      </div>
      <div className="flex flex-wrap items-center gap-3">
        <Button size="sm" onClick={save} disabled={saving || !changed}>
          {saving ? <LoaderCircle className="animate-spin" aria-hidden="true" /> : <Save aria-hidden="true" />} 회사 자료 저장
        </Button>
        {message && (
          <span className={cn("text-sm", message.error ? "text-destructive" : "text-success")} role={message.error ? "alert" : "status"}>
            {message.text}
          </span>
        )}
      </div>
      <div>
        <h3 className="text-sm font-semibold text-foreground">이 회사가 0to1로 만든 서비스 · {services.length}개</h3>
        {services.length === 0 ? (
          <p className="mt-1 text-xs text-muted-foreground">이 회사 프로젝트가 마지막 체크포인트(CP4)까지 끝나면 여기에 서비스로 올라가요. 새 요청은 이 서비스에 기능을 더할지, 연결할지, 새로 만들지 먼저 따져 봐요.</p>
        ) : (
          <ul className="mt-1.5 flex flex-col gap-1 text-sm">
            {services.map((s) => (
              <li key={s.project_id} className="rounded-xl bg-white/[0.03] px-3 py-2">
                <span className="font-medium text-foreground">{s.name}</span>
                <span className="text-muted-foreground"> · 기능 {s.features.length}개</span>
                <span className="block text-xs break-keep text-faint">{s.features.map((f) => f.title).join(", ")}</span>
              </li>
            ))}
          </ul>
        )}
      </div>
      <div>
        <h3 className="text-sm font-semibold text-foreground">지난 프로젝트에서 정한 것 · {past.length}건</h3>
        {past.length === 0 ? (
          <p className="mt-1 text-xs text-muted-foreground">이 회사 프로젝트에서 발주사가 질문 카드에 답하면 여기에 쌓이고, 다음 프로젝트가 그 답을 알고 시작해요.</p>
        ) : (
          <ul className="mt-1.5 flex max-h-56 flex-col gap-1 overflow-y-auto pr-1 text-sm">
            {past.map((d) => (
              <li key={`${d.project_id}:${d.decision_id}`} className="rounded-xl bg-white/[0.03] px-3 py-2">
                <span className="text-muted-foreground">{d.topic}</span>
                <span className="block font-medium text-foreground">→ {d.chosen}</span>
                <span className="text-xs text-faint">{d.project}</span>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}
