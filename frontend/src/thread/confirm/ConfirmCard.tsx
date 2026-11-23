import { Check, LoaderCircle, Lock, PenLine, Undo2 } from "lucide-react";
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import type { ChecklistRow, DocId, DocView, Prototype, SharedSourceData, Todo } from "../../api";
import type { PanelTarget } from "../../panel/types";
import { RefId, useView } from "../../ui/view";
import { Notice } from "@/components/ui/notice";
import AnswerCompare from "./AnswerCompare";
import { ReplyList } from "./Alternatives";
import DocTiles from "./DocTiles";
import FeedbackChips from "./FeedbackChips";
import ProblemSection from "./ProblemSection";
import PrototypeSection from "./PrototypeSection";
import RequirementSection from "./RequirementSection";
import RequirementDeck, { deckBlocker, type Review } from "./RequirementDeck";
import { approvalBlocker, BlockingNotice, InfoNotices, WaiverNotice, waiverValues } from "./ReviewNotices";
import { Term } from "../../ui/Term";

type ConfirmTodo = Extract<Todo, { kind: "confirmation" }>;
export type Decide = (approved: boolean, reason?: string, waivers?: Record<string, string>) => Promise<void>;

const COPY: Record<ConfirmTodo["cp"], { no: number; eyebrow: string; title: string; client: string; team: string; approve: string }> = {
  CP1: {
    no: 1,
    eyebrow: "문제와 범위",
    title: "팀이 이해한 문제가 맞는지 봐 주세요",
    client: "맞으면 승인해 주세요. 그다음 꼭 필요한 것만 질문으로 여쭤볼게요.",
    team: "승인하면 S3 구체화(요구사항 후보 · QA 점검 · 질문 카드)로 넘어가요.",
    approve: "네, 맞아요",
  },
  CP2: {
    no: 2,
    eyebrow: "요구사항",
    title: "고른 답으로 정리한 요구사항을 확정할까요?",
    client: "승인하면 지금 내용으로 고정하고 팀이 문서를 쓰기 시작해요.",
    team: "승인하면 요구사항 원본이 v1으로 고정되고 S5 문서화가 시작돼요.",
    approve: "확정할게요",
  },
  CP3: {
    no: 3,
    eyebrow: "문서 4종 · 프로토타입 작성",
    title: "문서 4종을 보고 프로토타입을 만들까요?",
    client: "문서를 열어 보고 괜찮으면 승인해 주세요. 승인하면 개발자가 프로토타입을 만들기 시작해요.",
    team: "승인하면 문서 4종이 v2로 고정되고 S6 개발이 시작돼요. 빈칸 이유는 승인 기록에 함께 남아요.",
    approve: "프로토타입 만들어 주세요",
  },
  CP4: {
    no: 4,
    eyebrow: "프로토타입 인수",
    title: "프로토타입을 받아 보시겠어요?",
    client: "직접 눌러 보고 괜찮으면 승인해 주세요. 승인하면 결과물을 내려받을 수 있어요.",
    team: "승인하면 인수 기록이 남고 zip 내려받기가 열려요.",
    approve: "받을게요",
  },
};

// The one big task card for a confirmation (CP1–CP4): what will be fixed, the checks, approve / reject.
// `onDecide` is absent in demo replay — the card is shown as recorded, read-only.
export default function ConfirmCard({ todo, source, docs, onDecide, onUseExisting, onBuildGap, onOpen, lock, onReview, onSendFixes, onConfirmRest }: {
  todo: ConfirmTodo;
  source: SharedSourceData;
  docs: Record<DocId, DocView> | null;
  onDecide?: Decide;
  onUseExisting?: (alternativeId: string) => Promise<void>; // CP1 only: end with an existing product
  onBuildGap?: (alternativeId: string) => Promise<void>; // CP1 only: keep the product, build what it lacks
  onOpen: (t: PanelTarget) => void;
  lock?: string | null; // a reason approval waits on something outside this card (an open CP5 change)
  onReview?: Review; // CP2 card deck: 확정 / 고칠 점 per requirement (absent in demo replay)
  onSendFixes?: () => Promise<void>;
  onConfirmRest?: () => Promise<unknown>; // CP2 deck: every open card 확정 at once
}) {
  const team = useView() === "team";
  const copy = COPY[todo.cp];
  const review = todo.review;
  const live = Boolean(onDecide);
  const [waivers, setWaivers] = useState<Record<string, string>>({});
  const blocked = (review?.blocking.length ?? 0) > 0;
  const [rejecting, setRejecting] = useState(blocked);
  const [reason, setReason] = useState("");
  const [pending, setPending] = useState<"approve" | "reject" | null>(null);
  const deck = todo.cp === "CP2" && live && onReview && onSendFixes && todo.req_reviews ? todo.req_reviews : null;
  const blocker = lock ?? approvalBlocker(review, waivers) ?? deckBlocker(deck ?? undefined);
  const filled = waiverValues(review, waivers); // typed reasons, else the ones the team filled in (11-22)
  const prototypes = (source.prototype as Prototype[] | undefined) ?? [];
  const checklists = (source.qa_checklist as { rows: ChecklistRow[] }[] | undefined) ?? [];

  const decide = async (approved: boolean) => {
    if (!onDecide) return;
    setPending(approved ? "approve" : "reject");
    try {
      await onDecide(approved, approved ? undefined : reason.trim(), approved ? filled : undefined);
      if (!approved) setReason("");
    } finally {
      setPending(null);
    }
  };

  return (
    <Card className="animate-rise px-8 pt-7 pb-7" aria-labelledby="confirm-title">
      <p className="flex items-center gap-2 text-sm font-semibold text-primary-text">
        <Term name="체크포인트" /> {copy.no}/4 · {copy.eyebrow}
        {team && <RefId id={todo.cp} />}
      </p>
      <h2 id="confirm-title" className="mt-3 text-title font-bold tracking-[-0.02em] text-balance break-keep text-foreground">
        {copy.title}
      </h2>
      <p className="mt-2 text-base break-keep text-muted-foreground">{team ? copy.team : copy.client}</p>
      {team && review?.summary && (todo.cp === "CP3" || todo.cp === "CP4") && (
        <p className="mt-1 text-sm break-keep text-faint">{review.summary}</p>
      )}

      <div className="mt-6 flex flex-col gap-5">
        {source.meta.pipeline?.error && (
          <Notice kind="reason" tag="다시 적어 주세요" title="말씀에 답하지 못했어요">
            <p className="text-sm break-keep text-soft">{source.meta.pipeline.error}</p>
          </Notice>
        )}
        <ReplyList items={(source.replies ?? []).filter((r) => r.cp === todo.cp)} />
        {review && <BlockingNotice review={review} />}
        {todo.cp === "CP1" && <ProblemSection source={source} onUseExisting={onUseExisting} onBuildGap={onBuildGap} />}
        {review && <AnswerCompare review={review} />}
        {todo.cp === "CP2" && deck && onReview && onSendFixes ? (
          <RequirementDeck requirements={source.requirements} reviews={deck} onReview={onReview} onSendFixes={onSendFixes} onConfirmRest={onConfirmRest} />
        ) : (
          todo.cp === "CP2" && <RequirementSection requirements={source.requirements} />
        )}
        {todo.cp === "CP3" && <DocTiles docs={docs} onOpen={onOpen} />}
        {todo.cp === "CP4" && (
          <PrototypeSection prototype={prototypes[prototypes.length - 1]} checklist={checklists[checklists.length - 1]?.rows ?? []} onOpen={onOpen} />
        )}
        {(todo.cp === "CP3" || todo.cp === "CP4") && (
          <FeedbackChips cp={todo.cp} items={review?.consumer_feedback ?? []} />
        )}
        {review && (
          <WaiverNotice review={review} waivers={waivers} live={live} setWaiver={(id, v) => setWaivers({ ...waivers, [id]: v })} />
        )}
        {review && <InfoNotices list={review.notices} />}
      </div>

      <div className="mt-7 border-t border-border pt-6">
        {live ? (
          <div className="flex flex-col gap-4">
            <div className="flex flex-wrap items-center gap-3">
              <Button
                size="lg"
                disabled={pending !== null || blocker !== null}
                aria-describedby={blocker ? "approve-blocker" : undefined}
                onClick={() => decide(true)}
              >
                {pending === "approve" ? <LoaderCircle className="animate-spin" /> : blocker ? <Lock /> : <Check />}
                {copy.approve}
              </Button>
              {!rejecting && (
                <Button variant="outline" size="lg" disabled={pending !== null} onClick={() => setRejecting(true)}>
                  <PenLine /> 궁금한 점·고칠 점이 있어요
                </Button>
              )}
              {blocker && (
                <p id="approve-blocker" className="text-sm break-keep text-muted-foreground">
                  {blocker}
                </p>
              )}
            </div>
            {rejecting && (
              <form
                className="flex flex-col gap-2"
                onSubmit={(e) => {
                  e.preventDefault();
                  if (reason.trim()) void decide(false);
                }}
              >
                <label htmlFor="reject-reason" className="text-sm font-medium text-soft">
                  궁금한 점이나 고칠 점을 한 줄로 적어 주세요. 질문이면 여기서 답만 드리고, 고칠 점이면 고쳐서 다시 보여 드려요.
                </label>
                <div className="flex items-center gap-2 rounded-2xl border border-border bg-white/[0.03] py-1.5 pr-1.5 pl-4 focus-within:border-primary-text/60">
                  <input
                    id="reject-reason"
                    value={reason}
                    maxLength={200}
                    onChange={(e) => setReason(e.target.value)}
                    placeholder={blocked ? "예) 배송 요일은 수·토 중 고르는 걸로 고쳐 주세요" : "예) 하지 않는 것에 서울 밖 배송을 넣어 주세요"}
                    className="h-10 min-w-0 flex-1 border-0 bg-transparent p-0 text-base text-foreground outline-none placeholder:text-faint focus-visible:outline-none"
                  />
                  <Button type="submit" variant="secondary" disabled={pending !== null || !reason.trim()}>
                    {pending === "reject" ? <LoaderCircle className="animate-spin" /> : <Undo2 />} 보내기
                  </Button>
                </div>
              </form>
            )}
          </div>
        ) : (
          <p className="text-sm text-muted-foreground">녹화 당시 발주사가 여기서 승인하거나 반려했어요. 다음 장면에서 결과가 보여요.</p>
        )}
      </div>
    </Card>
  );
}
