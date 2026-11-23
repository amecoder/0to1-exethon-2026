import { useRef, type ReactNode } from "react";
import { cn } from "@/lib/utils";

export interface TabItem<T extends string> {
  value: T;
  label: ReactNode;
  disabled?: boolean;
}

// A small accessible tab list (roving focus with arrow keys, Home/End). Panels are rendered by the caller
// with id `${idBase}-panel` and aria-labelledby `${idBase}-tab-${value}`.
export function Tabs<T extends string>({ items, value, onChange, idBase, label, size = "md", className }: {
  items: TabItem<T>[];
  value: T;
  onChange: (v: T) => void;
  idBase: string;
  label: string;
  size?: "sm" | "md";
  className?: string;
}) {
  const refs = useRef<(HTMLButtonElement | null)[]>([]);
  const enabled = items.filter((i) => !i.disabled);
  const move = (dir: number | "home" | "end") => {
    const at = enabled.findIndex((i) => i.value === value);
    const next =
      dir === "home" ? 0 : dir === "end" ? enabled.length - 1 : (at + dir + enabled.length) % enabled.length;
    const target = enabled[next];
    onChange(target.value);
    refs.current[items.indexOf(target)]?.focus();
  };
  return (
    <div
      role="tablist"
      aria-label={label}
      className={cn("inline-flex items-center gap-1 rounded-xl border border-border bg-white/[0.04] p-1", className)}
      onKeyDown={(e) => {
        if (e.key === "ArrowRight") move(1);
        else if (e.key === "ArrowLeft") move(-1);
        else if (e.key === "Home") move("home");
        else if (e.key === "End") move("end");
        else return;
        e.preventDefault();
      }}
    >
      {items.map((item, i) => {
        const selected = item.value === value;
        return (
          <button
            key={item.value}
            ref={(el) => (refs.current[i] = el)}
            type="button"
            role="tab"
            id={`${idBase}-tab-${item.value}`}
            aria-selected={selected}
            aria-controls={`${idBase}-panel`}
            tabIndex={selected ? 0 : -1}
            disabled={item.disabled}
            onClick={() => onChange(item.value)}
            className={cn(
              "inline-flex cursor-pointer items-center gap-1.5 rounded-lg font-semibold whitespace-nowrap transition-colors outline-none focus-visible:ring-[3px] focus-visible:ring-primary-ring disabled:cursor-default disabled:opacity-40",
              size === "sm" ? "h-7 px-2.5 text-xs" : "h-8 px-3 text-sm",
              selected ? "bg-white/[0.12] text-foreground" : "text-muted-foreground hover:text-foreground",
            )}
          >
            {item.label}
          </button>
        );
      })}
    </div>
  );
}
