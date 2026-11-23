import { ExternalLink, LoaderCircle, MessageCircleReply, PackageSearch } from "lucide-react";
import { useState } from "react";
import { Button } from "@/components/ui/button";
import type { Alternative, ClientReply } from "../../api";
import { RefId } from "../../ui/view";
import { StatusChip } from "../StatusChip";

// Shown first at a confirmation: what the client asked there and the team's answer, oldest first.
export function ReplyList({ items }: { items: ClientReply[] }) {
  if (items.length === 0) return null;
  return (
    <div className="flex flex-col gap-2">
      {items.map((r) => (
        <section key={r.id} className="rounded-2xl border border-primary-text/40 bg-primary-text/[0.06] p-4" aria-label="말씀에 대한 답">
          <p className="text-sm text-muted-foreground">
            물어보신 것: “{r.question}”{r.intent === "both" && " · 고칠 점은 반영해서 다시 만들었어요"}
          </p>
          <p className="mt-2 flex items-start gap-2 text-base font-medium break-keep text-foreground">
            <MessageCircleReply className="mt-1 size-4 shrink-0 text-primary-text" aria-hidden="true" />
            <span className="min-w-0">
              {r.answer} <RefId id={r.refs} />
            </span>
          </p>
        </section>
      ))}
    </div>
  );
}

// CP1 build-or-buy: existing products the researcher found, what they do and what they lack.
// With `onUse` (live mode) the client can end here with one of them instead of building;
// with `onGap` the client keeps the product and the team builds only what it lacks (CP1 is approved).
const FIRST_SHOWN = 3;

export function AlternativeList({ items, onUse, onGap }: {
  items: Alternative[];
  onUse?: (id: string) => Promise<void>;
  onGap?: (id: string) => Promise<void>;
}) {
  const [pending, setPending] = useState<string | null>(null);
  const [all, setAll] = useState(false);
  const shown = all ? items : items.slice(0, FIRST_SHOWN);
  if (items.length === 0) return null;
  const run = async (key: string, action: () => Promise<void>) => {
    setPending(key);
    try {
      await action();
    } finally {
      setPending(null);
    }
  };
  return (
    <section className="flex flex-col gap-3" aria-labelledby="alt-title">
      <div>
        <h3 id="alt-title" className="flex items-center gap-2 text-sm font-semibold text-muted-foreground">
          <PackageSearch className="size-4" aria-hidden="true" /> 이미 있는 제품 {items.length}개
        </h3>
        <p className="mt-1 text-sm break-keep text-soft">
          만들기 전에 찾아봤어요. 이걸로 충분하면 골라서 여기서 마칠 수 있고, 제품은 그대로 쓰면서 모자란 부분만 만들 수도 있어요. 전부 새로 만들려면 아래에서 승인하면 돼요.
        </p>
      </div>
      <ul className="flex flex-col gap-2">
        {shown.map((a) => (
          <li key={a.id} className="rounded-2xl border border-border bg-white/[0.025] p-4">
            <div className="flex flex-wrap items-center gap-2">
              <span className="text-base font-semibold text-foreground">{a.name}</span>
              {a.status === "미확인" && <StatusChip status="미확인" />}
              <RefId id={a.evidence_refs} />
              {a.url && (
                <a href={a.url} target="_blank" rel="noreferrer noopener" className="inline-flex items-center gap-1 text-xs text-muted-foreground underline-offset-2 hover:underline">
                  출처 <ExternalLink className="size-3" aria-hidden="true" />
                </a>
              )}
            </div>
            <dl className="mt-2 grid gap-1 text-sm break-keep sm:grid-cols-[6rem_1fr]">
              <dt className="text-cyan">되는 것</dt>
              <dd className="text-soft">{a.covers || "—"}</dd>
              <dt className="text-warning">안 되는 것</dt>
              <dd className="text-soft">{a.lacks || "확인한 빈틈이 없어요"}</dd>
            </dl>
            {(onUse || onGap) && (
              <div className="mt-3 flex flex-wrap gap-2">
                {onUse && (
                  <Button variant="outline" size="sm" disabled={pending !== null} onClick={() => run(`use:${a.id}`, () => onUse(a.id))}>
                    {pending === `use:${a.id}` && <LoaderCircle className="animate-spin" />} 이 제품을 쓸게요 — 여기서 마치기
                  </Button>
                )}
                {onGap && (
                  <Button variant="outline" size="sm" disabled={pending !== null} onClick={() => run(`gap:${a.id}`, () => onGap(a.id))}>
                    {pending === `gap:${a.id}` && <LoaderCircle className="animate-spin" />} 모자란 부분만 만들기
                  </Button>
                )}
              </div>
            )}
            {onGap && (
              <p className="mt-2 text-xs break-keep text-muted-foreground">
                모자란 부분만 만들기: {a.name}은(는) 그대로 쓰고, 안 되는 것과 {a.name}에 연결하는 부분만 만들도록 확인을 마치고 다음 단계로 넘어가요.
              </p>
            )}
          </li>
        ))}
      </ul>
      {items.length > FIRST_SHOWN && (
        <Button className="self-start" variant="ghost" size="sm" onClick={() => setAll(!all)}>
          {all ? "접기" : `나머지 ${items.length - FIRST_SHOWN}개 더 보기`}
        </Button>
      )}
    </section>
  );
}
