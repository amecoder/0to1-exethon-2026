import { ChevronDown, FileText, Image, Mic } from "lucide-react";
import { useState } from "react";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible";
import type { SourceSentence } from "../api";
import { RefId, useView } from "../ui/view";

const PREVIEW = 3;
// Sentences that were not typed: how many came from each kind of upload.
const ORIGINS = [
  { origin: "audio", Icon: Mic, text: (n: number) => `그중 ${n}문장은 회의 녹음에서 받아 적었어요` },
  { origin: "image", Icon: Image, text: (n: number) => `그중 ${n}문장은 첨부 이미지에서 옮겨 적었어요` },
  { origin: "document", Icon: FileText, text: (n: number) => `그중 ${n}문장은 첨부 문서에서 옮겨 적었어요` },
] as const;

// The client's own request, like the user's message in a chat: first sentences, the rest on demand.
export default function RequestBubble({ sources }: { sources: SourceSentence[] }) {
  const [open, setOpen] = useState(false);
  const team = useView() === "team";
  if (sources.length === 0) return null;
  const rest = sources.slice(PREVIEW);
  return (
    <section className="flex flex-col items-end gap-1.5" aria-label="보낸 요청">
      <p className="pr-1 text-xs font-medium text-muted-foreground">보낸 요청 · {sources.length}문장으로 나눠 원문 그대로 보관했어요</p>
      {ORIGINS.map(({ origin, Icon, text }) => {
        const count = sources.filter((s) => s.origin === origin).length;
        return (
          count > 0 && (
            <p key={origin} className="flex items-center gap-1 pr-1 text-xs text-muted-foreground">
              <Icon className="size-3.5 text-cyan" aria-hidden="true" /> {text(count)}
            </p>
          )
        );
      })}
      <Collapsible open={open} onOpenChange={setOpen} className="max-w-[88%] rounded-3xl rounded-tr-lg border border-white/[0.08] bg-white/[0.07] px-5 py-4">
        <p className="text-base leading-relaxed break-keep text-foreground">
          {sources.slice(0, PREVIEW).map((s) => (
            <Sentence key={s.id} s={s} team={team} />
          ))}
          {!open && rest.length > 0 && <span className="text-faint">…</span>}
        </p>
        {rest.length > 0 && (
          <>
            <CollapsibleContent>
              <p className="text-base leading-relaxed break-keep text-foreground">
                {rest.map((s) => (
                  <Sentence key={s.id} s={s} team={team} />
                ))}
              </p>
            </CollapsibleContent>
            <CollapsibleTrigger className="group mt-2 inline-flex cursor-pointer items-center gap-1 rounded-md text-sm font-medium text-muted-foreground hover:text-foreground">
              {open ? "접기" : `${rest.length}문장 더 보기`}
              <ChevronDown className="size-4 transition-transform group-data-[state=open]:rotate-180" aria-hidden="true" />
            </CollapsibleTrigger>
          </>
        )}
      </Collapsible>
    </section>
  );
}

function Sentence({ s, team }: { s: SourceSentence; team: boolean }) {
  const marked = s.origin !== undefined;
  const note = s.attachment_file ? `${s.origin_note} · ${s.attachment_file}` : s.origin_note;
  return (
    <span className={marked ? "underline decoration-cyan/40 decoration-dotted underline-offset-4" : undefined} title={marked ? note : undefined}>
      {s.text} {team && <RefId id={s.id} />}
      {team && marked && <span className="ml-1 text-xs text-faint">({note})</span>}{" "}
    </span>
  );
}
