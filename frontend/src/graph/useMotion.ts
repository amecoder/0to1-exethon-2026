import { useEffect, useState, type RefObject } from "react";

// prefers-reduced-motion, live (the OS setting can change while the page is open).
export function useReducedMotion(): boolean {
  const query = "(prefers-reduced-motion: reduce)";
  const [reduced, setReduced] = useState(() => typeof window !== "undefined" && window.matchMedia?.(query).matches);
  useEffect(() => {
    const mq = window.matchMedia?.(query);
    if (!mq) return;
    const on = () => setReduced(mq.matches);
    mq.addEventListener("change", on);
    return () => mq.removeEventListener("change", on);
  }, []);
  return reduced;
}

// The element's content size (0×0 until measured).
export function useSize(ref: RefObject<HTMLElement>): { width: number; height: number } {
  const [size, setSize] = useState({ width: 0, height: 0 });
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const observer = new ResizeObserver(([entry]) => {
      const { width, height } = entry.contentRect;
      setSize((s) => (Math.round(s.width) === Math.round(width) && Math.round(s.height) === Math.round(height) ? s : { width, height }));
    });
    observer.observe(el);
    return () => observer.disconnect();
  }, [ref]);
  return size;
}
