import type { FlowChart, Swimlane } from "../api";

export type FlowView = "lanes" | "liner";

// Which flow charts exist, in switch order. The role swimlane comes first (the client's default view);
// the Liner Visualization chart stays as the second option.
export function flowViews(lanes: Swimlane | undefined, flow: FlowChart | undefined): FlowView[] {
  const views: FlowView[] = [];
  if (lanes && lanes.steps.length > 0) views.push("lanes");
  if (flow) views.push("liner");
  return views;
}

// The picked view when it still exists, else the first one available.
export function shownView(views: FlowView[], picked: FlowView | null): FlowView | null {
  return picked && views.includes(picked) ? picked : (views[0] ?? null);
}
