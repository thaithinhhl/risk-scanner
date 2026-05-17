"""
Citation Verifier — T4.5 / T5.4

Automated verification of legal citations against Neo4j graph.
Parses Vietnamese legal citation format and verifies against graph nodes.

Usage:
    from src.llm.citation_verifier import CitationVerifier
    verifier = CitationVerifier()
    results = await verifier.verify(citations)
"""
from __future__ import annotations

import asyncio
import re
from dataclasses import asdict, dataclass
from typing import Any, Optional

from neo4j import GraphDatabase

from src.config import NEO4J_DATABASE, NEO4J_URI, NEO4J_TIMEOUT, NEO4J_DATABASE, neo4j_auth
from src.contract.citations import LegalCitation


@dataclass
class ParsedCitation:
    """
    Parsed legal citation.

    Attributes:
        raw_text: Original citation text
        article_number: Article number (Điều X)
        clause_number: Clause number (Khoản Y), optional
        point_letter: Point letter (Điểm Z), optional
        document_type: Luật, Nghị định, Thông tư
        so_ky_hieu: Normalized document identifier
    """
    raw_text: str
    article_number: Optional[int] = None
    clause_number: Optional[int] = None
    point_letter: Optional[str] = None
    document_type: str = ""
    so_ky_hieu: str = ""


@dataclass
class VerificationResult:
    """
    Result of citation verification.

    Attributes:
        citation: Original ParsedCitation
        verified: True if citation resolves to existing Neo4j node
        is_current: True if the provision is currently effective
        reason: Explanation if not verified
        article_uid: Resolved Article UID if found
    """
    citation: ParsedCitation
    verified: bool = False
    is_current: bool = False
    reason: str = ""
    article_uid: str = ""
    segment_uid: str = ""
    document_title: str = ""


class CitationVerifier:
    """
    Verify legal citations against Neo4j graph.

    Parses Vietnamese legal citation format:
    "Điều {N} khoản {K} {Loại_văn_bản} {so_ky_hieu}"
    """

    # Citation pattern: Điều N (khoản K)? (điểm L)? (Luật|NĐ|TT) (so_ky_hieu)?
    CITATION_PATTERN = re.compile(
        r"Điều\s+(\d+)"
        r"(?:\s+khoản\s+(\d+))?"
        r"(?:\s+điểm\s+([a-z]))?"
        r"(?:\s+(Luật|Bộ luật|Nghị định|Thông tư))?"
        r"(?:\s+([\w\-/]+))?",
        re.IGNORECASE,
    )

    def __init__(self) -> None:
        self._driver = GraphDatabase.driver(NEO4J_URI, auth=neo4j_auth())

    async def verify(self, citation_text: str | LegalCitation) -> VerificationResult:
        """
        Verify a single citation.

        Args:
            citation_text: Citation string or structured citation to verify

        Returns:
            VerificationResult with verified status and reason
        """
        if isinstance(citation_text, LegalCitation):
            return await self._verify_uid_citation(citation_text)

        parsed = self.parse_citation(citation_text)
        return await self._verify_parsed(parsed)

    async def verify_batch(self, citations: list[str | LegalCitation]) -> list[VerificationResult]:
        """
        Verify multiple citations in parallel.

        Args:
            citations: List of citation strings

        Returns:
            List of VerificationResult for each citation
        """
        tasks = [self.verify(c) for c in citations]
        return await asyncio.gather(*tasks)

    async def verify_qa_citations(self, citations: list[Any]) -> list[VerificationResult]:
        """Verify QA citation objects, preferring graph UID when available."""
        normalized: list[str | LegalCitation] = []
        for citation in citations:
            if isinstance(citation, LegalCitation):
                normalized.append(citation)
            elif hasattr(citation, "to_legal_citation"):
                normalized.append(citation.to_legal_citation())
            elif isinstance(citation, dict):
                normalized.append(
                    LegalCitation(
                        display_text=str(citation.get("display_text") or citation.get("text") or ""),
                        uid=str(citation.get("uid") or ""),
                        document_title=str(citation.get("document_title") or citation.get("document") or ""),
                        article=_optional_str(citation.get("article")),
                        clause=_optional_str(citation.get("clause")),
                        point=_optional_str(citation.get("point")),
                    )
                )
            else:
                normalized.append(str(citation or ""))
        return await self.verify_batch(normalized)

    @staticmethod
    def result_to_dict(result: VerificationResult) -> dict[str, Any]:
        return asdict(result)

    def parse_citation(self, citation_text: str) -> ParsedCitation:
        """
        Parse a Vietnamese legal citation.

        Args:
            citation_text: e.g., "Điều 301 khoản 2 Luật Thương mại 2005"

        Returns:
            ParsedCitation with extracted fields
        """
        match = self.CITATION_PATTERN.search(citation_text)
        if not match:
            return ParsedCitation(raw_text=citation_text)

        return ParsedCitation(
            raw_text=citation_text,
            article_number=int(match.group(1)),
            clause_number=int(match.group(2)) if match.group(2) else None,
            point_letter=match.group(3),
            document_type=match.group(4) or "",
            so_ky_hieu=match.group(5) or "",
            )

    async def _verify_uid_citation(self, citation: LegalCitation) -> VerificationResult:
        parsed = ParsedCitation(
            raw_text=citation.display_text,
            article_number=int(citation.article) if citation.article and str(citation.article).isdigit() else None,
            clause_number=int(citation.clause) if citation.clause and str(citation.clause).isdigit() else None,
            point_letter=citation.point,
        )

        if not citation.uid:
            return VerificationResult(
                citation=parsed,
                verified=False,
                reason="Citation uid is missing",
            )

        try:
            context = self._fetch_uid_context(citation.uid)
        except Exception as e:
            return VerificationResult(
                citation=parsed,
                verified=False,
                reason=f"Neo4j query failed: {str(e)}",
                segment_uid=citation.uid,
            )

        if not context:
            return VerificationResult(
                citation=parsed,
                verified=False,
                reason="Citation uid not found in graph",
                segment_uid=citation.uid,
            )

        mismatch = self._citation_mismatch_reason(citation, context)
        if mismatch:
            return VerificationResult(
                citation=parsed,
                verified=False,
                reason=mismatch,
                article_uid=context.get("article_uid", ""),
                segment_uid=citation.uid,
                document_title=context.get("document_title", ""),
            )

        return VerificationResult(
            citation=parsed,
            verified=True,
            is_current=context.get("is_current", True),
            article_uid=context.get("article_uid", ""),
            segment_uid=citation.uid,
            document_title=context.get("document_title", ""),
        )

    def _fetch_uid_context(self, uid: str) -> Optional[dict[str, Any]]:
        cypher = """
        MATCH (node {uid: $uid})
        OPTIONAL MATCH (doc_a:Document)-[:HAS_ARTICLE]->(node)
        OPTIONAL MATCH (doc_ch:Document)-[:HAS_CHAPTER]->(:Chapter)-[:HAS_ARTICLE]->(node)
        OPTIONAL MATCH (article_for_clause:Article)-[:HAS_CLAUSE]->(node)
        OPTIONAL MATCH (doc_c1:Document)-[:HAS_ARTICLE]->(article_for_clause)
        OPTIONAL MATCH (doc_c2:Document)-[:HAS_CHAPTER]->(:Chapter)-[:HAS_ARTICLE]->(article_for_clause)
        OPTIONAL MATCH (clause_for_point:Clause)-[:HAS_POINT]->(node)
        OPTIONAL MATCH (article_for_point:Article)-[:HAS_CLAUSE]->(clause_for_point)
        OPTIONAL MATCH (doc_p1:Document)-[:HAS_ARTICLE]->(article_for_point)
        OPTIONAL MATCH (doc_p2:Document)-[:HAS_CHAPTER]->(:Chapter)-[:HAS_ARTICLE]->(article_for_point)
        WITH node,
             coalesce(doc_a, doc_ch, doc_c1, doc_c2, doc_p1, doc_p2) AS doc,
             coalesce(article_for_clause, article_for_point, CASE WHEN node:Article THEN node ELSE null END) AS article,
             coalesce(clause_for_point, CASE WHEN node:Clause THEN node ELSE null END) AS clause
        RETURN node.uid AS uid,
               coalesce(article.uid, node.uid) AS article_uid,
               coalesce(article.index, CASE WHEN node:Article THEN node.index ELSE null END) AS article,
               coalesce(clause.index, CASE WHEN node:Clause THEN node.index ELSE null END) AS clause,
               CASE WHEN node:Point THEN node.letter ELSE null END AS point,
               doc.title AS document_title,
               coalesce(node.is_current, article.is_current, true) AS is_current
        """
        with self._driver.session(default_access_mode="READ", database=NEO4J_DATABASE) as session:
            record = session.run(
                cypher,
                uid=uid,
                config={"maxTransactionRetryTime": NEO4J_TIMEOUT * 1000},
            ).single()
            return dict(record) if record else None

    def _citation_mismatch_reason(self, citation: LegalCitation, context: dict[str, Any]) -> str:
        checks = [
            ("article", citation.article, context.get("article")),
            ("clause", citation.clause, context.get("clause")),
            ("point", citation.point, context.get("point")),
        ]
        for name, expected, actual in checks:
            if expected is not None and str(expected).strip().lower() != str(actual or "").strip().lower():
                return f"Citation {name} mismatch: expected {expected}, got {actual}"

        if citation.document_title and context.get("document_title"):
            expected_title = citation.document_title.strip().lower()
            actual_title = str(context["document_title"]).strip().lower()
            if expected_title and expected_title not in actual_title and actual_title not in expected_title:
                return "Citation document title mismatch"

        return ""

    async def _verify_parsed(self, parsed: ParsedCitation) -> VerificationResult:
        """Verify a parsed citation against Neo4j."""
        if not parsed.article_number:
            return VerificationResult(
                citation=parsed,
                verified=False,
                reason="Could not parse article number",
            )

        # Build query based on available info
        if parsed.so_ky_hieu:
            cypher = """
            MATCH (a:Article {index: $article_index})
            <-[:HAS_ARTICLE]-(d:Document {so_ky_hieu: $so_ky_hieu})
            RETURN a.uid AS uid, a.is_current AS is_current
            """
            params = {"article_index": parsed.article_number, "so_ky_hieu": parsed.so_ky_hieu}
        else:
            cypher = """
            MATCH (a:Article {index: $article_index})
            RETURN a.uid AS uid, a.is_current AS is_current
            LIMIT 1
            """
            params = {"article_index": parsed.article_number}

        try:
            with self._driver.session(default_access_mode="READ", database=NEO4J_DATABASE) as session:
                result = session.run(cypher, params, config={"maxTransactionRetryTime": NEO4J_TIMEOUT * 1000})
                record = result.single()

                if record:
                    return VerificationResult(
                        citation=parsed,
                        verified=True,
                        is_current=record["is_current"],
                        article_uid=record["uid"],
                    )
                else:
                    return VerificationResult(
                        citation=parsed,
                        verified=False,
                        reason="Article not found in graph",
                    )
        except Exception as e:
            return VerificationResult(
                citation=parsed,
                verified=False,
                reason=f"Neo4j query failed: {str(e)}",
            )


def _optional_str(value: Any) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip()
    return text or None
