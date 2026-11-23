import { RefreshCw } from "lucide-react";
import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { buildOf, isNewBuild } from "../lib/version";

const EVERY_MS = 60_000;

function runningBuild(): string | null {
  const src = document.querySelector<HTMLScriptElement>('script[type="module"][src*="/assets/index-"]')?.getAttribute("src");
  return src ? buildOf(`src="${src}"`) : null;
}

// A tab left open across a deploy keeps running the old bundle (index.html is no-cache, but only a reload
// fetches it). Check the served index.html every minute and when the tab comes back, and offer a reload —
// not an automatic one, so an answer being typed is never lost.
export default function NewBuildNotice() {
  const [fresh, setFresh] = useState(false);
  useEffect(() => {
    const current = runningBuild();
    if (current === null) return; // dev server: nothing to compare
    let stop = false;
    const check = async () => {
      if (stop || document.visibilityState !== "visible") return;
      try {
        const res = await fetch("/", { cache: "no-store" });
        if (res.ok && isNewBuild(current, await res.text())) setFresh(true);
      } catch {
        // offline or server restarting: try again on the next tick
      }
    };
    const timer = window.setInterval(check, EVERY_MS);
    document.addEventListener("visibilitychange", check);
    return () => {
      stop = true;
      window.clearInterval(timer);
      document.removeEventListener("visibilitychange", check);
    };
  }, []);
  if (!fresh) return null;
  return (
    <div role="status" className="fixed bottom-5 left-1/2 z-50 flex -translate-x-1/2 items-center gap-3 rounded-2xl border border-cyan/40 bg-popover px-4 py-2.5 text-sm text-popover-foreground shadow-lg">
      <span>새 버전이 배포됐어요. 새로고침하면 바로 적용돼요</span>
      <Button size="sm" onClick={() => window.location.reload()}>
        <RefreshCw aria-hidden="true" /> 새로고침
      </Button>
    </div>
  );
}
