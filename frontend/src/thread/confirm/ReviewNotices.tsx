import { Notice, NoticeList } from "@/components/ui/notice";
import type { CheckWarning, Review } from "../../api";
import { nameIds } from "../../lib/summarize";
import { RefId, useTitles, useView } from "../../ui/view";

// A warning sentence: IDs replaced by names for the client, kept (with the target chip) for the team.
export function WarningText({ w }: { w: CheckWarning }) {
  const team = useView() === "team";
  const titles = useTitles();
  return team ? (
    <>
      <RefId id={w.target} /> {w.message}
    </>
  ) : (
    <>{nameIds(w.message, titles)}</>
  );
}

export function BlockingNotice({ review }: { review: Review }) {
  if (review.blocking.length === 0) return null;
  return (
    <Notice kind="block" title={`고른 답과 다르게 적힌 요구사항이 ${review.blocking.length}건 있어요`}>
      <p className="mb-2 text-sm break-keep text-soft">
        이대로는 승인할 수 없어요. 아래 「궁금한 점·고칠 점이 있어요」에 고칠 점을 적어 주시면 팀이 고쳐서 다시 보여 드려요.
      </p>
      <NoticeList items={review.blocking.map((w) => <WarningText key={w.id} w={w} />)} />
    </Notice>
  );
}

// The reason each 빈칸 goes with: what the client typed, else the one the team filled in (11-22). An emptied
// field stays empty, so clearing a filled reason asks for a new one.
export function waiverValues(review: Review | undefined, waivers: Record<string, string>): Record<string, string> {
  const out: Record<string, string> = {};
  for (const w of review?.waivable ?? []) {
    const value = (waivers[w.id] ?? w.suggested ?? "").trim();
    if (value) out[w.id] = value;
  }
  return out;
}

// Coverage gaps that may pass with a one-line reason (the reason is stored with the approval).
export function WaiverNotice({ review, waivers, setWaiver, live }: {
  review: Review;
  waivers: Record<string, string>;
  setWaiver: (id: string, reason: string) => void;
  live: boolean;
}) {
  if (review.waivable.length === 0) return null;
  const values = waiverValues(review, waivers);
  const filled = Object.keys(values).length;
  const prefilled = review.waivable.some((w) => w.suggested);
  return (
    <Notice kind="reason" title={`빈칸 ${review.waivable.length}건 — 이유를 적으면 그대로 진행할 수 있어요`}>
      {prefilled && live && (
        <p className="mb-3 text-sm break-keep text-soft">
          팀이 이유를 미리 채워 뒀어요. 설명을 읽어 보고 맞지 않으면 고쳐 주세요. 그대로 두면 이 이유로 승인돼요.
        </p>
      )}
      <ul className="flex flex-col gap-4">
        {review.waivable.map((w) => (
          <li key={w.id} className="flex flex-col gap-1.5">
            <label htmlFor={`waiver-${w.id}`} className="text-sm font-medium break-keep text-foreground">
              <WarningText w={w} />
            </label>
            {w.explain && <ExplainText text={w.explain} />}
            <input
              id={`waiver-${w.id}`}
              value={waivers[w.id] ?? w.suggested ?? ""}
              maxLength={200}
              disabled={!live}
              placeholder={live ? "그대로 진행하는 이유를 한 줄로 적어 주세요" : "녹화에서는 이유를 적고 승인했어요"}
              onChange={(e) => setWaiver(w.id, e.target.value)}
              className="h-11 rounded-xl border border-[rgb(242_182_90/0.3)] bg-deep/70 px-3.5 text-base text-foreground outline-none placeholder:text-faint focus-visible:border-warning focus-visible:ring-[3px] focus-visible:ring-[rgb(242_182_90/0.3)] disabled:opacity-60"
            />
          </li>
        ))}
      </ul>
      {review.waivable.length > 1 && (
        <p className="mt-2 text-xs text-muted-foreground">
          {filled}/{review.waivable.length}건 적었어요
        </p>
      )}
    </Notice>
  );
}

// The explanation names things, but an open item's text may still carry IDs: names for the client.
function ExplainText({ text }: { text: string }) {
  const team = useView() === "team";
  const titles = useTitles();
  return <p className="text-sm leading-relaxed break-keep text-muted-foreground">{team ? text : nameIds(text, titles)}</p>;
}

export function InfoNotices({ list, title }: { list: CheckWarning[]; title?: string }) {
  if (list.length === 0) return null;
  return (
    <Notice kind="info" title={title ?? `알아 두시면 좋은 점 ${list.length}건`}>
      <NoticeList items={list.map((w) => <WarningText key={w.id} w={w} />)} />
    </Notice>
  );
}

// Why the approve button is locked, said right next to it.
export function approvalBlocker(review: Review | undefined, waivers: Record<string, string>): string | null {
  if (!review) return null;
  if (review.blocking.length > 0) return `고른 답과 다른 곳 ${review.blocking.length}건을 먼저 고쳐야 해요`;
  const values = waiverValues(review, waivers);
  const missing = review.waivable.filter((w) => !values[w.id]).length;
  if (missing > 0) return `빈칸 ${missing}건에 이유를 적으면 승인할 수 있어요`;
  return null;
}
