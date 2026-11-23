from __future__ import annotations
"""S2 problem recognition: FDE lead drafts problem/scope, researcher gathers evidence via Liner AI Search
(falling back to Web Search). G1 is the verbatim quote check; a Liner Decisions `noul` per checked sentence
then asks whether the quoted evidence supports it — a low probability adds a 참고 note, never a block."""

from collections.abc import Mapping
from typing import Any

from app.config import LinerKeyMissingError
from app.decisions import SUPPORT_MIN, read_noul, support_questions
from app.guardrails import verify_quote
from app.liner import LinerAPIError, LinerConfigError
from app.naming import clean_name
from app.schemas import PROBLEM_SCOPE, RESEARCH_EVIDENCE
from app.stage_common import MAX_RESEARCH_QUERIES, StageContext, citation_texts, str_list
from app.placement import PROBLEM_SCOPE_SERVICES, TASK_FDE_PLACEMENT, check_placement, services
from app.systems import FITS, TASK_FDE_NO_SYSTEMS, TASK_FDE_SYSTEMS

# Stage assignments (coordinator → agent). Generic on purpose: no hints about what the memo lacks.
TASK_FDE = (
    "단계 S2 문제 인식: 발주사 원문(sources)만 근거로 문제 진술(누가 who, 무엇이 불편한지 pain, "
    "무엇이 되면 완료인지 done), 범위(하는 것 scope_in / 하지 않는 것 scope_out), 해석이 갈리는 표현"
    "(interpretations)을 정리하라. 사실 문장(claims)을 포함한 모든 항목에 근거 원문 ID(refs)와 그 원문에서 "
    "한 글자도 바꾸지 않고 옮긴 인용문(quote)을 붙여라. 업계 관행·규정 근거가 필요하면 리서처에게 물을 "
    f"검색 질문을 research_requests 에 최대 {MAX_RESEARCH_QUERIES}개 적어라. 바퀴를 다시 만들지 않도록, 그중 하나는 "
    "원문이 바라는 일을 이미 해 주는 제품·서비스가 있는지 묻는 질문으로 하라. 원문이 만들려는 것을 부를 짧은 이름을 "
    "service_name 에 적어라(20자 이내 명사구. 원문에 가게·서비스 이름이 있으면 그 말을 쓰고, 없는 고유명사는 지어내지 않는다)."
)
TASK_RESEARCH = (
    "FDE 리드의 질문으로 Liner 검색을 했다. 추가 입력의 search_results 에서 근거가 되는 문장을 snippet(출처 문단) 에서 "
    "한 글자도 바꾸지 않고 quote 에 옮기고, 그 결과의 result_id 와 근거가 말하는 사실(fact)을 한 문장으로 "
    "적어라. 검색 결과에 원문이 바라는 일을 이미 해 주는 제품·서비스가 나오면 alternatives 에 제품 이름(name), 그 제품으로 "
    "되는 것(covers), 원문이 바라는데 안 되거나 확인되지 않은 것(lacks), 근거 result_id 와 snippet 에서 그대로 옮긴 "
    "인용문(quote)을 적어라. 추가 입력의 known_products 에 있는 제품과 같은 제품이면 name 은 그 이름을 한 글자도 바꾸지 "
    "말고 쓴다. 근거를 못 찾은 질문은 not_found 에 적어라."
)
CLAIM_GROUPS = ("claims", "scope_in", "scope_out", "interpretations")


def run_s2(ctx: StageContext) -> None:
    task = TASK_FDE + (TASK_FDE_SYSTEMS if ctx.ws.items("systems") else TASK_FDE_NO_SYSTEMS)
    built = bool(services(ctx.ws.items("systems")))  # a service made with 0to1: did the memo name it?
    task, schema = (task + TASK_FDE_PLACEMENT, PROBLEM_SCOPE_SERVICES) if built else (task, PROBLEM_SCOPE)
    ctx.bus.send("coordinator", "fde_lead", task)
    out = ctx.runner.ask("fde_lead", task, "problem_scope", schema, ctx.feedback_extra())
    name = clean_name(str(out.get("service_name", "")))
    if name and (ctx.ws.meta.get("name") or {}).get("by") != "client":  # the client's own name always stays
        ctx.ws.set_name(name, "fde_lead")
    checked = {group: check_claims(ctx, out.get(group, [])) for group in CLAIM_GROUPS}
    ctx.ws.write("fde_lead", "problem_statement", {
        "id": "PS-01", "who": str(out.get("who", "")), "pain": str(out.get("pain", "")),
        "done": str(out.get("done", "")), "claims": checked["claims"],
        "interpretations": checked["interpretations"],
    })
    ctx.ws.write("fde_lead", "scope", {"id": "SCOPE-01", "in": checked["scope_in"], "out": checked["scope_out"],
                                       "systems": check_fits(ctx, out.get("system_fit")),
                                       **({"placement": check_placement(ctx, out.get("placement"))} if built else {})})
    requests = str_list(out.get("research_requests"))[:MAX_RESEARCH_QUERIES]
    if requests:
        ctx.bus.send("fde_lead", "researcher", "근거 요청: " + " / ".join(requests))
        found = run_research(ctx, requests)
        ctx.bus.send("researcher", "fde_lead", f"출처 {found}건 저장")
    check_support(ctx)
    unverified = sum(c["status"] == "미확인" for group in checked.values() for c in group)
    ctx.bus.send("fde_lead", "coordinator", f"문제 진술·범위 정리 완료 (미확인 {unverified}건)")


def check_claims(ctx: StageContext, claims: Any) -> list[dict[str, Any]]:
    """G1: each sentence needs a stored citation whose text contains the quote verbatim."""
    texts = citation_texts(ctx.ws)
    checked = []
    for claim in claims if isinstance(claims, list) else []:
        if not isinstance(claim, Mapping):
            continue
        refs, quote = str_list(claim.get("refs")), str(claim.get("quote", ""))
        ok = verify_quote(quote, refs, texts)
        item = {"text": str(claim.get("text", "")), "refs": refs, "quote": quote, "status": "확인" if ok else "미확인"}
        if not ok:
            ctx.ws.guardrail("G1", "flagged", "인용문이 인용한 원문·출처에 그대로 없습니다", actor="fde_lead",
                             text=item["text"])
        checked.append(item)
    return checked


def check_fits(ctx: StageContext, raw: Any) -> list[dict[str, Any]]:
    """「우리 시스템」 matches: only listed systems; the quote must be in the cited memo sentence (G1)."""
    systems = {s["id"]: s for s in ctx.ws.items("systems")}
    texts = citation_texts(ctx.ws)
    fits = []
    for item in raw if isinstance(raw, list) else []:
        if not isinstance(item, Mapping):
            continue
        ref = str(item.get("system_ref", ""))
        if ref not in systems or item.get("fit") not in FITS:
            ctx.ws.guardrail("G1", "flagged", "목록에 없는 시스템이나 방식은 뺐습니다", actor="fde_lead", system=ref)
            continue
        refs, quote = str_list(item.get("refs")), str(item.get("quote", ""))
        ok = verify_quote(quote, refs, texts)
        if not ok:
            ctx.ws.guardrail("G1", "flagged", "시스템 활용 근거 인용문이 원문에 그대로 없습니다", actor="fde_lead", system=ref)
        fits.append({"system_ref": ref, "name": systems[ref]["name"], "fit": item["fit"],
                     "what": str(item.get("what", "")), "refs": refs, "quote": quote, "status": "확인" if ok else "미확인"})
    return fits


def run_research(ctx: StageContext, queries: list[str]) -> int:
    results = []
    for qi, query in enumerate(queries, start=1):
        hits = ctx.runner.research("researcher", query)
        results.append({"query": query, "results": [
            {"result_id": f"R{qi}-{hi}", **hit} for hi, hit in enumerate(hits, start=1)]})
    by_id = {r["result_id"]: (group["query"], r) for group in results for r in group["results"]}
    if not by_id:
        return 0
    known = [a["name"] for a in ctx.ws.items("alternatives")]
    out = ctx.runner.ask("researcher", TASK_RESEARCH, "research_evidence", RESEARCH_EVIDENCE,
                         {"search_results": results, **({"known_products": known} if known else {})})
    stored, ev_ids = 0, {}
    for item in out.get("evidence", []) if isinstance(out.get("evidence"), list) else []:
        if isinstance(item, Mapping):
            ev_ids[str(item.get("result_id"))] = store_evidence(ctx, item, by_id)
            stored += 1
    store_alternatives(ctx, out.get("alternatives"), by_id, ev_ids)
    return stored


def store_alternatives(ctx: StageContext, raw: Any, by_id: Mapping[str, Any], ev_ids: Mapping[str, str]) -> None:
    """Existing products that already do what the memo asks (build-or-buy). G1: the quote must be in the hit.
    A later run (CP1 rework) replaces an entry with the same name and keeps the others."""
    found: dict[str, dict[str, Any]] = {a["name"]: a for a in ctx.ws.items("alternatives")}
    for item in raw if isinstance(raw, list) else []:
        name = str(item.get("name", "")).strip() if isinstance(item, Mapping) else ""
        if not name:
            continue
        rid = str(item.get("result_id", ""))
        _, hit = by_id.get(rid, ("", {"url": "", "snippet": ""}))
        raw_text = "\n".join(t for t in (hit.get("snippet", ""), hit.get("description", "")) if t)
        quote = str(item.get("quote", ""))
        ok = verify_quote(quote, ["hit"], {"hit": raw_text})
        if not ok:
            ctx.ws.guardrail("G1", "flagged", "기존 제품 근거 인용문이 검색 결과 원문에 그대로 없습니다", actor="researcher")
        old = found.get(name, {})
        found[name] = {"id": old.get("id") or f"ALT-{len(found) + 1:02d}", "name": name,
                       "covers": str(item.get("covers", "")), "lacks": str(item.get("lacks", "")),
                       "url": hit.get("url", ""), "quote": quote,
                       "evidence_refs": [ev_ids[rid]] if rid in ev_ids else [], "status": "확인" if ok else "미확인"}
    if found:
        ctx.ws.write_all("researcher", "alternatives", list(found.values()))
        ctx.bus.send("researcher", "fde_lead", "이미 있는 제품: " + ", ".join(found))


def store_evidence(ctx: StageContext, item: Mapping[str, Any], by_id: Mapping[str, Any]) -> str:
    """The AI Search chunk (content + description) is kept as raw_snippet, so G1 matches quotes against it."""
    query, hit = by_id.get(str(item.get("result_id")), ("", {"url": "", "title": "", "snippet": ""}))
    quote = str(item.get("quote", ""))
    raw = "\n".join(dict.fromkeys(t for t in (hit["snippet"], hit.get("description", "")) if t))
    ok = verify_quote(quote, ["hit"], {"hit": raw})
    if not ok:
        ctx.ws.guardrail("G1", "flagged", "인용문이 검색 결과 원문에 그대로 없습니다", actor="researcher")
    extra = {k: hit[k] for k in ("date", "chunk_id", "via") if hit.get(k)}
    ev_id = ctx.ws.next_id("evidence", "EV")
    ctx.ws.write("researcher", "evidence", {
        "id": ev_id, "query": query, "url": hit["url"], "title": hit["title"],
        "quote": quote, "raw_snippet": raw, "fact": str(item.get("fact", "")),
        "status": "확인" if ok else "미확인", **extra,
    })
    return ev_id


SUPPORT_LOW_NOTE = "참고: 인용한 근거가 이 문장을 뒷받침하는지 판정 확률이 낮아요({p:.2f}) — 한 번 더 읽어 보세요"


def _checked_sentences(ctx: StageContext) -> list[tuple[str, str, str, str, str]]:
    """(key, kind, location, sentence, quote) for every G1-확인 sentence of S2."""
    out = []
    ps = (ctx.ws.items("problem_statement") or [{}])[0]
    scope = (ctx.ws.items("scope") or [{}])[0]
    groups = (("problem_statement", "claims", ps), ("problem_statement", "interpretations", ps),
              ("scope", "in", scope), ("scope", "out", scope))
    for kind, group, holder in groups:
        for i, claim in enumerate(holder.get(group, [])):
            if claim.get("status") == "확인":
                out.append((f"s{len(out) + 1}", kind, f"{group}.{i}", claim["text"], claim["quote"]))
    for ev in ctx.ws.items("evidence"):
        if ev.get("status") == "확인":
            out.append((f"s{len(out) + 1}", "evidence", ev["id"], ev.get("fact", ""), ev["quote"]))
    return out


def check_support(ctx: StageContext) -> None:
    """G1 secondary (Decisions `noul`, one call for all sentences). Fail-open: errors only leave a note."""
    sentences = [s for s in _checked_sentences(ctx) if s[3].strip() and s[4].strip()]
    if not sentences:
        return
    try:
        body = ctx.runner.decide("fde_lead", "g1_support", {"단계": "S2 문제 인식"},
                                 support_questions([(k, text, quote) for k, _, _, text, quote in sentences]))
    except (LinerAPIError, LinerConfigError, LinerKeyMissingError) as exc:
        ctx.ws.emit("check_result", "coordinator", {"check": "g1_support", "outcome": "skipped", "items": [],
                                                    "details": [f"근거 뒷받침 판정을 못 했어요: {exc}"]})
        return
    answers = body.get("answers") if isinstance(body.get("answers"), Mapping) else {}
    scores = {key: read_noul(answers.get(key)) for key, *_ in sentences}
    low = [(s, scores[s[0]]) for s in sentences if scores[s[0]] is not None and scores[s[0]] < SUPPORT_MIN]
    _store_support(ctx, sentences, scores)
    ctx.ws.emit("check_result", "coordinator", {
        "check": "g1_support", "outcome": "flagged" if low else "passed",
        "items": [s[2] for s, _ in low], "details": [f"「{s[3][:40]}」 뒷받침 {p:.2f}" for s, p in low]})


def _store_support(ctx: StageContext, sentences: list[tuple[str, str, str, str, str]],
                   scores: Mapping[str, float | None]) -> None:
    def mark(item: dict[str, Any], key: str) -> dict[str, Any]:
        p = scores.get(key)
        if p is None:
            return item
        return {**item, "support": round(p, 4), **({"support_note": SUPPORT_LOW_NOTE.format(p=p)} if p < SUPPORT_MIN else {})}

    ps = dict((ctx.ws.items("problem_statement") or [{}])[0])
    scope = dict((ctx.ws.items("scope") or [{}])[0])
    holders = {"problem_statement": ps, "scope": scope}
    for key, kind, loc, *_ in sentences:
        if kind == "evidence":
            ctx.ws.write("researcher", "evidence", mark(ctx.ws.get("evidence", loc), key))
            continue
        group, index = loc.split(".")
        holder = holders[kind]
        items = list(holder[group])
        items[int(index)] = mark(items[int(index)], key)
        holder[group] = items
    if ps.get("id"):
        ctx.ws.write("fde_lead", "problem_statement", ps)
    if scope.get("id"):
        ctx.ws.write("fde_lead", "scope", scope)
