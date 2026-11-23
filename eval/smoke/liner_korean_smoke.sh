#!/usr/bin/env bash
# Korean smoke test for Liner Model API candidates. Pass criteria are fixed here BEFORE the first run.
#
#   C1 format : all 10 calls return parseable JSON with the required fields
#   C2 fidelity: >= 90% of extracted source_quote strings appear verbatim in the memo
#   C3 plain  : all 5 question cards contain none of the banned jargon terms and have 2-4 options
#   C4 latency: median call time <= 15 s
#
# Decision rule: liner-mark-1.3 passing C1-C4 becomes the default model; otherwise the first passing
# router in order claude -> gpt -> gemini. If none pass, report and do not pick.
#
# Usage: eval/smoke/liner_korean_smoke.sh            (reads LINER_API_KEY from env or .env)
#        LINER_MODELS="liner-mark-1.3" eval/smoke/liner_korean_smoke.sh
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
if [[ -z "${LINER_API_KEY:-}" && -f "$ROOT/.env" ]]; then
  set -a; source "$ROOT/.env"; set +a
fi
: "${LINER_API_KEY:?LINER_API_KEY is not set. Put it in .env (see README).}"

URL="https://platform.liner.com/api/v1/chat/completions"
MODELS="${LINER_MODELS:-liner-mark-1.3 liner-claude-router liner-gpt-router liner-gemini-router}"
MEMOS=("$ROOT/examples/flower-subscription/request_memo.md" "$ROOT"/eval/smoke/memos/*.md)
BANNED='인수 조건|요구사항 ID|REQ-|스키마|API|엔드포인트|유효성|프로세스|파라미터|acceptance|Given|When|Then'
OUT_DIR="${RESULTS_DIR:-$ROOT/eval/results}"
mkdir -p "$OUT_DIR"
OUT="$OUT_DIR/smoke-$(date +%Y%m%d-%H%M%S).jsonl"

EXTRACT_SCHEMA='{"name":"requirement_candidates","strict":true,"schema":{"type":"object","additionalProperties":false,"required":["items"],"properties":{"items":{"type":"array","items":{"type":"object","additionalProperties":false,"required":["text","source_quote"],"properties":{"text":{"type":"string"},"source_quote":{"type":"string"}}}}}}}'
CARD_SCHEMA='{"name":"question_card","strict":true,"schema":{"type":"object","additionalProperties":false,"required":["question","why","options"],"properties":{"question":{"type":"string"},"why":{"type":"string"},"options":{"type":"array","items":{"type":"string"}}}}}'
EXTRACT_PROMPT='다음은 가게 사장님이 개발자에게 보낸 요청 메모다. 요구사항 후보를 모두 뽑아라. 각 후보의 source_quote 에는 메모 원문에서 그 근거가 된 부분을 한 글자도 바꾸지 말고 그대로 옮겨라. JSON 으로만 답하라.'
CARD_PROMPT='다음 요청 메모에서 개발자가 만들기 전에 꼭 확인해야 할 빠진 점 하나를 골라, 사장님에게 물을 질문 카드 하나를 만들어라. 사장님은 개발 용어를 모른다. 쉬운 말로, 고를 수 있는 선택지 2~4개를 주고, why 에는 왜 묻는지 한 문장을 써라. "잘 모르겠어요" 는 화면이 따로 붙이므로 선택지에 넣지 마라. JSON 으로만 답하라.'

call() { # model, system_prompt, memo_text, schema -> prints "<http_code> <seconds>" and writes body to $BODY
  local payload
  payload=$(jq -n --arg m "$1" --arg s "$2" --arg u "$3" --argjson js "$4" \
    '{model:$m, messages:[{role:"system",content:$s},{role:"user",content:$u}], response_format:{type:"json_schema", json_schema:$js}}')
  curl -sS -o "$BODY" -w '%{http_code} %{time_total}\n' -X POST "$URL" \
    -H "Authorization: Bearer $LINER_API_KEY" -H 'Content-Type: application/json' \
    --max-time 120 -d "$payload" || echo "000 120"
}

BODY="$(mktemp)"; trap 'rm -f "$BODY"' EXIT
for model in $MODELS; do
  for memo_file in "${MEMOS[@]}"; do
    memo=$(cat "$memo_file")
    for task in extract card; do
      if [[ $task == extract ]]; then read -r code secs < <(call "$model" "$EXTRACT_PROMPT" "$memo" "$EXTRACT_SCHEMA")
      else read -r code secs < <(call "$model" "$CARD_PROMPT" "$memo" "$CARD_SCHEMA"); fi
      content=$(jq -r '.choices[0].message.content // empty' "$BODY" 2>/dev/null || true)
      jq -nc --arg model "$model" --arg memo "$(basename "$memo_file")" --arg task "$task" \
        --arg code "$code" --argjson secs "${secs:-0}" --arg content "$content" \
        --arg memo_text "$memo" --arg banned "$BANNED" --arg err "$(head -c 300 "$BODY")" '
        ($content | try fromjson catch null) as $j
        | {model:$model, memo:$memo, task:$task, http:$code, secs:$secs,
           format_ok: (if $task == "extract" then ($j.items | type) == "array" and ($j.items | length) > 0
                       else ($j.question | type) == "string" and ($j.options | type) == "array" end),
           quotes_total: (if $task == "extract" then ($j.items // [] | length) else null end),
           quotes_verbatim: (if $task == "extract" then ([$j.items // [] | .[] | select(.source_quote as $q | $memo_text | contains($q))] | length) else null end),
           plain_ok: (if $task == "card" then (($j.options // [] | length) as $n | $n >= 2 and $n <= 4)
                      and (([$j.question, $j.why] + ($j.options // []) | map(. // "") | join(" ")) | test($banned) | not) else null end),
           error: (if $code == "200" then null else $err end),
           output: $j}' >> "$OUT"
      echo "  $model  $(basename "$memo_file")  $task  http=$code  ${secs}s"
    done
  done
done

echo
echo "results: $OUT"
jq -rs '
  group_by(.model)[] | . as $rows | $rows[0].model as $m
  | ([$rows[] | select(.task == "extract")]) as $ex | ([$rows[] | select(.task == "card")]) as $cd
  | ([$rows[].secs] | sort | .[(length / 2 | floor)]) as $median
  | (([$ex[].quotes_verbatim] | add // 0) / ([$ex[].quotes_total] | add // 0 | if . == 0 then 1 else . end)) as $fid
  | {c1: (([$rows[] | select(.format_ok)] | length) == ($rows | length)),
     c2: ($fid >= 0.9), c3: (([$cd[] | select(.plain_ok)] | length) == ($cd | length)), c4: ($median <= 15)}
  | "\($m): C1 format=\(.c1)  C2 fidelity=\(.c2) (\($fid * 100 | floor)%)  C3 plain=\(.c3)  C4 median=\($median)s \(.c4)  => \(if .c1 and .c2 and .c3 and .c4 then "PASS" else "FAIL" end)"
' "$OUT"
