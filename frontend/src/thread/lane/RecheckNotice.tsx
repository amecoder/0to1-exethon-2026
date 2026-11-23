import type { Pipeline, Recheck } from "../../api";
import { Notice, NoticeList } from "@/components/ui/notice";
import { recheckView } from "./model";

// Shown while a CP5 change is being reworked: why the zip is locked and what the client does next.
export default function RecheckNotice({ recheck, pipeline }: { recheck: Recheck; pipeline: Pipeline | undefined }) {
  const view = recheckView(recheck, pipeline);
  return (
    <Notice kind="reason" tag="내려받기 잠김" title={view.title}>
      <NoticeList items={[`다시 만드는 것: ${view.redo.join(" · ")}`, `다음 단계: ${view.next}`]} />
    </Notice>
  );
}
