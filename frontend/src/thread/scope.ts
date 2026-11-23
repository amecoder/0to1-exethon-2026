// G8 scope card (11-22): while the client picks screens, say right there which features lose their screen,
// instead of finding them later as 빈칸 at CP3. Same rule as the server (orchestrator.narrow_scope).
type ScopeScreen = { id: string; requirement_refs: string[] };

export function droppedFeatures(screens: ScopeScreen[], keep: string[]): string[] {
  const kept = new Set(screens.filter((s) => keep.includes(s.id)).flatMap((s) => s.requirement_refs));
  const dropped = screens.filter((s) => !keep.includes(s.id)).flatMap((s) => s.requirement_refs);
  return [...new Set(dropped.filter((r) => !kept.has(r)))].sort();
}
