import { useEffect, useState } from "react";
import { api, type Team } from "../api";

const BASE_NAMES: Record<string, string> = { client: "발주사", system: "시스템" };

export interface TeamInfo {
  team: Team | null;
  label: (id: string) => string;
  error: string | null;
}

// The default team definition and display names, fetched once per mount.
export function useTeam(): TeamInfo {
  const [team, setTeam] = useState<Team | null>(null);
  const [names, setNames] = useState<Record<string, string>>(BASE_NAMES);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    let alive = true;
    Promise.all([api.team("default"), api.agents()])
      .then(([t, agents]) => {
        if (!alive) return;
        setTeam(t);
        setNames({ ...BASE_NAMES, ...Object.fromEntries(agents.map((a) => [a.id, a.name])) });
      })
      .catch((e: unknown) => alive && setError(e instanceof Error ? e.message : String(e)));
    return () => {
      alive = false;
    };
  }, []);
  return { team, label: (id: string) => names[id] ?? id, error };
}
