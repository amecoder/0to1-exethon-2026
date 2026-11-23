import { ArrowRight, X } from "lucide-react";
import { createContext, useContext, useEffect, useLayoutEffect, useRef, useState, type ReactNode } from "react";
import { createPortal } from "react-dom";
import type { DocId } from "../api";
import { DOC_NAME } from "../panel/types";
import { codeMeaning, type RefInfo } from "../lib/refCatalog";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip";
import { splitIds } from "../lib/docOutline";

// IDs inside documents (REQ-03, SCR-01, DEC-02 …) as links: a click opens a small card with what the item is,
// and 「문서에서 보기」 jumps to the row of the document that lists it.
interface Refs {
  catalog: Record<string, RefInfo>;
  onJump?: (doc: DocId, id: string) => void;
}

const RefsContext = createContext<Refs>({ catalog: {} });

export function RefsProvider({ catalog, onJump, children }: Refs & { children: ReactNode }) {
  const parent = useContext(RefsContext);
  return <RefsContext.Provider value={{ catalog: catalog ?? parent.catalog, onJump: onJump ?? parent.onJump }}>{children}</RefsContext.Provider>;
}

// Only adds the jump handler, keeping the catalog given higher up.
export function RefJumpProvider({ onJump, children }: { onJump: (doc: DocId, id: string) => void; children: ReactNode }) {
  const parent = useContext(RefsContext);
  return <RefsContext.Provider value={{ ...parent, onJump }}>{children}</RefsContext.Provider>;
}

export function useRefs(): Refs {
  return useContext(RefsContext);
}

const CHIP = "mx-0.5 inline-block rounded-md bg-primary-soft px-1.5 py-px font-mono text-[11px] leading-5 font-semibold whitespace-nowrap text-primary-text";

// Hover: what the code is (kind, the item itself, what this kind of code means) — for readers new to codes.
// Own provider so the link also works outside a page-level TooltipProvider (start screen, cards).
function CodeTip({ id, info, open, children }: { id: string; info?: RefInfo; open?: boolean; children: ReactNode }) {
  const meaning = codeMeaning(id);
  if (!meaning && !info) return <>{children}</>;
  return (
    <TooltipProvider delayDuration={120}>
      <Tooltip open={open ? false : undefined}>
        <TooltipTrigger asChild>{children}</TooltipTrigger>
        <TooltipContent className="max-w-80 text-left break-keep">
          <p className="font-semibold text-foreground">
            <span className="font-mono">{id}</span> · {info?.kind ?? meaning?.kind}
          </p>
          {info && info.title !== id && <p className="mt-0.5 line-clamp-2 text-soft">{info.title}</p>}
          {meaning && <p className="mt-1 text-muted-foreground">{meaning.about}</p>}
          {info && <p className="mt-1 text-faint">누르면 자세히 볼 수 있어요</p>}
        </TooltipContent>
      </Tooltip>
    </TooltipProvider>
  );
}

// `label`: what the reader sees (the ID chip in the team view, 「name」 in the client view).
export function RefLink({ id, label }: { id: string; label?: string }) {
  const { catalog } = useRefs();
  const info = catalog[id];
  const button = useRef<HTMLSpanElement>(null);
  const [open, setOpen] = useState(false);
  if (!info) {
    return (
      <CodeTip id={id}>
        {label ? <span tabIndex={0} className="underline decoration-muted-foreground/50 decoration-dotted underline-offset-4">{label}</span> : <code tabIndex={0} className={CHIP}>{id}</code>}
      </CodeTip>
    );
  }
  return (
    <>
      {/* A span with button role: RefLink also sits inside buttons (doc tiles, log rows), where a real
          <button> would nest; clicks stop here so the outer control does not fire. */}
      <CodeTip id={id} info={info} open={open}>
        <span
          ref={button}
          role="button"
          tabIndex={0}
          aria-haspopup="dialog"
          aria-expanded={open}
          aria-label={`${id} ${info.kind}: ${info.title}`}
          onClick={(e) => {
            e.preventDefault();
            e.stopPropagation();
            setOpen((v) => !v);
          }}
          onKeyDown={(e) => {
            if (e.key !== "Enter" && e.key !== " ") return;
            e.preventDefault();
            e.stopPropagation();
            setOpen((v) => !v);
          }}
          className={label
            ? "cursor-pointer rounded-sm text-inherit underline decoration-primary-text/50 decoration-dotted underline-offset-4 hover:text-primary-text focus-visible:outline-2"
            : `${CHIP} cursor-pointer hover:bg-primary-text/25 focus-visible:outline-2`}
        >
          {label ?? id}
        </span>
      </CodeTip>
      {open && <RefCard info={info} anchor={button} onClose={() => setOpen(false)} />}
    </>
  );
}

function RefCard({ info, anchor, onClose }: { info: RefInfo; anchor: React.RefObject<HTMLSpanElement | null>; onClose: () => void }) {
  const { onJump } = useRefs();
  const card = useRef<HTMLDivElement>(null);
  const [pos, setPos] = useState<{ top: number; left: number } | null>(null);

  useLayoutEffect(() => {
    const r = anchor.current?.getBoundingClientRect();
    if (!r) return;
    const width = Math.min(352, window.innerWidth - 24);
    const height = card.current?.offsetHeight ?? 0;
    const below = r.bottom + 6 + height < window.innerHeight;
    setPos({ left: Math.max(12, Math.min(r.left, window.innerWidth - width - 12)), top: below ? r.bottom + 6 : Math.max(12, r.top - height - 6) });
  }, [anchor]);

  useEffect(() => {
    const away = (e: Event) => {
      if (!card.current?.contains(e.target as Node) && !anchor.current?.contains(e.target as Node)) onClose();
    };
    const key = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    document.addEventListener("pointerdown", away);
    document.addEventListener("keydown", key);
    window.addEventListener("resize", onClose);
    return () => {
      document.removeEventListener("pointerdown", away);
      document.removeEventListener("keydown", key);
      window.removeEventListener("resize", onClose);
    };
  }, [anchor, onClose]);

  return createPortal(
    <div
      ref={card}
      role="dialog"
      aria-label={`${info.kind} ${info.id}`}
      // A portal still bubbles React events to the link's ancestors (maybe a button): stop them here.
      onClick={(e) => e.stopPropagation()}
      className="fixed z-[80] w-[22rem] max-w-[calc(100vw-1.5rem)] rounded-2xl border border-border-strong bg-popover p-4 text-left text-popover-foreground shadow-card animate-rise"
      style={pos ?? { visibility: "hidden", top: 0, left: 0 }}
    >
      <div className="flex items-start justify-between gap-2">
        <p className="text-xs font-semibold text-primary-text">
          {info.kind} <span className="font-mono text-muted-foreground">{info.id}</span>
        </p>
        <button type="button" onClick={onClose} aria-label="닫기" className="rounded-md p-0.5 text-muted-foreground hover:text-foreground">
          <X className="size-3.5" />
        </button>
      </div>
      <p className="mt-1 text-sm font-semibold break-keep text-foreground">{info.title}</p>
      {codeMeaning(info.id) && <p className="mt-1 text-xs break-keep text-muted-foreground">{codeMeaning(info.id)?.about}</p>}
      {info.lines.length > 0 && (
        <dl className="mt-2 grid grid-cols-[5rem_1fr] gap-x-2 gap-y-1 text-xs break-keep">
          {info.lines.map((l) => (
            <div key={l.label} className="contents">
              <dt className="text-muted-foreground">{l.label}</dt>
              <dd className="text-soft [overflow-wrap:anywhere]">{l.value}</dd>
            </div>
          ))}
        </dl>
      )}
      {info.doc && onJump && (
        <button
          type="button"
          onClick={() => {
            onJump(info.doc as DocId, info.id);
            onClose();
          }}
          className="mt-3 inline-flex items-center gap-1 text-xs font-semibold text-primary-text hover:underline"
        >
          {DOC_NAME[info.doc]}에서 보기 <ArrowRight className="size-3.5" aria-hidden="true" />
        </button>
      )}
    </div>,
    document.body,
  );
}

// Any UI text with codes in it ("바꿀 때마다 1번(CP5)"): known codes become links, the rest stays text.
export function Codes({ text }: { text: string }) {
  const { catalog } = useRefs();
  return (
    <>
      {splitIds(text).map((p, i) =>
        p.id && (catalog[p.text] || codeMeaning(p.text)) ? (
          <RefLink key={i} id={p.text} label={p.text} />
        ) : (
          <span key={i}>{p.text}</span>
        ),
      )}
    </>
  );
}
