// 11-22 「기본값 목록 한 화면」 (app/team_defaults.py): only the lines the client actually changed go to the server;
// every other default is kept as the team set it.
export interface TeamDefault {
  id: string;
  title: string;
  team_default: string;
  team_why: string;
  requirement_refs: string[];
}

export function changedDefaults(defaults: readonly TeamDefault[], edits: Readonly<Record<string, string>>): Record<string, string> {
  const out: Record<string, string> = {};
  for (const d of defaults) {
    const edit = edits[d.id]?.trim();
    if (edit && edit !== d.team_default) out[d.id] = edit;
  }
  return out;
}
