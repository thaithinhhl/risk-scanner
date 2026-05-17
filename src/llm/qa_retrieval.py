"""Retrieval adapter for the Phase 5 legal QA pipeline."""
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional, Protocol

from neo4j import GraphDatabase

from src.config import LOOKUP_PATH, NEO4J_TIMEOUT, NEO4J_URI, neo4j_auth
from src.contract.hybrid_retriever import LegalCandidate, LegalHybridRetriever
from src.contract.query_rewriter import LegalRetrievalPlan
from src.llm.client import LLMClient, create_client
from src.llm.models import IntentClassification, SubQuery
from src.llm.prompts import PromptTemplate
from src.llm.qa_models import (
    QAValidity,
    QARetrievalResult,
    QARetrievedProvision,
    VALIDITY_LIKELY_CURRENT,
    VALIDITY_UNKNOWN,
    VALIDITY_VERIFIED,
)
from src.llm.qa_planner import plan_qa_sub_queries

logger = logging.getLogger(__name__)


@dataclass
class LegalReference:
    article: Optional[int] = None
    clause: Optional[str] = None
    point: Optional[str] = None
    doc_id: str = ""
    so_ky_hieu: str = ""
    document_hint: str = ""
    year: str = ""
    canonical_citation: str = ""
    rewrite_source: str = "parser"


class CandidateRetriever(Protocol):
    async def retrieve(self, plan: LegalRetrievalPlan) -> list[LegalCandidate]:
        ...


class QARetrievalService:
    def __init__(
        self,
        hybrid_retriever: Optional[CandidateRetriever] = None,
        driver: Any = None,
        llm_client: Optional[LLMClient] = None,
        return_top_n: int = 5,
    ) -> None:
        self._hybrid_retriever = hybrid_retriever
        self._driver = driver
        self._llm = llm_client
        self._return_top_n = return_top_n
        self._doc_lookup: Optional[dict[str, str]] = None

    async def retrieve(
        self,
        question: str,
        classification: IntentClassification,
    ) -> QARetrievalResult:
        sub_queries = plan_qa_sub_queries(classification, question)
        logger.info(
            "QA retrieval plan conversation_id=%s sub_queries=%d",
            classification.conversation_id,
            len(sub_queries),
        )
        for index, sub_query in enumerate(sub_queries, start=1):
            logger.info(
                "QA retrieval sub_query[%d] intent=%s query=%r strategy=%s requires=%s",
                index,
                sub_query.intent,
                sub_query.query,
                sub_query.retrieval_strategy,
                sub_query.requires,
            )
        provisions: list[QARetrievedProvision] = []
        errors: list[str] = []
        rewritten_queries: dict[str, str] = {}
        query_debug: dict[str, dict[str, Any]] = {}

        for sub_query in sub_queries:
            try:
                sub_provisions, debug = await self.retrieve_sub_query(sub_query)
                provisions.extend(sub_provisions)
                if debug.get("rewritten_query"):
                    rewritten_queries[sub_query.query] = str(debug["rewritten_query"])
                if debug:
                    query_debug[sub_query.query] = debug
            except Exception as exc:
                errors.append(f"{sub_query.retrieval_strategy}: {exc}")

        provisions = self._dedupe_and_rank(provisions)
        status = "ok" if provisions else "no_results"
        if errors and not provisions:
            status = "error"

        return QARetrievalResult(
            query=question,
            sub_queries=sub_queries,
            provisions=provisions,
            retrieval_status=status,
            errors=errors,
            rewritten_queries=rewritten_queries,
            query_debug=query_debug,
        )

    async def retrieve_sub_query(self, sub_query: SubQuery) -> tuple[list[QARetrievedProvision], dict[str, Any]]:
        strategy = sub_query.retrieval_strategy
        logger.info(
            "QA retrieval execute intent=%s query=%r strategy=%s requires=%s",
            sub_query.intent,
            sub_query.query,
            strategy,
            sub_query.requires,
        )
        if strategy == "direct_lookup":
            results, debug = await self._direct_lookup(sub_query)
            logger.info("QA retrieval direct_lookup results=%d query=%r", len(results), sub_query.query)
            return results, debug
        if strategy == "validity_check":
            provisions, debug = await self._direct_lookup(sub_query)
            if not provisions:
                logger.info("QA retrieval validity_check unresolved query=%r", sub_query.query)
                return [
                    QARetrievedProvision(
                        uid="",
                        strategy="validity_check",
                        validity=QAValidity(
                            status=VALIDITY_UNKNOWN,
                            reason="Could not resolve the legal reference for validity checking.",
                        ),
                    )
                ], debug
            results = [self._with_validity(provision) for provision in provisions]
            logger.info("QA retrieval validity_check results=%d query=%r", len(results), sub_query.query)
            return results, debug
        results = await self._hybrid_search(sub_query)
        logger.info("QA retrieval hybrid_search results=%d query=%r strategy=%s", len(results), sub_query.query, strategy)
        return results, {"rewritten_query": sub_query.query, "strategy": strategy}

    async def _hybrid_search(self, sub_query: SubQuery) -> list[QARetrievedProvision]:
        retriever = self._hybrid_retriever or LegalHybridRetriever(return_top_n=self._return_top_n)
        plan = LegalRetrievalPlan(
            original_text=sub_query.query,
            legal_issue=sub_query.query,
            search_queries=[sub_query.query],
            keywords=[],
            expected_domains=[],
            title_hints=[],
            risk_type=sub_query.intent.lower(),
            confidence=0.5,
            source="qa_sub_query",
        )
        candidates = await retriever.retrieve(plan)
        return [self._candidate_to_provision(candidate, sub_query.retrieval_strategy) for candidate in candidates]

    async def retrieve_plan(self, plan: LegalRetrievalPlan, strategy: str = "hybrid_search") -> QARetrievalResult:
        """Run QA-style retrieval from an explicit legal retrieval plan."""
        retriever = self._hybrid_retriever or LegalHybridRetriever(return_top_n=self._return_top_n)
        candidates = await retriever.retrieve(plan)
        provisions = [self._candidate_to_provision(candidate, strategy) for candidate in candidates]
        provisions = self._dedupe_and_rank(provisions)
        return QARetrievalResult(
            query=plan.original_text,
            sub_queries=[
                SubQuery(
                    intent=plan.risk_type.upper() or "SCENARIO",
                    query=plan.legal_issue or plan.original_text,
                    retrieval_strategy=strategy,
                    requires=["legal_provision", "effective_text", "contract_context"],
                )
            ],
            provisions=provisions,
            retrieval_status="ok" if provisions else "no_results",
            errors=[],
            rewritten_queries={plan.original_text: plan.legal_issue or plan.original_text},
            query_debug={
                plan.original_text: {
                    "strategy": strategy,
                    "source": plan.source,
                    "search_queries": list(plan.search_queries),
                    "keywords": list(plan.keywords),
                    "expected_domains": list(plan.expected_domains),
                    "title_hints": list(plan.title_hints),
                    "risk_type": plan.risk_type,
                }
            },
        )

    async def _direct_lookup(self, sub_query: SubQuery) -> tuple[list[QARetrievedProvision], dict[str, Any]]:
        reference = await self._resolve_direct_reference(sub_query.query)
        debug = self._direct_lookup_debug(sub_query.query, reference)
        if not reference.article:
            return [], debug
        reference.doc_id = reference.doc_id or self._resolve_doc_id(reference)
        debug = self._direct_lookup_debug(sub_query.query, reference)
        logger.info(
            "QA direct_lookup rewrite raw=%r rewritten=%r source=%s article=%s clause=%s point=%s doc_id=%r so_ky_hieu=%r normalized_so_ky_hieu=%r document_hint=%r year=%r",
            sub_query.query,
            debug.get("rewritten_query", ""),
            debug.get("rewrite_source", ""),
            reference.article,
            reference.clause,
            reference.point,
            reference.doc_id,
            reference.so_ky_hieu,
            debug.get("normalized_so_ky_hieu", ""),
            reference.document_hint,
            reference.year,
        )

        driver = self._driver or GraphDatabase.driver(NEO4J_URI, auth=neo4j_auth())
        cypher = """
        MATCH (doc:Document)
        WHERE ($doc_id <> "" AND toString(doc.id) = $doc_id)
           OR ($doc_id = "" AND $so_ky_hieu <> "" AND (
              doc.so_ky_hieu = $so_ky_hieu
              OR doc.normalized_so_ky_hieu = $normalized_so_ky_hieu
              OR toLower(coalesce(doc.so_ky_hieu, "")) = toLower($so_ky_hieu)
              OR toLower(coalesce(doc.normalized_so_ky_hieu, "")) = toLower($normalized_so_ky_hieu)
           ))
           OR ($doc_id = "" AND $document_hint <> "" AND toLower(coalesce(doc.title, "")) CONTAINS toLower($document_hint))
        OPTIONAL MATCH (doc)-[:HAS_ARTICLE]->(a_direct:Article)
          WHERE toString(a_direct.index) = $article
        OPTIONAL MATCH (doc)-[:HAS_CHAPTER]->(:Chapter)-[:HAS_ARTICLE]->(a_ch:Article)
          WHERE toString(a_ch.index) = $article
        OPTIONAL MATCH (a_uid:Article {uid: $article_uid})
        WITH doc, coalesce(a_direct, a_ch, a_uid) AS a
        WHERE a IS NOT NULL
        OPTIONAL MATCH (a)-[:HAS_CLAUSE]->(clause:Clause)
          WHERE $clause = "" OR toString(clause.index) = $clause
        OPTIONAL MATCH (clause)-[:HAS_POINT]->(point:Point)
          WHERE $point = "" OR toLower(point.letter) = toLower($point)
        WITH a, doc, clause, point
        WHERE $clause = "" OR clause IS NOT NULL
        WITH a, doc, clause, point
        WHERE $point = "" OR point IS NOT NULL
        RETURN a, doc, clause, point
        LIMIT 200
        """
        logger.info(
            "QA direct_lookup neo4j params doc_id=%r article=%s article_uid=%r clause=%r point=%r so_ky_hieu=%r normalized_so_ky_hieu=%r document_hint=%r year=%r",
            debug.get("doc_id", ""),
            debug.get("article"),
            _article_uid(reference),
            debug.get("clause", ""),
            debug.get("point", ""),
            debug.get("so_ky_hieu", ""),
            debug.get("normalized_so_ky_hieu", ""),
            debug.get("document_hint", ""),
            debug.get("year", ""),
        )
        logger.info(
            "QA direct_lookup neo4j cypher=%s",
            "MATCH Document by id/so_ky_hieu/title; resolve Article by HAS_ARTICLE, HAS_CHAPTER/HAS_ARTICLE, or uid doc_{doc_id}_dieu_{article}; then HAS_CLAUSE/HAS_POINT",
        )

        with driver.session(default_access_mode="READ", database="neo4j") as session:
            rows = list(
                session.run(
                    cypher,
                    article=str(reference.article),
                    article_uid=_article_uid(reference),
                    clause=reference.clause or "",
                    point=reference.point or "",
                    doc_id=reference.doc_id,
                    so_ky_hieu=reference.so_ky_hieu,
                    normalized_so_ky_hieu=_normalize_so_ky_hieu(reference.so_ky_hieu, reference.document_hint),
                    document_hint=reference.document_hint,
                    year=reference.year,
                    config={"maxTransactionRetryTime": NEO4J_TIMEOUT * 1000},
                )
            )

        provisions = []
        article_added = False
        clause_uids_added: set[str] = set()
        for row in rows:
            if not article_added and not reference.clause and not reference.point:
                article_row = _article_only_row(row)
                provisions.append(self._row_to_provision(article_row, reference, sub_query.retrieval_strategy))
                article_added = True
            if not reference.clause and not reference.point and row.get("clause"):
                clause_uid = row["clause"].get("uid")
                if clause_uid and clause_uid not in clause_uids_added:
                    clause_row = _clause_only_row(row)
                    provisions.append(self._row_to_provision(clause_row, reference, sub_query.retrieval_strategy))
                    clause_uids_added.add(clause_uid)
            if row.get("point") or reference.clause or reference.point or not row.get("clause"):
                provisions.append(self._row_to_provision(row, reference, sub_query.retrieval_strategy))
        logger.info("QA direct_lookup neo4j rows=%d doc_id=%r article=%s", len(rows), reference.doc_id, reference.article)
        debug["neo4j_rows"] = len(rows)
        return provisions, debug

    def _direct_lookup_debug(self, raw_query: str, reference: LegalReference) -> dict[str, Any]:
        return {
            "raw_query": raw_query,
            "rewritten_query": reference.canonical_citation or _canonical_reference(reference),
            "rewrite_source": reference.rewrite_source,
            "article": reference.article,
            "clause": reference.clause or "",
            "point": reference.point or "",
            "doc_id": reference.doc_id,
            "so_ky_hieu": reference.so_ky_hieu,
            "normalized_so_ky_hieu": _normalize_so_ky_hieu(reference.so_ky_hieu, reference.document_hint),
            "document_hint": reference.document_hint,
            "year": reference.year,
        }

    async def _resolve_direct_reference(self, query: str) -> LegalReference:
        reference = parse_legal_reference(query)
        rewritten = None
        if (
            _has_citation_signal(query)
            and not (reference.article and (reference.document_hint or reference.so_ky_hieu))
        ):
            rewritten = await self._rewrite_direct_reference(query)
        if rewritten:
            reference = rewritten
        if reference.article:
            reference.doc_id = reference.doc_id or self._resolve_doc_id(reference)
            reference.canonical_citation = reference.canonical_citation or _canonical_reference(reference)
            logger.info(
                "QA direct_lookup rewrite raw=%r rewritten=%r source=%s article=%s clause=%s point=%s doc_id=%r so_ky_hieu=%r document_hint=%r year=%r",
                query,
                reference.canonical_citation,
                reference.rewrite_source,
                reference.article,
                reference.clause,
                reference.point,
                reference.doc_id,
                reference.so_ky_hieu,
                reference.document_hint,
                reference.year,
            )
            return reference

        return reference

    async def _rewrite_direct_reference(self, query: str) -> Optional[LegalReference]:
        llm = self._llm
        if llm is None:
            try:
                llm = create_client()
                self._llm = llm
            except Exception as exc:
                logger.info("QA direct_lookup rewrite unavailable query=%r error=%s", query, exc)
                return None

        prompt = PromptTemplate("direct_reference_rewrite").render(query=query)
        try:
            raw = await llm.chat(prompt, temperature=0.0)
        except Exception as exc:
            logger.info("QA direct_lookup rewrite failed query=%r error=%s", query, exc)
            return None

        reference = legal_reference_from_rewrite(raw)
        if reference.article:
            logger.info(
                "QA direct_lookup rewrite article=%s clause=%s point=%s doc=%r so_ky_hieu=%r year=%r",
                reference.article,
                reference.clause,
                reference.point,
                reference.document_hint,
                reference.so_ky_hieu,
                reference.year,
            )
            return reference
        return None

    def _resolve_doc_id(self, reference: LegalReference) -> str:
        lookup = self._load_doc_lookup()
        if not lookup:
            return ""

        candidates = [
            reference.so_ky_hieu,
            _normalize_so_ky_hieu(reference.so_ky_hieu, reference.document_hint),
        ]
        for candidate in candidates:
            key = candidate.strip() if candidate else ""
            if key and key in lookup:
                return str(lookup[key])
        return ""

    def _load_doc_lookup(self) -> dict[str, str]:
        if self._doc_lookup is not None:
            return self._doc_lookup

        lookup: dict[str, str] = {}
        for path in [Path(LOOKUP_PATH), Path("data/so_ky_hieu_lookup.json"), Path("output/final_lookup_ui.json")]:
            if not path.exists():
                continue
            try:
                with path.open(encoding="utf-8") as f:
                    data = json.load(f)
            except Exception as exc:
                logger.info("QA direct_lookup lookup load failed path=%s error=%s", path, exc)
                continue
            for key, value in data.items():
                lookup[str(key).strip()] = str(value)

        self._doc_lookup = lookup
        logger.info("QA direct_lookup lookup loaded entries=%d", len(lookup))
        return lookup

    def _row_to_provision(self, row: Any, reference: LegalReference, strategy: str) -> QARetrievedProvision:
        article = dict(row["a"]) if row.get("a") else {}
        doc = dict(row["doc"]) if row.get("doc") else {}
        clause = dict(row["clause"]) if row.get("clause") else {}
        point = dict(row["point"]) if row.get("point") else {}
        node = point or clause or article
        segment_type = "Point" if point else "Clause" if clause else "Article"
        uid = node.get("uid") or article.get("uid", "")
        text = node.get("clean_text") or node.get("text_content") or article.get("clean_text", "")
        citation = _display_citation(
            article_index=article.get("index"),
            clause_index=clause.get("index") or reference.clause,
            point_label=point.get("letter") or reference.point,
            document_title=doc.get("title", ""),
        )
        is_current = bool(node.get("is_current", article.get("is_current", True)))

        return QARetrievedProvision(
            uid=uid,
            segment_type=segment_type,
            text=text,
            display_citation=citation,
            article_uid=article.get("uid", ""),
            article_index=article.get("index"),
            article_title=article.get("title", ""),
            clause_index=str(clause.get("index")) if clause.get("index") is not None else reference.clause,
            point_label=point.get("letter", reference.point or ""),
            document_title=doc.get("title", ""),
            document_so_ky_hieu=doc.get("so_ky_hieu", ""),
            document_type=doc.get("loai_van_ban", ""),
            score=1.0,
            strategy=strategy,
            effective_text=text,
            effective_text_status="fallback",
            validity=QAValidity(
                status=VALIDITY_VERIFIED if is_current else VALIDITY_LIKELY_CURRENT,
                reason="Graph is_current metadata was available." if is_current else "Graph metadata indicates the provision may not be current.",
                evidence=[{"is_current": is_current}],
            ),
        )

    def _candidate_to_provision(self, candidate: LegalCandidate, strategy: str) -> QARetrievedProvision:
        validity = self._validity_from_candidate(candidate)
        return QARetrievedProvision(
            uid=candidate.uid,
            segment_type=candidate.segment_type or "LegalSegment",
            text=candidate.text,
            display_citation=candidate.display_citation(),
            article_uid=candidate.article_uid,
            article_index=_maybe_int(candidate.article_index),
            article_title=candidate.article_title,
            clause_index=str(candidate.clause_index) if candidate.clause_index is not None else None,
            point_label=candidate.point_letter,
            document_title=candidate.document_title,
            document_so_ky_hieu=candidate.document_so_ky_hieu,
            document_type=candidate.document_type,
            score=float(candidate.combined_score or 0.0),
            strategy=strategy,
            effective_text=candidate.text,
            effective_text_status="fallback",
            validity=validity,
            references_context=list(candidate.references_context),
            modifies_context=list(candidate.modifies_context),
            score_factors={
                "vector": candidate.score_factors.vector,
                "lexical": candidate.score_factors.lexical,
                "exact": candidate.score_factors.exact,
                "title": candidate.score_factors.title,
                "graph": candidate.score_factors.graph,
                "authority": candidate.score_factors.authority,
                "validity": candidate.score_factors.validity,
            },
        )

    def _with_validity(self, provision: QARetrievedProvision) -> QARetrievedProvision:
        if provision.validity.status == VALIDITY_VERIFIED:
            return provision
        provision.validity = QAValidity(
            status=VALIDITY_UNKNOWN,
            reason="Validity was requested, but only partial graph metadata is available.",
            evidence=provision.validity.evidence,
        )
        return provision

    def _validity_from_candidate(self, candidate: LegalCandidate) -> QAValidity:
        if candidate.validity_signal == "possibly_modified" or candidate.modifies_context:
            return QAValidity(
                status=VALIDITY_LIKELY_CURRENT,
                reason="Related MODIFIES context exists; effective text composition is not available.",
                evidence=list(candidate.modifies_context),
            )
        return QAValidity(
            status=VALIDITY_UNKNOWN,
            reason="No definitive EffectiveArticle or relationship evidence was available.",
            evidence=[],
        )

    def _dedupe_and_rank(self, provisions: list[QARetrievedProvision]) -> list[QARetrievedProvision]:
        by_uid: dict[str, QARetrievedProvision] = {}
        for provision in provisions:
            key = provision.uid or f"{provision.display_citation}:{provision.strategy}"
            if key not in by_uid or provision.score > by_uid[key].score:
                by_uid[key] = provision
        ranked = sorted(by_uid.values(), key=lambda item: item.score, reverse=True)
        if any(item.strategy in {"direct_lookup", "validity_check"} for item in ranked):
            return ranked
        return ranked[: self._return_top_n]


def parse_legal_reference(text: str) -> LegalReference:
    article = _match_int(r"[Đđ]iều\s+(\d+)", text)
    clause = _match_text(r"[Kk]hoản\s+(\d+)", text)
    point = _match_text(r"[Đđ]iểm\s+([a-zA-Z])", text)
    so_ky_hieu = _match_text(
        r"\b((?:LT|ND|TT|TTLT|BL)-\d{2,3}-\d{4}|\d+/\d{4}/[A-ZĐ0-9\-]+)\b",
        text,
    )
    year = _match_text(r"\b(20\d{2}|19\d{2})\b", text)
    document_hint = _extract_document_hint(text)
    return LegalReference(
        article=article,
        clause=clause,
        point=point.lower() if point else None,
        so_ky_hieu=so_ky_hieu,
        document_hint=document_hint,
        year=year,
    )


def legal_reference_from_rewrite(raw: dict[str, Any]) -> LegalReference:
    canonical = str(raw.get("canonical_citation") or "")
    parsed = parse_legal_reference(canonical)
    article = _maybe_int(raw.get("article")) or parsed.article
    clause = _clean_reference_text(raw.get("clause")) or parsed.clause
    point = (_clean_reference_text(raw.get("point")) or parsed.point or "").lower() or None
    doc_id = _clean_reference_text(raw.get("doc_id"))
    so_ky_hieu = _clean_reference_text(raw.get("so_ky_hieu")) or parsed.so_ky_hieu
    document_hint = _clean_reference_text(raw.get("document_hint")) or parsed.document_hint
    year = _clean_reference_text(raw.get("year")) or parsed.year
    return LegalReference(
        article=article,
        clause=clause,
        point=point,
        doc_id=doc_id,
        so_ky_hieu=so_ky_hieu,
        document_hint=document_hint,
        year=year,
        canonical_citation=canonical,
        rewrite_source="llm",
    )


def _extract_document_hint(text: str) -> str:
    pattern = re.compile(
        r"(Luật|Bộ luật|Nghị định|Thông tư)\s+(.+?)(?:\s+\d{4}|\s+\d+/\d{4}/|\s+Điều|\s+khoản|$)",
        re.IGNORECASE,
    )
    match = pattern.search(text)
    if not match:
        return ""
    return f"{match.group(1)} {match.group(2)}".strip()


def _display_citation(
    article_index: Any,
    clause_index: Any,
    point_label: Any,
    document_title: str,
) -> str:
    parts = []
    if article_index is not None:
        parts.append(f"Điều {article_index}")
    if clause_index:
        parts.append(f"khoản {clause_index}")
    if point_label:
        parts.append(f"điểm {point_label}")
    if document_title:
        parts.append(document_title)
    return " ".join(parts).strip()


def _canonical_reference(reference: LegalReference) -> str:
    parts = []
    if reference.point:
        parts.append(f"điểm {reference.point}")
    if reference.clause:
        parts.append(f"khoản {reference.clause}")
    if reference.article is not None:
        parts.append(f"Điều {reference.article}")
    if reference.document_hint:
        parts.append(reference.document_hint)
    elif reference.so_ky_hieu:
        parts.append(reference.so_ky_hieu)
    if reference.year and reference.year not in " ".join(parts):
        parts.append(reference.year)
    return " ".join(parts).strip()


def _article_only_row(row: Any) -> dict[str, Any]:
    return {"a": row["a"], "doc": row["doc"], "clause": None, "point": None}


def _clause_only_row(row: Any) -> dict[str, Any]:
    return {"a": row["a"], "doc": row["doc"], "clause": row["clause"], "point": None}


def _article_uid(reference: LegalReference) -> str:
    if not reference.doc_id or reference.article is None:
        return ""
    return f"doc_{reference.doc_id}_dieu_{reference.article}"


def _match_int(pattern: str, text: str) -> Optional[int]:
    value = _match_text(pattern, text)
    return int(value) if value and value.isdigit() else None


def _match_text(pattern: str, text: str) -> str:
    match = re.search(pattern, text or "", re.IGNORECASE)
    return match.group(1).strip() if match else ""


def _clean_reference_text(value: Any) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    return "" if text.lower() in {"", "none", "null"} else text


def _has_citation_signal(text: str) -> bool:
    return bool(re.search(r"(?i)\b(điều|khoản|điểm)\b", text or ""))


def _normalize_so_ky_hieu(raw: str, document_hint: str = "") -> str:
    text = (raw or "").strip().upper()
    match = re.search(r"(\d+)\s*/\s*(\d{4})\s*/\s*([A-ZĐ0-9\-]+)", text)
    if not match:
        return text

    number = match.group(1).zfill(3)
    year = match.group(2)
    issuer = match.group(3)
    hint = (document_hint or "").lower()

    if "nghị định" in hint or "NĐ" in issuer:
        prefix = "ND"
    elif "thông tư liên tịch" in hint or "TTLT" in issuer:
        prefix = "TTLT"
    elif "thông tư" in hint or issuer.startswith("TT"):
        prefix = "TT"
    elif "bộ luật" in hint or "luật" in hint or issuer.startswith("QH"):
        prefix = "LT"
    else:
        prefix = re.sub(r"[^A-ZĐ0-9]+", "", issuer).split("-")[0] or "UNKNOWN"

    return f"{prefix}-{number}-{year}"


def _maybe_int(value: Any) -> Optional[int]:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
