import { useEffect, useRef, useState } from "react";
import { cn } from "@/lib/utils";
import { dragWidth, keyWidth, maxWidth, MIN_WIDTH } from "./panelSize";

// The window's inner width, live (the panel's limits follow the window).
export function useViewportWidth(): number {
  const [vw, setVw] = useState(() => window.innerWidth);
  useEffect(() => {
    const on = () => setVw(window.innerWidth);
    window.addEventListener("resize", on);
    return () => window.removeEventListener("resize", on);
  }, []);
  return vw;
}

// A vertical splitter on the panel's left edge: drag with the pointer, or focus it and use ←/→.
export default function ResizeHandle({ width, viewport, onResize }: { width: number; viewport: number; onResize: (px: number) => void }) {
  const drag = useRef<{ x: number; width: number } | null>(null);
  const [active, setActive] = useState(false);

  return (
    <div
      role="separator"
      aria-orientation="vertical"
      aria-label="결과물 창 너비 조절 (←/→)"
      aria-controls="artifact-panel"
      aria-valuenow={width}
      aria-valuemin={MIN_WIDTH}
      aria-valuemax={maxWidth(viewport)}
      tabIndex={0}
      className={cn(
        "group absolute inset-y-0 -left-1.5 z-10 flex w-3 cursor-col-resize touch-none justify-center outline-none",
        "focus-visible:ring-[3px] focus-visible:ring-primary-ring",
      )}
      onPointerDown={(e) => {
        if (e.button !== 0) return;
        e.preventDefault();
        e.currentTarget.setPointerCapture(e.pointerId);
        drag.current = { x: e.clientX, width };
        setActive(true);
      }}
      onPointerMove={(e) => {
        if (drag.current) onResize(dragWidth(drag.current.width, drag.current.x, e.clientX, viewport));
      }}
      onPointerUp={(e) => {
        drag.current = null;
        setActive(false);
        if (e.currentTarget.hasPointerCapture(e.pointerId)) e.currentTarget.releasePointerCapture(e.pointerId);
      }}
      onPointerCancel={() => {
        drag.current = null;
        setActive(false);
      }}
      onKeyDown={(e) => {
        const next = keyWidth(width, e.key, viewport);
        if (next === null) return;
        e.preventDefault();
        onResize(next);
      }}
    >
      <span
        aria-hidden="true"
        className={cn(
          "h-full w-px bg-transparent transition-colors group-hover:bg-primary-text/60 group-focus-visible:bg-primary-text",
          active && "bg-primary-text",
        )}
      />
    </div>
  );
}
