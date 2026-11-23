#!/usr/bin/env bash
# Validate that the golden sets are internally consistent before they are used for scoring.
#   1. fixture: every referenced REQ/SCR/TC id exists, each TC belongs to exactly one REQ
#   2. change_cases: 20 unique cases, target exists, expected impact == impact_rule recomputed from fixture
#   3. seeded_defects: 10 unique defects, valid types, every quote appears verbatim in the memo
#   4. complaint_cases: 20 unique cases, 10 violation + 10 new_change, confirmed REQ ids exist, text not empty
# Usage: eval/validate_golden.sh [repo_root]   (exit 0 = consistent)
set -euo pipefail

ROOT="${1:-$(cd "$(dirname "$0")/.." && pwd)}"
FIXTURE="$ROOT/examples/flower-subscription/requirements_fixture.json"
CHANGES="$ROOT/eval/golden/change_cases.json"
DEFECTS="$ROOT/eval/golden/seeded_defects.json"
MEMO="$ROOT/examples/flower-subscription/request_memo.md"
COMPLAINTS="$ROOT/eval/golden/complaint_cases.json"

for f in "$FIXTURE" "$CHANGES" "$DEFECTS" "$MEMO" "$COMPLAINTS"; do
  [[ -f "$f" ]] || { echo "FAIL missing file: $f" >&2; exit 2; }
done

errors=$(jq -r --slurpfile fx "$FIXTURE" --rawfile memo "$MEMO" --slurpfile df "$DEFECTS" --slurpfile cc "$COMPLAINTS" '
  ($fx[0]) as $F
  | ($F.requirements) as $R
  | ([$R[].id]) as $rids
  | ([$F.screens[].id]) as $sids
  | ([$F.tests[].id]) as $tids

  # transitive closure over reverse depends_on edges
  | def close: . as $s
      | ([$s[] as $t | $R[] | select(.depends_on | index($t)) | .id] + $s | unique) as $n
      | if ($n | length) == ($s | length) then $s else ($n | close) end;

  [
    # --- 1. fixture integrity
    ($R[] | .id as $id | .depends_on[] | select(. as $x | ($rids | index($x)) == null)
      | "fixture: \($id) depends_on unknown \(.)"),
    ($R[] | .id as $id | .screens[] | select(. as $x | ($sids | index($x)) == null)
      | "fixture: \($id) links unknown screen \(.)"),
    ($R[] | .id as $id | .tests[] | select(. as $x | ($tids | index($x)) == null)
      | "fixture: \($id) links unknown test \(.)"),
    ($tids[] as $t | ([$R[] | select(.tests | index($t))] | length) as $n
      | select($n != 1) | "fixture: \($t) is linked from \($n) requirements (expected 1)"),

    # --- 2. change cases
    (.cases | length | select(. != 20) | "change_cases: \(.) cases (expected 20)"),
    ([.cases[].id] | group_by(.) | map(select(length > 1) | .[0])[] | "change_cases: duplicate id \(.)"),
    (.cases[] | . as $c
      | if ($rids | index($c.target)) | not then "change_cases: \($c.id) unknown target \($c.target)"
        else
          ([$c.target] | close) as $reqs
          | ([$R[] | select(.id as $i | $reqs | index($i)) | .screens[]] | unique) as $scr
          | ([$R[] | select(.id as $i | $reqs | index($i)) | .tests[]] | unique) as $tc
          | (if ($c.expected.requirements | sort) != $reqs then "change_cases: \($c.id) requirements \($c.expected.requirements | sort) != rule \($reqs)" else empty end),
            (if ($c.expected.screens | sort) != $scr then "change_cases: \($c.id) screens \($c.expected.screens | sort) != rule \($scr)" else empty end),
            (if ($c.expected.tests | sort) != $tc then "change_cases: \($c.id) tests \($c.expected.tests | sort) != rule \($tc)" else empty end)
        end),

    # --- 3. seeded defects
    ($df[0] | .defects | length | select(. != 10) | "seeded_defects: \(.) defects (expected 10)"),
    ($df[0] | [.defects[].id] | group_by(.) | map(select(length > 1) | .[0])[] | "seeded_defects: duplicate id \(.)"),
    ($df[0] | (.types | keys) as $types | .defects[]
      | select(.type as $t | ($types | index($t)) | not) | "seeded_defects: \(.id) unknown type \(.type)"),
    ($df[0] | .defects[] | .id as $id | .quotes[]
      | select(. as $q | ($memo | contains($q)) | not) | "seeded_defects: \($id) quote not in memo: \(.)"),

    # --- 4. complaint cases
    ($cc[0] | .cases | length | select(. != 20) | "complaint_cases: \(.) cases (expected 20)"),
    ($cc[0] | [.cases[].id] | group_by(.) | map(select(length > 1) | .[0])[] | "complaint_cases: duplicate id \(.)"),
    ($cc[0] | [.cases[] | select(.expected == "violation")] | length | select(. != 10)
      | "complaint_cases: \(.) violation cases (expected 10)"),
    ($cc[0] | [.cases[] | select(.expected == "new_change")] | length | select(. != 10)
      | "complaint_cases: \(.) new_change cases (expected 10)"),
    ($cc[0] | .cases[] | select((.expected == "violation" or .expected == "new_change") | not)
      | "complaint_cases: \(.id) unknown label \(.expected)"),
    ($cc[0] | .cases[] | select((.complaint // "") | length == 0) | "complaint_cases: \(.id) empty complaint"),
    ($cc[0] | .cases[] | .id as $id | select((.confirmed | length) == 0) | "complaint_cases: \($id) no confirmed requirement"),
    ($cc[0] | .cases[] | .id as $id | .confirmed[] | select(. as $x | ($rids | index($x)) == null)
      | "complaint_cases: \($id) unknown requirement \(.)")
  ] | .[]
' "$CHANGES")

if [[ -n "$errors" ]]; then
  echo "$errors" | sed 's/^/FAIL /'
  echo "golden sets: INCONSISTENT ($(echo "$errors" | wc -l | tr -d ' ') problems)"
  exit 1
fi

jq -r '"change_cases: \(.cases | length) cases, \([.cases[].target] | unique | length) distinct targets"' "$CHANGES"
jq -r '"seeded_defects: \(.defects | length) defects — " + ([.defects | group_by(.type)[] | "\(.[0].type)=\(length)"] | join(", "))' "$DEFECTS"
jq -r '"complaint_cases: \(.cases | length) cases — " + ([.cases | group_by(.expected)[] | "\(.[0].expected)=\(length)"] | join(", "))' "$COMPLAINTS"
echo "golden sets: OK"
