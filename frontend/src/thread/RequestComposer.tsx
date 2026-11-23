import { ArrowUp, Boxes, CircleAlert, FileText, FileUp, Image, LoaderCircle, Mic, Paperclip, Plus, X } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { api, type AttachmentResult, type AudioResult, type TriageAnswer, type TriageVerdict } from "../api";
import IntakeTriage from "./IntakeTriage";
import { addAnswers, type Drafts, keepsVerdict, withAnswersChunk } from "./intake";
import { systemsKey, systemsToPrefill } from "../lib/company";

const AUDIO_ACCEPT = ".wav,.mp3,.flac,.m4a,.mp4,.ogg,.oga,.opus,.webm,audio/*";
// Same kinds as the server (app/attachments.py): images for the router, PDF for the file model, text read as is.
const ATTACH_ACCEPT = ".png,.jpg,.jpeg,.gif,.webp,.pdf,.txt,.md,.csv,image/png,image/jpeg,image/gif,image/webp";
const SYSTEMS_ACCEPT = ".csv,.tsv,.txt,.md,.pdf,.png,.jpg,.jpeg,.gif,.webp";
const KIND_NOTE = { image: "이미지에서 옮겨 적음", document: "문서에서 옮겨 적음" } as const;
// The last 「우리 시스템 목록」 is remembered in this browser only, per company (a convenience for the next project).
const SYSTEMS_MAX = 6000;

function rememberedSystems(companyId: string | undefined): string {
  try {
    return localStorage.getItem(systemsKey(companyId)) ?? "";
  } catch {
    return "";
  }
}

// Same rule as the server (app/systems.py): one system per non-empty line, '#' lines are headings.
export function countSystems(text: string): number {
  return text.split("\n").filter((l) => l.trim() && !l.trim().startsWith("#")).length;
}

// Lines read from a file go under what is already in the 「우리 시스템 목록」 box (still editable).
export function appendLines(text: string, lines: string[]): string {
  const kept = text.replace(/\s+$/, "");
  return [kept, ...lines].filter((l) => l !== "").join("\n");
}

// Step 1 in the new look: paste the request memo (one or more chunks) and send it to the team.
export default function RequestComposer({ projectId, companyId, onSent }: {
  projectId: string;
  companyId?: string;
  onSent: () => void;
}) {
  const [chunks, setChunks] = useState<string[]>([""]);
  const [busy, setBusy] = useState(false);
  const [blocked, setBlocked] = useState<{ message: string; refused: boolean } | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [audio, setAudio] = useState<AudioResult | null>(null);
  const [listening, setListening] = useState(false);
  const fileInput = useRef<HTMLInputElement>(null);
  const [attachments, setAttachments] = useState<AttachmentResult[]>([]);
  const [reading, setReading] = useState(false);
  const attachInput = useRef<HTMLInputElement>(null);
  const [loadingSystems, setLoadingSystems] = useState(false);
  const systemsInput = useRef<HTMLInputElement>(null);
  const [systems, setSystems] = useState(() => rememberedSystems(companyId));
  const [showSystems, setShowSystems] = useState(() => rememberedSystems(companyId).trim() !== "");
  const typedSystems = useRef("");
  // Intake triage: nothing goes to the team until the verdict is ok (app/intake_triage.py).
  const [verdict, setVerdict] = useState<TriageVerdict | null>(null);
  const [answers, setAnswers] = useState<TriageAnswer[]>([]);
  const [drafts, setDrafts] = useState<Drafts>({});
  const systemCount = countSystems(systems);

  // The company's own 「우리 시스템 목록」 comes first (회사 자료); the browser's last list is the fallback.
  useEffect(() => {
    if (!companyId) return;
    let live = true;
    api
      .company(companyId)
      .then((c) => {
        if (!live) return;
        const next = systemsToPrefill(c.systems, rememberedSystems(companyId), typedSystems.current);
        setSystems(next);
        setShowSystems(next.trim() !== "");
      })
      .catch(() => {
        // keep the remembered list: the request can still be written and sent
      });
    return () => {
      live = false;
    };
  }, [companyId]);
  const ready = chunks.some((c) => c.trim()) || audio !== null || attachments.length > 0;

  // Meeting recording → Liner speech-to-text. The transcript waits on the server until 「팀에게 보내기」.
  const upload = async (file: File | undefined) => {
    if (!file) return;
    setListening(true);
    setError(null);
    try {
      setAudio(await api.uploadAudio(projectId, file));
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setListening(false);
      if (fileInput.current) fileInput.current.value = "";
    }
  };

  // Images and documents → their text (Liner reads images and PDFs; text files cost no call). One at a time;
  // the same file name again replaces the earlier one. The text waits on the server until 「팀에게 보내기」.
  const attach = async (files: FileList | null) => {
    if (!files || files.length === 0) return;
    setReading(true);
    setError(null);
    try {
      for (const file of Array.from(files)) {
        const read = await api.uploadAttachment(projectId, file);
        setAttachments((prev) => [...prev.filter((a) => a.filename !== read.filename), read]);
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setReading(false);
      if (attachInput.current) attachInput.current.value = "";
    }
  };

  const detach = async (filename: string) => {
    setError(null);
    try {
      await api.removeAttachment(projectId, filename);
      setAttachments((prev) => prev.filter((a) => a.filename !== filename));
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  };

  // 「우리 시스템 목록」 from a file: the found systems are added to the box, nothing is sent yet.
  const loadSystems = async (file: File | undefined) => {
    if (!file) return;
    setLoadingSystems(true);
    setError(null);
    try {
      const found = await api.systemsFromFile(projectId, file);
      setSystems((prev) => appendLines(prev, found.lines).slice(0, SYSTEMS_MAX));
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoadingSystems(false);
      if (systemsInput.current) systemsInput.current.value = "";
    }
  };

  // Judges without their own memo: load the sample memo (request_memo.md, served by /api/sample-memo).
  const fillExample = async () => {
    setError(null);
    try {
      const memo = await api.exampleMemo();
      setChunks([memo.text]);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  };

  // 「처음부터 다시 쓰기」: the Q&A is cleared, the memo stays as it is (always editable).
  const restart = () => {
    setVerdict(null);
    setAnswers([]);
    setDrafts({});
  };

  // 「팀에게 보내기」 and 「답하고 다시 확인하기」: one triage round, then /input only when it is ok.
  const submit = async (mask: boolean, given: TriageAnswer[] = answers) => {
    setBusy(true);
    setError(null);
    if (!keepsVerdict(verdict)) setVerdict(null);
    try {
      const texts = chunks.filter((c) => c.trim());
      const triage = await api.triageInput(projectId, texts, given, mask, audio !== null, attachments.length > 0);
      if (triage.blocked) {
        const refused = triage.guard === "G9";
        // G3: keep this round's answers so 「가린 값으로 보내기」 re-checks the same words, masked.
        // G9: the product itself is refused; earlier questions and answers belong to it.
        setAnswers(refused ? [] : given);
        if (refused) setVerdict(null);
        setDrafts({});
        setBlocked({ message: triage.message, refused });
        return;
      }
      setBlocked(null);
      setDrafts({});
      if (triage.case !== "ok") {
        setVerdict(triage);
        // A request the team cannot take or cannot read needs new words; earlier answers belong to the old one.
        setAnswers(triage.case === "insufficient" ? given : []);
        return;
      }
      setVerdict(null);
      setAnswers(given);
      const listed = showSystems ? systems.trim() : "";
      const result = await api.submitInput(projectId, withAnswersChunk(texts, given), mask, audio !== null, listed, attachments.length > 0);
      try {
        localStorage.setItem(systemsKey(companyId), systems);
      } catch {
        // storage blocked: the list is simply not prefilled next time
      }
      setBlocked(result.blocked ? { message: result.message ?? "민감 정보가 있어요", refused: result.guard === "G9" } : null);
      onSent();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="flex animate-rise flex-col gap-6 pt-6">
      <div className="flex flex-col gap-2">
        <h2 className="text-title font-bold tracking-[-0.02em] text-foreground">어떤 걸 만들고 싶으세요?</h2>
        <p className="text-base text-muted-foreground">
          받은 메모를 그대로 붙여 넣거나 회의 녹음(25MB 이하)·화면 캡처·문서 파일을 올려 주세요. 메신저·메일 그대로 괜찮아요. 팀이 필요한 것만 다시 여쭤볼게요.
        </p>
      </div>
      <Card className="flex flex-col gap-3 rounded-3xl p-3 focus-within:border-primary-ring">
        {chunks.map((chunk, i) => (
          <div key={i} className="relative">
            <label htmlFor={`memo-${i}`} className="sr-only">
              요구 메모 {i + 1}
            </label>
            <textarea
              id={`memo-${i}`}
              rows={chunks.length > 1 ? 5 : 9}
              value={chunk}
              placeholder={i === 0 ? "예) 저희 꽃집 정기구독 앱을 만들고 싶어요. 고객이 일주일에 한 번 꽃을 받는 거예요…" : `메모 ${i + 1}`}
              onChange={(e) => {
                setChunks(chunks.map((c, j) => (j === i ? e.target.value : c)));
                if (!keepsVerdict(verdict)) setVerdict(null);
              }}
              className="m-0 block w-full resize-none rounded-2xl border-0 bg-white/[0.03] px-4 py-3.5 text-base leading-relaxed text-foreground outline-none placeholder:text-faint focus-visible:outline-none"
            />
            {chunks.length > 1 && (
              <Button
                variant="ghost"
                size="icon"
                className="absolute top-2 right-2 size-7"
                aria-label={`메모 ${i + 1} 지우기`}
                onClick={() => setChunks(chunks.filter((_, j) => j !== i))}
              >
                <X />
              </Button>
            )}
          </div>
        ))}
        {audio && (
          <section aria-label="받아 적은 회의 녹음" className="relative rounded-2xl border border-border bg-white/[0.025] px-4 py-3.5">
            <p className="flex items-center gap-1.5 text-sm font-semibold text-foreground">
              <Mic className="size-4 text-cyan" aria-hidden="true" /> 음성에서 받아 적음 · {audio.filename}
            </p>
            <p className="mt-1.5 max-h-32 overflow-y-auto text-sm leading-relaxed break-keep whitespace-pre-wrap text-soft">{audio.text}</p>
            <p className="mt-1.5 text-xs text-muted-foreground">받아 적은 글은 고치지 않고 원문으로 보관해요. 다르면 메모 칸에 바로잡아 적어 주세요.</p>
            <Button
              variant="ghost"
              size="icon"
              className="absolute top-2 right-2 size-7"
              aria-label="받아 적은 녹음 빼기"
              onClick={() => setAudio(null)}
            >
              <X />
            </Button>
          </section>
        )}
        {attachments.map((a) => (
          <section key={a.filename} aria-label={`첨부 ${a.filename}`} className="relative rounded-2xl border border-border bg-white/[0.025] px-4 py-3.5">
            <p className="flex items-center gap-1.5 pr-8 text-sm font-semibold break-all text-foreground">
              {a.kind === "image" ? <Image className="size-4 shrink-0 text-cyan" aria-hidden="true" /> : <FileText className="size-4 shrink-0 text-cyan" aria-hidden="true" />}
              {KIND_NOTE[a.kind]} · {a.filename}
            </p>
            <p className="mt-1.5 max-h-32 overflow-y-auto text-sm leading-relaxed break-keep whitespace-pre-wrap text-soft">{a.text}</p>
            <Button
              variant="ghost"
              size="icon"
              className="absolute top-2 right-2 size-7"
              aria-label={`첨부 ${a.filename} 빼기`}
              onClick={() => detach(a.filename)}
            >
              <X />
            </Button>
          </section>
        ))}
        {attachments.length > 0 && (
          <p className="px-1 text-xs text-muted-foreground">옮겨 적은 글은 고치지 않고 원문으로 보관해요. 다르면 메모 칸에 바로잡아 적어 주세요.</p>
        )}
        {showSystems && (
          <section aria-label="우리 시스템 목록" className="relative rounded-2xl border border-border bg-white/[0.025] px-4 py-3.5">
            <label htmlFor="our-systems" className="flex items-center gap-1.5 text-sm font-semibold text-foreground">
              <Boxes className="size-4 text-cyan" aria-hidden="true" /> 우리 시스템 목록 (선택)
              {systemCount > 0 && <span className="font-normal text-muted-foreground">· {systemCount}개</span>}
            </label>
            <p className="mt-1 text-xs break-keep text-muted-foreground">
              회사가 이미 쓰는 시스템을 한 줄에 하나씩 「이름: 하는 일」로 적어 주세요. 팀이 새로 만들지, 있는 시스템에 기능을 더할지, 연계할지 먼저 따져 봐요.
            </p>
            <textarea
              id="our-systems"
              rows={4}
              maxLength={SYSTEMS_MAX}
              value={systems}
              placeholder={"예) 주문관리 시스템: 주문 상태와 도착 예정일을 갖고 있어요\n알림톡 발송: 고객에게 카카오 알림톡을 보낼 수 있어요"}
              onChange={(e) => {
                typedSystems.current = e.target.value;
                setSystems(e.target.value);
              }}
              className="mt-2 block w-full resize-y rounded-xl border-0 bg-white/[0.03] px-3 py-2.5 text-sm leading-relaxed text-foreground outline-none placeholder:text-faint"
            />
            <input
              ref={systemsInput}
              type="file"
              accept={SYSTEMS_ACCEPT}
              aria-label="시스템 목록 파일"
              tabIndex={-1}
              className="sr-only"
              onChange={(e) => loadSystems(e.target.files?.[0])}
            />
            <Button variant="ghost" size="sm" className="mt-1.5" disabled={loadingSystems || busy} onClick={() => systemsInput.current?.click()}>
              {loadingSystems ? <LoaderCircle className="animate-spin" /> : <FileUp />}
              {loadingSystems ? "불러오는 중…" : "파일에서 불러오기"}
            </Button>
            <Button
              variant="ghost"
              size="icon"
              className="absolute top-2 right-2 size-7"
              aria-label="우리 시스템 목록 빼기"
              onClick={() => setShowSystems(false)}
            >
              <X />
            </Button>
          </section>
        )}
        <div className="flex items-center justify-between gap-2 px-1">
          <div className="flex flex-wrap items-center gap-1">
            <Button variant="ghost" size="sm" disabled={busy} onClick={fillExample}>
              <FileText /> 예제 메모 채우기
            </Button>
            <Button variant="ghost" size="sm" onClick={() => setChunks([...chunks, ""])}>
              <Plus /> 메모 덩어리 추가
            </Button>
            {!showSystems && (
              <Button variant="ghost" size="sm" onClick={() => setShowSystems(true)}>
                <Boxes /> 우리 시스템 목록
              </Button>
            )}
            <input
              ref={fileInput}
              id="meeting-audio"
              type="file"
              accept={AUDIO_ACCEPT}
              aria-label="회의 녹음 파일"
              tabIndex={-1}
              className="sr-only"
              onChange={(e) => upload(e.target.files?.[0])}
            />
            <Button variant="ghost" size="sm" disabled={listening || busy} onClick={() => fileInput.current?.click()}>
              {listening ? <LoaderCircle className="animate-spin" /> : <Mic />}
              {listening ? "받아 적는 중…" : audio ? "다른 녹음 올리기" : "회의 녹음 올리기"}
            </Button>
            <input
              ref={attachInput}
              id="request-attachments"
              type="file"
              multiple
              accept={ATTACH_ACCEPT}
              aria-label="첨부 파일"
              tabIndex={-1}
              className="sr-only"
              onChange={(e) => attach(e.target.files)}
            />
            <Button variant="ghost" size="sm" disabled={reading || busy} onClick={() => attachInput.current?.click()}>
              {reading ? <LoaderCircle className="animate-spin" /> : <Paperclip />}
              {reading ? "읽는 중…" : "파일 첨부"}
            </Button>
          </div>
          <Button disabled={busy || !ready} onClick={() => submit(false)}>
            {busy && <LoaderCircle className="animate-spin" />}
            {busy ? "확인하는 중…" : "팀에게 보내기"} <ArrowUp />
          </Button>
        </div>
      </Card>
      {verdict && (
        <IntakeTriage
          verdict={verdict}
          answers={answers}
          drafts={drafts}
          busy={busy}
          onDraft={(slot, value) => setDrafts((prev) => ({ ...prev, [slot]: value }))}
          onRecheck={() => verdict && submit(false, addAnswers(answers, verdict.questions, drafts))}
          onRestart={restart}
        />
      )}
      {blocked && (
        <div className="flex items-start gap-3 rounded-2xl bg-warning-soft px-5 py-4" role="alert">
          <CircleAlert className="mt-0.5 size-5 shrink-0 text-warning" aria-hidden="true" />
          <div className="flex flex-col gap-3">
            <div>
              <p className="font-semibold text-foreground">
                {blocked.refused ? "이 요청은 만들 수 없어요" : "민감 정보가 있어서 아직 보내지 않았어요"}
              </p>
              <p className="text-sm text-soft">{blocked.message}</p>
            </div>
            {!blocked.refused && (
              <Button variant="outline" size="sm" className="w-fit" disabled={busy} onClick={() => submit(true)}>
                가린 값으로 보내기
              </Button>
            )}
          </div>
        </div>
      )}
      {error && (
        <p className="text-sm text-destructive" role="alert">
          {error}
        </p>
      )}
    </div>
  );
}
