// Role view (발주사 보기 / 팀 보기): same data, different density (FR-09, plan principle 3).
import { createContext, useContext, type ReactNode } from "react";
import type { View } from "../lib/labels";
import { RefLink } from "./refs";

const ViewContext = createContext<View>("team");

export function ViewProvider({ view, children }: { view: View; children: ReactNode }) {
  return <ViewContext.Provider value={view}>{children}</ViewContext.Provider>;
}

export function useView(): View {
  return useContext(ViewContext);
}

// Item titles by ID (requirements, screens, tests) so client-facing text can name items instead of IDs.
const TitlesContext = createContext<Record<string, string>>({});

export function TitlesProvider({ titles, children }: { titles: Record<string, string>; children: ReactNode }) {
  return <TitlesContext.Provider value={titles}>{children}</TitlesContext.Provider>;
}

export function useTitles(): Record<string, string> {
  return useContext(TitlesContext);
}

// An internal ID: a small code chip in the team view (a link that opens what it is); the client view hides IDs.
export function RefId({ id }: { id: string | string[] }) {
  const view = useView();
  const ids = (Array.isArray(id) ? id : id.split(/\s*,\s*/)).filter(Boolean);
  if (ids.length === 0 || view !== "team") return null;
  return (
    <span className="inline-flex flex-wrap items-center gap-0.5 align-middle">
      {ids.map((one) => (
        <RefLink key={one} id={one} />
      ))}
    </span>
  );
}
