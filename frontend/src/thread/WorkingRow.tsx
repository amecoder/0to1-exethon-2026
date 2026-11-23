import type { ReactNode } from "react";
import { AgentAvatar } from "./AgentAvatar";

// Text with a slow light sweep — the only "working" animation in the thread.
export function ShimmerText({ children }: { children: ReactNode }) {
  return (
    <span className="bg-[linear-gradient(90deg,var(--color-faint)_0%,var(--color-faint)_40%,var(--color-foreground)_50%,var(--color-faint)_60%,var(--color-faint)_100%)] bg-[length:200%_100%] bg-clip-text text-transparent animate-shimmer">
      {children}
    </span>
  );
}

// The "team is working" line between steps: active agent avatar + one sentence.
export default function WorkingRow({ agent, text }: { agent: string | null; text: string }) {
  return (
    <div className="flex animate-rise items-center gap-3 px-3 py-2" role="status" aria-live="polite">
      <AgentAvatar id={agent ?? "coordinator"} active />
      <p className="text-base font-medium">
        <ShimmerText>{text}…</ShimmerText>
      </p>
    </div>
  );
}
