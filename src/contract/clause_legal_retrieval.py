"""Contract-clause retrieval adapter backed by the QA retrieval service."""
from __future__ import annotations

from typing import Optional

from src.contract.models import ContractClause
from src.contract.query_rewriter import LegalRetrievalPlan, QueryRewriter
from src.llm.qa_models import QARetrievalResult
from src.llm.qa_retrieval import QARetrievalService


class ClauseLegalRetrieval:
    """Retrieve legal provisions for a contract clause without QA memory."""

    def __init__(
        self,
        retrieval_service: Optional[QARetrievalService] = None,
        query_rewriter: Optional[QueryRewriter] = None,
    ) -> None:
        self._retrieval = retrieval_service or QARetrievalService()
        self._query_rewriter = query_rewriter or QueryRewriter()

    async def retrieve(self, clause: ContractClause) -> QARetrievalResult:
        plan = await self._query_rewriter.rewrite(clause)
        plan = self._enrich_contract_plan(clause, plan)
        return await self._retrieval.retrieve_plan(plan, strategy="hybrid_search")

    def _enrich_contract_plan(self, clause: ContractClause, plan: LegalRetrievalPlan) -> LegalRetrievalPlan:
        text = " ".join([clause.clause_type, clause.text_content]).lower()
        original_text = self._query_from_clause(clause)
        plan.original_text = original_text

        if any(term in text for term in ["lương", "tiền lương", "trả lương", "chậm lương", "dòng tiền"]):
            plan.legal_issue = "thời hạn trả lương, chậm trả lương, tiền lãi khi trả lương chậm và lương tối thiểu vùng trong hợp đồng lao động"
            plan.risk_type = "wage_payment"
            plan.search_queries = self._dedupe(
                [
                    "người sử dụng lao động phải trả lương trực tiếp đầy đủ đúng hạn Bộ luật Lao động",
                    "chậm trả lương 60 ngày có phải trả thêm tiền lãi Bộ luật Lao động",
                    "trả lương chậm từ 15 ngày trở lên phải đền bù tiền lãi",
                    "thời hạn trả lương không được chậm quá 30 ngày",
                    "lương tối thiểu vùng khu vực I Hà Nội người lao động",
                    "mức lương tối thiểu tháng vùng I Hà Nội hợp đồng lao động",
                    *plan.search_queries,
                ]
            )
            plan.keywords = self._dedupe(
                [
                    "tiền lương",
                    "trả lương đúng hạn",
                    "chậm trả lương",
                    "tiền lãi",
                    "15 ngày",
                    "30 ngày",
                    "60 ngày",
                    "lương tối thiểu vùng",
                    "khu vực I",
                    "Hà Nội",
                    *plan.keywords,
                ]
            )
            plan.expected_domains = self._dedupe(["Bộ luật Lao động", "Nghị định lương tối thiểu", *plan.expected_domains])
            plan.title_hints = self._dedupe(["Bộ luật Lao động", "lương tối thiểu vùng", *plan.title_hints])
            plan.source = f"{plan.source}+contract_wage_enrichment"

        return plan

    def _query_from_clause(self, clause: ContractClause) -> str:
        parts = [
            "Rà soát tuân thủ pháp luật lao động cho điều khoản hợp đồng.",
            f"Loại điều khoản: {clause.clause_type}",
            f"Nội dung điều khoản: {clause.text_content}",
        ]
        if clause.obligations:
            parts.append(f"Nghĩa vụ: {'; '.join(clause.obligations)}")
        if clause.amount:
            parts.append(f"Số tiền: {clause.amount}")
        if clause.deadline:
            parts.append(f"Thời hạn: {clause.deadline}")
        return "\n".join(part for part in parts if part)

    def _dedupe(self, values) -> list[str]:
        seen: set[str] = set()
        result: list[str] = []
        for value in values:
            text = str(value or "").strip()
            key = text.lower()
            if text and key not in seen:
                result.append(text)
                seen.add(key)
        return result
