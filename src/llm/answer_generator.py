"""Answer generation for the Phase 5 legal QA pipeline."""
from __future__ import annotations

import json
from typing import Any, AsyncIterator, Optional

from src.llm.client import LLMClient, create_client
from src.llm.models import IntentClassification
from src.llm.prompts import PromptTemplate
from src.llm.qa_models import (
    QAAnswer,
    QACitation,
    QARetrievalResult,
    QAValidity,
    VALIDITY_UNKNOWN,
    intent_to_dict,
)


class QAAnswerGenerator:
    def __init__(self, llm_client: Optional[LLMClient] = None, max_retries: int = 1) -> None:
        self._llm = llm_client or create_client()
        self._max_retries = max_retries

    async def generate(
        self,
        question: str,
        classification: IntentClassification,
        retrieval: QARetrievalResult,
    ) -> QAAnswer:
        if not retrieval.provisions:
            return self.no_result_answer(classification, retrieval)

        prompt = self._build_prompt(question, retrieval)
        warnings: list[str] = []
        raw_output: Any = None

        for attempt in range(self._max_retries + 1):
            raw_output = await self._llm.chat(prompt, temperature=0.0)
            try:
                answer = self.parse_llm_output(
                    raw_output,
                    classification=classification,
                    retrieval=retrieval,
                )
                answer.warnings.extend(warnings)
                return answer
            except ValueError as exc:
                warnings.append(str(exc))
                if attempt >= self._max_retries:
                    return QAAnswer(
                        answer=str(raw_output),
                        citations=[],
                        retrieved_provisions=retrieval.provisions,
                        intent=intent_to_dict(classification),
                        confidence=classification.confidence,
                        validity=_aggregate_validity(retrieval),
                        retrieval_status=retrieval.retrieval_status,
                        warnings=warnings,
                        raw_output=raw_output,
                    )

        raise RuntimeError("Unreachable answer generation state")

    async def stream_answer(
        self,
        question: str,
        classification: IntentClassification,
        retrieval: QARetrievalResult,
    ) -> AsyncIterator[str]:
        prompt = self._build_stream_prompt(question, retrieval)
        if not retrieval.provisions:
            yield self.no_result_answer(classification, retrieval).answer
            return

        async for chunk in self._llm.chat_stream(prompt, temperature=0.0):
            yield chunk

    def no_result_answer(
        self,
        classification: IntentClassification,
        retrieval: QARetrievalResult,
    ) -> QAAnswer:
        return QAAnswer(
            answer="Tôi chưa tìm thấy quy định pháp luật phù hợp trong dữ liệu hiện có.",
            citations=[],
            retrieved_provisions=[],
            intent=intent_to_dict(classification),
            confidence=classification.confidence,
            validity=QAValidity(
                status=VALIDITY_UNKNOWN,
                reason="No retrieved provisions were available for validity assessment.",
            ),
            retrieval_status="no_results",
        )

    def parse_llm_output(
        self,
        raw: Any,
        classification: IntentClassification,
        retrieval: QARetrievalResult,
    ) -> QAAnswer:
        data = self._coerce_json_object(raw)
        allowed_uids = {provision.uid for provision in retrieval.provisions if provision.uid}
        citations: list[QACitation] = []
        warnings: list[str] = []

        for raw_citation in data.get("citations", []) or []:
            citation = QACitation.from_raw(raw_citation)
            if citation.uid and citation.uid not in allowed_uids:
                warnings.append(f"Dropped citation with unknown uid: {citation.uid}")
                continue
            if not citation.uid and len(retrieval.provisions) == 1:
                citation.uid = retrieval.provisions[0].uid
            citations.append(citation)

        if not citations and retrieval.provisions:
            citations = [retrieval.provisions[0].to_citation()]

        return QAAnswer(
            answer=str(data.get("answer") or ""),
            citations=citations,
            retrieved_provisions=retrieval.provisions,
            intent=data.get("intent") if isinstance(data.get("intent"), dict) else intent_to_dict(classification),
            confidence=float(data.get("confidence") or classification.confidence),
            validity=_coerce_validity(data.get("validity")) or _aggregate_validity(retrieval),
            retrieval_status=str(data.get("retrieval_status") or retrieval.retrieval_status),
            warnings=warnings,
            raw_output=raw,
        )

    def _build_prompt(self, question: str, retrieval: QARetrievalResult) -> str:
        provision_dicts = [provision.to_dict() for provision in retrieval.provisions]
        effective_text = "\n\n".join(
            provision.effective_text or provision.text for provision in retrieval.provisions if provision.effective_text or provision.text
        )
        amendment_history = [
            {
                "uid": provision.uid,
                "modifies_context": provision.modifies_context,
                "validity": provision.validity.to_dict(),
            }
            for provision in retrieval.provisions
        ]

        return PromptTemplate("answer_generation").render(
            question=question,
            retrieved_provisions=json.dumps(provision_dicts, ensure_ascii=False),
            effective_text=effective_text,
            amendment_history=json.dumps(amendment_history, ensure_ascii=False),
        )

    def _build_stream_prompt(self, question: str, retrieval: QARetrievalResult) -> str:
        provision_dicts = [provision.to_dict() for provision in retrieval.provisions]
        effective_text = "\n\n".join(
            provision.effective_text or provision.text for provision in retrieval.provisions if provision.effective_text or provision.text
        )
        amendment_history = [
            {
                "uid": provision.uid,
                "modifies_context": provision.modifies_context,
                "validity": provision.validity.to_dict(),
            }
            for provision in retrieval.provisions
        ]

        return PromptTemplate("answer_generation_stream").render(
            question=question,
            retrieved_provisions=json.dumps(provision_dicts, ensure_ascii=False),
            effective_text=effective_text,
            amendment_history=json.dumps(amendment_history, ensure_ascii=False),
        )

    def _coerce_json_object(self, raw: Any) -> dict[str, Any]:
        if isinstance(raw, dict):
            return raw
        if isinstance(raw, str):
            content = raw.strip()
            if content.startswith("```"):
                parts = content.split("```")
                if len(parts) >= 3:
                    content = parts[1]
                if content.strip().startswith("json"):
                    content = content.strip()[4:]
            parsed = json.loads(content)
            if isinstance(parsed, dict):
                return parsed
        raise ValueError("Answer generation expected a JSON object")


def _coerce_validity(raw: Any) -> Optional[QAValidity]:
    if not isinstance(raw, dict):
        return None
    evidence = raw.get("evidence") if isinstance(raw.get("evidence"), list) else []
    return QAValidity(
        status=str(raw.get("status") or VALIDITY_UNKNOWN),
        reason=str(raw.get("reason") or ""),
        evidence=evidence,
    )


def _aggregate_validity(retrieval: QARetrievalResult) -> QAValidity:
    if not retrieval.provisions:
        return QAValidity(status=VALIDITY_UNKNOWN, reason="No provisions were retrieved.")
    statuses = {provision.validity.status for provision in retrieval.provisions}
    if len(statuses) == 1:
        status = next(iter(statuses))
    else:
        status = VALIDITY_UNKNOWN
    return QAValidity(
        status=status,
        reason="Aggregated from retrieved provision validity signals.",
        evidence=[{"uid": p.uid, "validity": p.validity.to_dict()} for p in retrieval.provisions],
    )
