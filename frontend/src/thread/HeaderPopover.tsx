import { useEffect, useId, useRef, useState, type ReactNode } from "react";
import { cn } from "@/lib/utils";

// A small disclosure popover for the header: a button that opens a panel under it.
// Closes on Escape (focus returns to the button) and on a click outside.
export default function HeaderPopover({ trigger, label, children, className, panelClassName }: {
  trigger: ReactNode;
  label: string;
  children: ReactNode;
  className?: string;
  panelClassName?: string;
}) {
  const [open, setOpen] = useState(false);
  const box = useRef<HTMLDivElement>(null);
  const button = useRef<HTMLButtonElement>(null);
  const id = useId();
  useEffect(() => {
    if (!open) return;
    const onDown = (e: MouseEvent) => {
      if (!box.current?.contains(e.target as Node)) setOpen(false);
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== "Escape") return;
      setOpen(false);
      button.current?.focus();
    };
    document.addEventListener("mousedown", onDown);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDown);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);
  return (
    <div ref={box} className={cn("relative", className)}>
      <button
        ref={button}
        type="button"
        aria-label={label}
        aria-expanded={open}
        aria-controls={id}
        onClick={() => setOpen(!open)}
        className="inline-flex cursor-pointer items-center gap-1.5 rounded-md px-1 text-sm whitespace-nowrap tabular-nums text-muted-foreground outline-none hover:text-foreground focus-visible:ring-[3px] focus-visible:ring-primary-ring"
      >
        {trigger}
      </button>
      {open && (
        <div
          id={id}
          role="dialog"
          aria-label={label}
          className={cn(
            "absolute top-[calc(100%+0.75rem)] right-0 z-40 rounded-2xl border border-border-strong bg-deep p-4 shadow-card backdrop-blur-md",
            panelClassName,
          )}
        >
          {children}
        </div>
      )}
    </div>
  );
}
