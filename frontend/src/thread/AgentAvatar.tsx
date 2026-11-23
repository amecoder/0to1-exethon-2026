import {
  ClipboardList,
  CodeXml,
  Compass,
  Palette,
  Search,
  ShieldCheck,
  Store,
  UserRound,
  Users,
  Workflow,
  type LucideIcon,
} from "lucide-react";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import { cn } from "@/lib/utils";

// One icon per role, so the team reads at a glance without a legend.
export const AGENT_ICON: Record<string, LucideIcon> = {
  coordinator: Workflow,
  fde_lead: Compass,
  researcher: Search,
  pm: ClipboardList,
  designer: Palette,
  developer: CodeXml,
  qa: ShieldCheck,
  consumer: UserRound,
  client: Store,
};

export function AgentAvatar({ id, active, size = "md", className }: {
  id: string;
  active?: boolean;
  size?: "sm" | "md";
  className?: string;
}) {
  const Icon = AGENT_ICON[id] ?? Users;
  return (
    <Avatar
      className={cn(
        size === "sm" ? "size-6" : "size-8",
        "ring-2 ring-background transition-transform duration-300",
        !active && "shadow-[inset_0_0_0_1px_rgb(255_255_255/0.1)]",
        active && "z-10 scale-110 overflow-visible animate-breathe",
        className,
      )}
    >
      <AvatarFallback
        className={cn(
          active
            ? "bg-[radial-gradient(circle_at_32%_28%,#d9fbff_0%,#7fe3f0_38%,#6553f5_100%)] text-[#071341]"
            : "bg-[radial-gradient(circle_at_32%_28%,rgb(255_255_255/0.14),rgb(255_255_255/0.04))] text-soft",
        )}
        aria-hidden="true"
      >
        <Icon className={size === "sm" ? "size-3" : "size-3.5"} strokeWidth={1.75} />
      </AvatarFallback>
    </Avatar>
  );
}
