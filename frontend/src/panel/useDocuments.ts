import { useEffect, useState } from "react";
import { api, type DocId, type DocView, type Project } from "../api";

// A document has content once its owner agent has written its bundle.
export const DOC_READY: Record<DocId, (source: Project["source"]) => boolean> = {
  brd: (s) => ((s.brd as unknown[] | undefined)?.length ?? 0) > 0,
  prd: (s) => s.requirements.length > 0,
  screens: (s) => ((s.screens as unknown[] | undefined)?.length ?? 0) > 0,
  tests: (s) => ((s.tests as unknown[] | undefined)?.length ?? 0) > 0,
};

// Real mode: fetch the four documents, again whenever the event log grows. Demo mode passes `given`
// (the replay endpoint already built them) and nothing is fetched.
export function useDocuments(project: Project, given?: Record<DocId, DocView> | null): Record<DocId, DocView> | null {
  const [docs, setDocs] = useState<Record<DocId, DocView> | null>(null);
  const version = project.source.events.length;
  const enabled = given === undefined && Object.values(DOC_READY).some((ready) => ready(project.source));
  useEffect(() => {
    if (!enabled) return;
    let alive = true;
    api
      .documents(project.id)
      .then((d) => alive && setDocs(d))
      .catch(() => alive && setDocs(null));
    return () => {
      alive = false;
    };
  }, [project.id, version, enabled]);
  return given === undefined ? docs : given;
}
