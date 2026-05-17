"""Contract-specific compliance analysis over QA-style retrieved provisions."""
from __future__ import annotations

import json
import logging
from typing import Any, Optional

from src.contract.models import ComplianceResult, ComplianceViolation, ContractClause
from src.llm.client import LLMClient, create_client
from src.llm.prompts import PromptTemplate
from src.llm.qa_models import QARetrievedProvision

logger = logging.getLogger(__name__)


class ContractComplianceAnalyzer:
    """Analyze one contract clause against retrieved legal provisions."""

    def __init__(self, llm_client: Optional[LLMClient] = None) -> None:
        self._llm = llm_client or create_client()

    async def analyze(
        self,
        clause: ContractClause,
        provisions: list[QARetrievedProvision],
    ) -> ComplianceResult:
        if not provisions:
            return ComplianceResult(
                compliance_status="partially_compliant",
                summary="Không đủ căn cứ pháp lý trực tiếp từ dữ liệu truy xuất để kết luận.",
                violations=[],
                risks=[],
                suggestions=[],
                citations=[],
            )

        prompt = self._build_prompt(clause, provisions)
        raw_result = await self._llm.chat(prompt, temperature=0.0)
        return self._parse_llm_output(raw_result, provisions)

    def _build_prompt(self, clause: ContractClause, provisions: list[QARetrievedProvision]) -> str:
        provision_dicts = [provision.to_dict() for provision in provisions]
        effective_text = "\n\n".join(
            provision.effective_text or provision.text for provision in provisions if provision.effective_text or provision.text
        )
        amendment_history = [
            {
                "uid": provision.uid,
                "validity": provision.validity.to_dict(),
                "references_context": provision.references_context,
                "modifies_context": provision.modifies_context,
            }
            for provision in provisions
        ]
        return PromptTemplate("contract_clause_compliance_analysis").render(
            clause_type=clause.clause_type,
            clause_text=clause.text_content,
            retrieved_provisions=json.dumps(provision_dicts, ensure_ascii=False),
            effective_text=effective_text,
            amendment_history=json.dumps(amendment_history, ensure_ascii=False),
        )

    def _parse_llm_output(self, raw: Any, provisions: list[QARetrievedProvision]) -> ComplianceResult:
        data = self._coerce_json_object(raw)
        allowed_uids = {provision.uid for provision in provisions if provision.uid}

        violations = []
        for item in self._coerce_violation_list(data.get("violations")):
            violations.append(
                ComplianceViolation(
                    clause=str(item.get("clause") or ""),
                    description=str(item.get("description") or ""),
                    citation=str(item.get("citation") or ""),
                    severity=str(item.get("severity") or "medium"),
                )
            )

        citations = []
        for citation in self._coerce_dict_list(data.get("citations"), "citations"):
            uid = str(citation.get("uid") or "")
            if uid and uid not in allowed_uids:
                logger.warning("Dropped contract compliance citation with unknown uid: %s", uid)
                continue
            if not uid and len(provisions) == 1:
                citation["uid"] = provisions[0].uid
            citations.append(citation)

        return ComplianceResult(
            compliance_status=str(data.get("compliance_status") or "compliant"),
            summary=str(data.get("summary") or ""),
            violations=violations,
            risks=self._coerce_str_list(data.get("risks"), "risks"),
            suggestions=self._coerce_str_list(data.get("suggestions"), "suggestions"),
            citations=citations,
        )

    def _coerce_json_object(self, raw: Any) -> dict[str, Any]:
        if isinstance(raw, dict):
            return raw
        if isinstance(raw, str):
            content = raw.strip()
            if content.startswith("```"):
                segments = content.split("```")
                if len(segments) >= 3:
                    content = segments[1]
                if content.startswith("json"):
                    content = content[4:]
                content = content.strip()
            parsed = json.loads(content)
            if isinstance(parsed, dict):
                return parsed
        raise ValueError(f"Contract compliance analyzer expected JSON object, got {type(raw).__name__}")

    def _coerce_str_list(self, value: Any, field_name: str) -> list[str]:
        if value is None:
            return []
        if not isinstance(value, list):
            raise ValueError(f"Contract compliance analyzer expected '{field_name}' to be a list")
        return [str(item) for item in value]

    def _coerce_dict_list(self, value: Any, field_name: str) -> list[dict[str, Any]]:
        if value is None:
            return []
        if not isinstance(value, list):
            raise ValueError(f"Contract compliance analyzer expected '{field_name}' to be a list")
        return [item for item in value if isinstance(item, dict)]

    def _coerce_violation_list(self, value: Any) -> list[dict[str, Any]]:
        if value is None:
            return []
        if not isinstance(value, list):
            raise ValueError("Contract compliance analyzer expected 'violations' to be a list")
        normalized = []
        for item in value:
            if isinstance(item, dict):
                normalized.append(item)
            elif isinstance(item, str):
                normalized.append({"description": item, "severity": "medium"})
        return normalized
