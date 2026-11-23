import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { findTerm } from "../lib/terms";

// 11-22 user decision: the screen says the technical word; a dotted underline opens the plain explanation.
// A word the glossary does not have is shown as plain text.
export function Term({ name, children }: { name: string; children?: React.ReactNode }) {
  const term = findTerm(name);
  const label = children ?? name;
  if (!term) return <>{label}</>;
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <span tabIndex={0} className="cursor-help underline decoration-dotted decoration-1 underline-offset-4 outline-none focus-visible:ring-[3px] focus-visible:ring-primary-ring">
          {label}
        </span>
      </TooltipTrigger>
      <TooltipContent className="max-w-sm">
        <p className="font-semibold">{term.term}</p>
        <p className="mt-1 break-keep">{term.plain}</p>
        <p className="mt-1 break-keep text-muted-foreground">예: {term.example}</p>
      </TooltipContent>
    </Tooltip>
  );
}
