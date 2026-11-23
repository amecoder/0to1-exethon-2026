import { Badge } from "@/components/ui/badge";

const VARIANT = { 확정: "success", 가정: "warning", 미결: "secondary", 미확인: "danger", 확인: "success" } as const;
const MEANING: Record<string, string> = {
  확정: "원문이나 고른 답에 근거가 있어요",
  가정: "근거가 없어 기본값으로 채웠어요",
  미결: "아직 답이 없어요",
  미확인: "원문·출처와 글자가 그대로 맞는지 아직 확인하지 못했어요",
  확인: "원문·출처와 맞춰 봤어요",
};

// 확정 / 가정 / 미결 / 미확인 as a small chip; the meaning is in the title for hover.
export function StatusChip({ status }: { status: string }) {
  const variant = VARIANT[status as keyof typeof VARIANT] ?? "secondary";
  return (
    <Badge variant={variant} title={MEANING[status]}>
      {status}
    </Badge>
  );
}
