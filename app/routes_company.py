from __future__ import annotations
"""회사 작업 공간 API: list/create companies, read/save a company's shared material (G3 before saving)."""

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.company import NAME_MAX, NOTES_MAX, company_items
from app.guardrails import sensitive_labels
from app.store import ProjectStore
from app.systems import TEXT_MAX

SENSITIVE = "회사 자료에 민감 정보로 보이는 것이 있어요({kinds}). 지우거나 가린 뒤 다시 저장해 주세요"


class CompanyCreate(BaseModel):
    name: str = Field(min_length=1, max_length=NAME_MAX)


class CompanyProfile(BaseModel):
    systems: str = Field(default="", max_length=TEXT_MAX)  # 「우리 시스템 목록」, one system per line
    notes: str = Field(default="", max_length=NOTES_MAX)  # 회사 공통 자료: 용어·사내 규칙·이미 정한 것


def build_company_router(store: ProjectStore) -> APIRouter:
    router = APIRouter(prefix="/api/companies")

    def found(company_id: str) -> dict[str, Any]:
        company = store.get_company(company_id)
        if company is None:
            raise HTTPException(status_code=404, detail="회사가 없습니다")
        return company

    @router.get("")
    def list_companies() -> dict[str, Any]:
        return {"companies": store.companies()}

    @router.post("", status_code=201)
    def create_company(body: CompanyCreate) -> dict[str, Any]:
        name = body.name.strip()
        if not name:
            raise HTTPException(status_code=400, detail="회사 이름을 적어 주세요")
        labels = sensitive_labels([name])
        if labels:
            raise HTTPException(status_code=400, detail=SENSITIVE.format(kinds=", ".join(labels)))
        return store.create_company(name)

    @router.get("/{company_id}")
    def get_company(company_id: str) -> dict[str, Any]:
        company = found(company_id)
        past = store.past_decisions(company_id)
        return {**company, "past_decisions": past, "items": company_items(company, past),
                "services": store.services(company_id)}

    @router.put("/{company_id}")
    def save_company(company_id: str, body: CompanyProfile) -> dict[str, Any]:
        found(company_id)
        labels = sensitive_labels([body.systems, body.notes])
        if labels:
            raise HTTPException(status_code=400, detail=SENSITIVE.format(kinds=", ".join(labels)))
        return store.update_company(company_id, body.systems, body.notes)

    return router
