import { useEffect, useRef, useState } from "react";
import type { Project } from "../api";
import { GOTO_MESSAGE, osNoticeToShow, pendingNotice } from "../panel/notice";

const supported = () => typeof window !== "undefined" && "Notification" in window;

// Operating-system notice when something new waits for the client while this window is out of sight.
// Clicking it brings the window forward and scrolls to the card (same GOTO message the pop-out uses).
export function useOsNotice(project: Project): { permission: NotificationPermission | null; enable: () => void } {
  const [permission, setPermission] = useState<NotificationPermission | null>(supported() ? Notification.permission : null);
  const last = useRef<string | null | undefined>(undefined);
  const notice = pendingNotice(project);
  const key = notice?.key ?? null;

  useEffect(() => {
    const prev = last.current;
    last.current = key;
    if (!supported()) return;
    const show = osNoticeToShow(prev, notice, { hidden: document.hidden, permission: Notification.permission });
    if (!show) return;
    const n = new Notification(`0to1 · ${project.name}`, { body: show.text, tag: `0to1-${project.id}` });
    n.onclick = () => {
      window.focus();
      window.postMessage({ type: GOTO_MESSAGE, target: show.target }, window.location.origin);
      n.close();
    };
    // notice is derived from key; re-running on the same key would only repeat the check
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key, project.id, project.name]);

  const enable = () => {
    if (!supported()) return;
    void Notification.requestPermission().then(setPermission);
  };
  return { permission, enable };
}
