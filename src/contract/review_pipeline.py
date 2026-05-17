from __future__ import annotations

from dataclasses import dataclass, field
from typing import Awaitable, Callable, Optional

from src.contract.citations import LegalCitation
from src.contract.clause_extractor import ClauseExtractor
from src.contract.clause_legal_retrieval import ClauseLegalRetrieval
from src.contract.contract_compliance_analyzer import ContractComplianceAnalyzer
from src.contract.models import ComplianceResult, Contract, ContractClause
from src.contract.parser import ContractParser
from src.llm.citation_verifier import CitationVerifier, VerificationResult
from src.llm.qa_models import QARetrievalResult, QARetrievedProvision


class ContractReviewPipelineError(Exception):
    def __init__(self, stage: str, message: str, original: Optional[Exception] = None) -> None:
        self.stage = stage
        self.original = original
        super().__init__(f"{stage}: {message}")


ProgressCallback = Callable[[str, int], Awaitable[None] | None]


@dataclass
class ClauseReviewResult:
    clause: ContractClause
    retrieval_result: QARetrievalResult
    matches: list[QARetrievedProvision] = field(default_factory=list)
    compliance: Optional[ComplianceResult] = None
    citations: list[LegalCitation] = field(default_factory=list)
    verification_results: list[VerificationResult] = field(default_factory=list)


@dataclass
class ContractReviewResult:
    contract: Contract
    clauses: list[ClauseReviewResult] = field(default_factory=list)


class ContractReviewPipeline:
    """Real Task 4 orchestration service."""

    def __init__(
        self,
        parser: Optional[ContractParser] = None,
        clause_extractor: Optional[ClauseExtractor] = None,
        clause_retrieval: Optional[ClauseLegalRetrieval] = None,
        analyzer: Optional[ContractComplianceAnalyzer] = None,
        citation_verifier: Optional[CitationVerifier] = None,
        progress_callback: Optional[ProgressCallback] = None,
    ) -> None:
        self._parser = parser or ContractParser()
        self._clause_extractor = clause_extractor or ClauseExtractor()
        self._clause_retrieval = clause_retrieval or ClauseLegalRetrieval()
        self._analyzer = analyzer or ContractComplianceAnalyzer()
        self._citation_verifier = citation_verifier or CitationVerifier()
        self._progress_callback = progress_callback

    async def review_file(self, file_path: str) -> ContractReviewResult:
        await self._report_progress("parsing", 10)
        contract = self._run_stage("parsing", lambda: self._parser.parse(file_path))
        await self._report_progress("parsing", 25)
        self._ensure_supported_contract(contract)
        return await self.review_contract(contract)

    async def review_contract(self, contract: Contract) -> ContractReviewResult:
        await self._report_progress("extracting", 25)
        clauses = await self._run_async_stage("extracting", self._clause_extractor.extract(contract))
        await self._report_progress("extracting", 40)
        result = ContractReviewResult(contract=contract)

        if not clauses:
            return result

        import asyncio

        semaphore = asyncio.Semaphore(3)  # Limit concurrency to avoid API rate limits
        total = max(len(clauses), 1)

        async def run_bounded(fn):
            async with semaphore:
                return await fn()

        async def retrieve_clause(clause: ContractClause):
            retrieval = await self._run_async_stage("retrieving", self._clause_retrieval.retrieve(clause))
            return clause, retrieval

        retrieved: list[tuple[ContractClause, QARetrievalResult]] = []
        retrieve_tasks = [asyncio.create_task(run_bounded(lambda clause=clause: retrieve_clause(clause))) for clause in clauses]
        for completed, task in enumerate(asyncio.as_completed(retrieve_tasks), start=1):
            retrieved.append(await task)
            await self._report_progress("retrieving", 40 + round((completed / total) * 25))

        async def analyze_clause(clause: ContractClause, retrieval: QARetrievalResult):
            compliance = await self._run_async_stage("analyzing", self._analyzer.analyze(clause, retrieval.provisions))
            return clause.id, compliance

        compliance_by_clause: dict[str, ComplianceResult] = {}
        analyze_tasks = [
            asyncio.create_task(run_bounded(lambda clause=clause, retrieval=retrieval: analyze_clause(clause, retrieval)))
            for clause, retrieval in retrieved
        ]
        for completed, task in enumerate(asyncio.as_completed(analyze_tasks), start=1):
            clause_id, compliance = await task
            compliance_by_clause[clause_id] = compliance
            await self._report_progress("analyzing", 65 + round((completed / total) * 20))

        async def verify_clause(
            clause: ContractClause,
            retrieval: QARetrievalResult,
            compliance: Optional[ComplianceResult],
        ) -> ClauseReviewResult:
            citations = self._citations_from_matches(retrieval.provisions)
            verification_results = await self._run_async_stage("verifying", self._citation_verifier.verify_batch(citations))

            compliance_citations = self._citations_from_compliance(compliance)
            if compliance and compliance_citations:
                compliance_verification = await self._citation_verifier.verify_batch(compliance_citations)
                for violation, verification in zip(compliance.violations, compliance_verification):
                    violation.verified = verification.verified

            return ClauseReviewResult(
                clause=clause,
                retrieval_result=retrieval,
                matches=retrieval.provisions,
                compliance=compliance,
                citations=citations,
                verification_results=verification_results,
            )

        verify_tasks = [
            asyncio.create_task(
                run_bounded(
                    lambda clause=clause, retrieval=retrieval: verify_clause(
                        clause,
                        retrieval,
                        compliance_by_clause.get(clause.id),
                    )
                )
            )
            for clause, retrieval in retrieved
        ]
        for completed, task in enumerate(asyncio.as_completed(verify_tasks), start=1):
            result.clauses.append(await task)
            await self._report_progress("verifying", 85 + round((completed / total) * 10))

        result.clauses.sort(key=lambda item: item.clause.index)
        return result

    def _citations_from_matches(self, matches: list[QARetrievedProvision]) -> list[LegalCitation]:
        citations: list[LegalCitation] = []
        for match in matches:
            citations.append(match.to_citation().to_legal_citation())
        return citations

    def _citations_from_compliance(self, compliance: Optional[ComplianceResult]) -> list[LegalCitation]:
        """Extract citations from compliance analysis results for verification."""
        if not compliance or not compliance.citations:
            return []
        citations: list[LegalCitation] = []
        for cit in compliance.citations:
            if isinstance(cit, dict):
                citations.append(
                    LegalCitation(
                        display_text=cit.get("display_text") or cit.get("citation", ""),
                        uid=cit.get("uid", ""),
                        document_title=cit.get("document_title") or cit.get("documentTitle", ""),
                        article=cit.get("article"),
                        clause=cit.get("clause"),
                        point=cit.get("point"),
                    )
                )
        return citations

    def _ensure_supported_contract(self, contract: Contract) -> None:
        text = f"{contract.raw_text}\n{contract.redacted_text}".lower()
        rental_terms = [
            "hợp đồng thuê nhà",
            "thuê nhà",
            "thuê căn hộ",
            "căn hộ",
            "nhà ở",
            "bên cho thuê",
            "bên thuê",
            "giá thuê",
            "tiền thuê nhà",
            "đặt cọc thuê",
            "bất động sản",
        ]
        labor_terms = [
            "hợp đồng lao động",
            "người lao động",
            "người sử dụng lao động",
            "tiền lương",
            "lương",
            "phụ cấp",
            "bảo hiểm xã hội",
            "bảo hiểm y tế",
            "bảo hiểm thất nghiệp",
            "thử việc",
            "nghỉ việc",
            "sa thải",
            "kỷ luật lao động",
            "thời giờ làm việc",
            "việc làm",
        ]

        if any(term in text for term in rental_terms):
            raise ContractReviewPipelineError(
                "guardrail",
                "Loại hợp đồng này chưa được hỗ trợ. Contract Review hiện chỉ hỗ trợ hợp đồng lao động/việc làm/BHXH, chưa hỗ trợ hợp đồng thuê nhà hoặc bất động sản.",
            )

        if not any(term in text for term in labor_terms):
            raise ContractReviewPipelineError(
                "guardrail",
                "Loại hợp đồng này chưa được hỗ trợ. Contract Review hiện chỉ hỗ trợ hợp đồng lao động/việc làm/BHXH.",
            )

    def _run_stage(self, stage: str, fn):
        try:
            return fn()
        except ContractReviewPipelineError:
            raise
        except Exception as e:
            raise ContractReviewPipelineError(stage, str(e), e) from e

    async def _run_async_stage(self, stage: str, awaitable):
        try:
            return await awaitable
        except ContractReviewPipelineError:
            raise
        except Exception as e:
            raise ContractReviewPipelineError(stage, str(e), e) from e

    async def _report_progress(self, status: str, progress: int) -> None:
        if not self._progress_callback:
            return
        result = self._progress_callback(status, max(0, min(100, progress)))
        if result is not None:
            await result
