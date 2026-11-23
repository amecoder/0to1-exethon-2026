import { Copy, ExternalLink, LoaderCircle, LogOut, Upload } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { api, type GitHubPush, type GitHubStatus } from "../api";

// GitHub 연동 inside the header popover: sign in with a device code, then push the same files as the zip.
// The repo name is remembered per project in this browser only (a convenience, not shared state).
const repoKey = (projectId: string) => `gh-repo:${projectId}`;

function remembered(projectId: string): string {
  try {
    return localStorage.getItem(repoKey(projectId)) || `planning-${projectId.slice(0, 6)}`;
  } catch {
    return `planning-${projectId.slice(0, 6)}`;
  }
}

export default function GitHubPanel({ projectId, final }: { projectId: string; final: boolean }) {
  const [status, setStatus] = useState<GitHubStatus | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [repo, setRepo] = useState(() => remembered(projectId));
  const [isPrivate, setIsPrivate] = useState(true);
  const [result, setResult] = useState<GitHubPush | null>(null);

  const run = useCallback(async (call: () => Promise<GitHubStatus>) => {
    setError(null);
    try {
      setStatus(await call());
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      api.githubStatus().then(setStatus, () => undefined);
    }
  }, []);

  useEffect(() => {
    run(api.githubStatus);
  }, [run]);

  // While a code waits for approval, ask the server once per interval (it never polls GitHub faster).
  const pending = status?.pending;
  useEffect(() => {
    if (!pending) return;
    const timer = window.setTimeout(() => run(api.githubPoll), Math.max(pending.interval, 2) * 1000);
    return () => window.clearTimeout(timer);
  }, [pending, run]);

  const push = async () => {
    setBusy(true);
    setError(null);
    setResult(null);
    try {
      const out = await api.githubPush(projectId, repo.trim(), isPrivate);
      setResult(out);
      try {
        localStorage.setItem(repoKey(projectId), repo.trim());
      } catch {
        // storage blocked: the default name comes back next time
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      api.githubStatus().then(setStatus, () => undefined);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="flex flex-col gap-3 text-sm break-keep">
      <p className="font-semibold text-foreground">GitHub에 올리기</p>
      {!status ? (
        <p className="text-muted-foreground">연결 상태를 확인하고 있어요…</p>
      ) : !status.configured ? (
        <p className="text-muted-foreground">운영자가 GitHub 연동을 켜지 않았어요. 내려받기(zip)로 받아 주세요.</p>
      ) : status.pending ? (
        <DeviceCode pending={status.pending} onCancel={() => run(api.githubDisconnect)} />
      ) : !status.connected ? (
        <>
          <p className="text-muted-foreground">
            내 GitHub 계정을 연결하면 결과물을 내 저장소에 커밋으로 올릴 수 있어요. 연결은 이 브라우저에만 적용되고, 비밀번호는 이 앱에 넣지 않아요.
          </p>
          <Button size="sm" onClick={() => run(api.githubConnect)}>GitHub 연결</Button>
        </>
      ) : (
        <>
          <p className="flex items-center justify-between gap-2 text-muted-foreground">
            <span>
              <b className="text-foreground">{status.login}</b> 계정으로 연결됐어요
            </span>
            <button type="button" onClick={() => run(api.githubDisconnect)} className="inline-flex items-center gap-1 text-xs hover:text-foreground">
              <LogOut className="size-3.5" aria-hidden="true" /> 연결 끊기
            </button>
          </p>
          <label className="flex flex-col gap-1">
            <span className="text-xs text-muted-foreground">저장소 이름 (없으면 내 계정에 새로 만들어요 · 조직은 owner/이름)</span>
            <input
              value={repo}
              onChange={(e) => setRepo(e.target.value)}
              className="rounded-lg border border-border bg-white/[0.04] px-3 py-2 font-mono text-sm text-foreground outline-none focus-visible:ring-[3px] focus-visible:ring-primary-ring"
              aria-label="저장소 이름"
              spellCheck={false}
            />
          </label>
          <label className="flex items-center gap-2 text-xs text-muted-foreground">
            <input type="checkbox" checked={isPrivate} onChange={(e) => setIsPrivate(e.target.checked)} />
            새로 만들 때 비공개 저장소로
          </label>
          <Button size="sm" onClick={push} disabled={busy || !repo.trim()}>
            {busy ? <LoaderCircle className="animate-spin" /> : <Upload />} {final ? "확정본 올리기" : "작업본 올리기"}
          </Button>
          <p className="text-xs text-faint">내려받기 zip과 같은 파일이 커밋 하나로 올라가요. 올릴 때마다 새 커밋이 쌓여요.</p>
        </>
      )}
      {result && (
        <p className="rounded-lg border border-border bg-white/[0.03] px-3 py-2 text-xs text-soft" role="status">
          {result.created ? "새 저장소를 만들고 " : ""}
          <b>{result.repo}</b>에 {result.files}개 파일을 올렸어요.{" "}
          <a href={result.commit_url} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 font-semibold text-primary-text hover:underline">
            커밋 보기 <ExternalLink className="size-3" aria-hidden="true" />
          </a>
        </p>
      )}
      {error && (
        <p className="text-xs text-destructive" role="alert">
          {error}
        </p>
      )}
    </div>
  );
}

function DeviceCode({ pending, onCancel }: { pending: NonNullable<GitHubStatus["pending"]>; onCancel: () => void }) {
  const [copied, setCopied] = useState(false);
  return (
    <div className="flex flex-col gap-2">
      <p className="text-muted-foreground">아래 코드를 GitHub 페이지에 넣고 허락해 주세요. 허락하면 여기서 자동으로 연결돼요.</p>
      <div className="flex items-center gap-2">
        <code className="rounded-lg bg-white/[0.06] px-3 py-1.5 font-mono text-lg font-bold tracking-widest text-foreground">{pending.user_code}</code>
        <button
          type="button"
          aria-label="코드 복사"
          onClick={() => navigator.clipboard?.writeText(pending.user_code).then(() => setCopied(true), () => undefined)}
          className="rounded-md p-1 text-muted-foreground hover:text-foreground"
        >
          <Copy className="size-4" />
        </button>
        {copied && <span className="text-xs text-faint">복사했어요</span>}
      </div>
      <a href={pending.verification_uri} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 font-semibold text-primary-text hover:underline">
        {pending.verification_uri.replace(/^https:\/\//, "")} 열기 <ExternalLink className="size-3.5" aria-hidden="true" />
      </a>
      <p className="flex items-center gap-2 text-xs text-faint">
        <LoaderCircle className="size-3.5 animate-spin" aria-hidden="true" /> 허락을 기다리는 중 · {Math.ceil(pending.expires_in / 60)}분 안에 넣어 주세요
        <button type="button" onClick={onCancel} className="ml-auto hover:text-foreground">취소</button>
      </p>
    </div>
  );
}
