"""
Contract Parser Module — T4.1 (Người C)
========================================
Parses contract documents (PDF, DOCX, TXT) to Markdown using MinerU,
with PII detection and redaction for Vietnamese contracts.

Owner: Người C
Dependencies: MinerU (Apache 2.0)
Output: Contract dataclass with raw_text, redacted_text, pii_map
"""

from .models import Contract, ParseError
from .citations import LegalCitation

__all__ = [
    "Contract",
    "ParseError",
    "ContractParser",
    "LegalCitation",
    "LegalContextAssembler",
    "LegalRetrievalPlan",
    "QueryRewriter",
    "detect_pii",
    "redact_pii",
    "reconstruct_text",
]


def __getattr__(name: str):
    if name == "ContractParser":
        from .parser import ContractParser

        return ContractParser
    if name == "LegalContextAssembler":
        from .context_assembler import LegalContextAssembler

        return LegalContextAssembler
    if name in {"LegalRetrievalPlan", "QueryRewriter"}:
        from .query_rewriter import LegalRetrievalPlan, QueryRewriter

        return {
            "LegalRetrievalPlan": LegalRetrievalPlan,
            "QueryRewriter": QueryRewriter,
        }[name]
    if name in {"detect_pii", "redact_pii", "reconstruct_text"}:
        from .pii import detect_pii, redact_pii, reconstruct_text

        return {
            "detect_pii": detect_pii,
            "redact_pii": redact_pii,
            "reconstruct_text": reconstruct_text,
        }[name]
    if name in {"ContractReviewPipeline", "ContractReviewPipelineError"}:
        from .review_pipeline import ContractReviewPipeline, ContractReviewPipelineError

        return {
            "ContractReviewPipeline": ContractReviewPipeline,
            "ContractReviewPipelineError": ContractReviewPipelineError,
        }[name]
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
