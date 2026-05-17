"""
Hybrid legal retrieval for contract review.

Searches LegalSegment nodes (Article, Clause, Point) using vector search,
full-text search, exact boosts, REFERENCES/MODIFIES graph expansion, and
transparent reranking.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Optional

from neo4j import GraphDatabase

from src.config import NEO4J_TIMEOUT, NEO4J_DATABASE, NEO4J_URI, neo4j_auth
from src.config import EMBED_QUERY_INSTRUCTION
from src.contract.mock_bridge import EmbeddingService, create_embedding_service
from src.contract.query_rewriter import LegalRetrievalPlan
from src.data_pipeline.legal_segment_index import (
    LEGAL_SEGMENT_FULLTEXT_INDEX,
    LEGAL_SEGMENT_VECTOR_INDEX,
)


AUTHORITY_WEIGHTS = {
    "Bộ luật": 3.0,
    "Luật": 3.0,
    "Nghị định": 2.0,
    "Thông tư": 1.5,
    "Thông tư liên tịch": 1.0,
}


@dataclass
class ScoreFactors:
    vector: float = 0.0
    lexical: float = 0.0
    exact: float = 0.0
    title: float = 0.0
    graph: float = 1.0
    authority: float = 1.0
    validity: float = 1.0


@dataclass
class LegalCandidate:
    uid: str
    labels: list[str] = field(default_factory=list)
    segment_type: str = ""
    text: str = ""
    title: str = ""
    index: Any = None
    document_id: str = ""
    document_title: str = ""
    document_so_ky_hieu: str = ""
    document_type: str = ""
    article_uid: str = ""
    article_index: Any = None
    article_title: str = ""
    clause_uid: str = ""
    clause_index: Any = None
    point_letter: str = ""
    sources: set[str] = field(default_factory=set)
    score_factors: ScoreFactors = field(default_factory=ScoreFactors)
    validity_signal: str = "latest_known"
    references_context: list[dict[str, Any]] = field(default_factory=list)
    modifies_context: list[dict[str, Any]] = field(default_factory=list)
    combined_score: float = 0.0

    def display_citation(self) -> str:
        parts = []
        if self.article_index:
            parts.append(f"Điều {self.article_index}")
        if self.clause_index:
            parts.append(f"khoản {self.clause_index}")
        if self.point_letter:
            parts.append(f"điểm {self.point_letter}")
        if self.document_title:
            parts.append(self.document_title)
        return " ".join(str(p) for p in parts if p).strip() or self.uid


class LegalHybridRetriever:
    def __init__(
        self,
        embedding_service: Optional[EmbeddingService] = None,
        top_k: int = 10,
        return_top_n: int = 5,
    ) -> None:
        self._driver = GraphDatabase.driver(NEO4J_URI, auth=neo4j_auth())
        self._embedding_service = embedding_service or create_embedding_service()
        self._top_k = top_k
        self._return_top_n = return_top_n

    def close(self) -> None:
        self._driver.close()

    async def retrieve(self, plan: LegalRetrievalPlan) -> list[LegalCandidate]:
        candidates: dict[str, LegalCandidate] = {}

        # Batch vector embeddings for all queries
        queries = plan.normalized_queries()[:3]
        if queries:
            await self._add_vector_candidates_batch(candidates, queries)

        for query in [*plan.normalized_queries(), *plan.keywords, *plan.title_hints]:
            self._add_fulltext_candidates(candidates, query)

        self._apply_exact_boosts(candidates, plan)
        self._add_graph_expansion(candidates)
        self._apply_exact_boosts(candidates, plan)

        reranked = self._rerank(candidates.values())
        return reranked[: self._return_top_n]

    async def _add_vector_candidates_batch(self, candidates: dict[str, LegalCandidate], queries: list[str]) -> None:
        """Add vector candidates for multiple queries in batch."""
        try:
            formatted_queries = [self._format_query(query) for query in queries]
            embeddings = await self._embedding_service.embed_batch(formatted_queries)
        except Exception:
            return

        cypher = f"""
        CALL db.index.vector.queryNodes("{LEGAL_SEGMENT_VECTOR_INDEX}", $top_k, $vector)
        YIELD node, score
        RETURN node, labels(node) AS labels, score
        ORDER BY score DESC
        """
        with self._driver.session(default_access_mode="READ", database=NEO4J_DATABASE) as session:
            for embedding in embeddings:
                try:
                    rows = session.run(
                        cypher,
                        {"top_k": self._top_k, "vector": embedding},
                        config={"maxTransactionRetryTime": NEO4J_TIMEOUT * 1000},
                    )
                    hydrated = self._hydrate_nodes([{"node": row["node"], "labels": row["labels"], "score": row["score"]} for row in rows])
                except Exception:
                    continue

                for candidate in hydrated:
                    existing = candidates.get(candidate.uid)
                    if existing:
                        existing.score_factors.vector = max(existing.score_factors.vector, candidate.score_factors.vector)
                        existing.sources.add("vector")
                    else:
                        candidate.sources.add("vector")
                        candidates[candidate.uid] = candidate

    def _format_query(self, query: str) -> str:
        """Format semantic search queries for Harrier-style instruction tuning."""
        cleaned = (query or "").strip()
        if not cleaned or cleaned.startswith("Instruct:"):
            return cleaned
        return f"Instruct: {EMBED_QUERY_INSTRUCTION}\nQuery: {cleaned}"

    async def _add_vector_candidates(self, candidates: dict[str, LegalCandidate], query: str) -> None:
        try:
            embedding = await self._embedding_service.embed(self._format_query(query))
        except Exception:
            return

        cypher = f"""
        CALL db.index.vector.queryNodes("{LEGAL_SEGMENT_VECTOR_INDEX}", $top_k, $vector)
        YIELD node, score
        RETURN node, labels(node) AS labels, score
        ORDER BY score DESC
        """
        with self._driver.session(default_access_mode="READ", database=NEO4J_DATABASE) as session:
            rows = session.run(
                cypher,
                top_k=self._top_k,
                vector=embedding,
                config={"maxTransactionRetryTime": NEO4J_TIMEOUT * 1000},
            )
            hydrated = self._hydrate_nodes([{"node": row["node"], "labels": row["labels"], "score": row["score"]} for row in rows])

        for candidate in hydrated:
            existing = candidates.get(candidate.uid)
            if existing:
                existing.score_factors.vector = max(existing.score_factors.vector, candidate.score_factors.vector)
                existing.sources.add("vector")
            else:
                candidate.sources.add("vector")
                candidates[candidate.uid] = candidate

    def _add_fulltext_candidates(self, candidates: dict[str, LegalCandidate], query: str) -> None:
        safe_query = self._sanitize_fulltext_query(query)
        if not safe_query:
            return

        cypher = f"""
        CALL db.index.fulltext.queryNodes("{LEGAL_SEGMENT_FULLTEXT_INDEX}", $query, {{limit: $top_k}})
        YIELD node, score
        RETURN node, labels(node) AS labels, score
        ORDER BY score DESC
        """
        with self._driver.session(default_access_mode="READ", database=NEO4J_DATABASE) as session:
            try:
                rows = session.run(
                    cypher,
                    {"query": safe_query, "top_k": self._top_k},
                    config={"maxTransactionRetryTime": NEO4J_TIMEOUT * 1000},
                )
                hydrated = self._hydrate_nodes([{"node": row["node"], "labels": row["labels"], "score": row["score"]} for row in rows], score_kind="lexical")
            except Exception:
                return

        for candidate in hydrated:
            existing = candidates.get(candidate.uid)
            if existing:
                existing.score_factors.lexical = max(existing.score_factors.lexical, candidate.score_factors.lexical)
                existing.sources.add("fulltext")
            else:
                candidate.sources.add("fulltext")
                candidates[candidate.uid] = candidate

    def _add_graph_expansion(self, candidates: dict[str, LegalCandidate]) -> None:
        seed_uids = [c.uid for c in self._rerank(candidates.values())[: self._return_top_n]]
        if not seed_uids:
            return

        cypher = """
        UNWIND $uids AS uid
        MATCH (seed {uid: uid})
        MATCH (seed)-[r:REFERENCES|MODIFIES]-(node:LegalSegment)
        WITH DISTINCT node, labels(node) AS labels, type(r) AS rel_type, properties(r) AS props
        RETURN node, labels, rel_type,
               coalesce(props.ref_type, props.raw_type, props.action, rel_type) AS rel_detail
        LIMIT $limit
        """
        with self._driver.session(default_access_mode="READ", database=NEO4J_DATABASE) as session:
            rows = list(session.run(cypher, uids=seed_uids, limit=self._top_k))

        hydrated = self._hydrate_nodes(
            [{"node": row["node"], "labels": row["labels"], "score": 0.6} for row in rows],
            score_kind="graph",
        )
        for row, candidate in zip(rows, hydrated):
            rel_context = {"type": row["rel_type"], "detail": row["rel_detail"]}
            existing = candidates.get(candidate.uid)
            target = existing or candidate
            target.sources.add("graph")
            target.score_factors.graph = max(target.score_factors.graph, 1.25)
            if row["rel_type"] == "MODIFIES":
                target.validity_signal = "possibly_modified"
                target.modifies_context.append(rel_context)
                target.score_factors.validity = min(target.score_factors.validity, 0.95)
            else:
                target.references_context.append(rel_context)
            if not existing:
                candidates[candidate.uid] = target

    def _hydrate_nodes(self, rows: list[dict[str, Any]], score_kind: str = "vector") -> list[LegalCandidate]:
        if not rows:
            return []

        node_rows = []
        for idx, row in enumerate(rows):
            node = row["node"]
            node_rows.append({"uid": node.get("uid"), "score": float(row.get("score") or 0.0), "labels": row.get("labels") or [], "idx": idx})

        cypher = """
        UNWIND $rows AS row
        MATCH (node {uid: row.uid})
        OPTIONAL MATCH (doc_a:Document)-[:HAS_ARTICLE]->(node)
        OPTIONAL MATCH (doc_ch:Document)-[:HAS_CHAPTER]->(:Chapter)-[:HAS_ARTICLE]->(node)
        OPTIONAL MATCH (article_for_clause:Article)-[:HAS_CLAUSE]->(node)
        OPTIONAL MATCH (doc_c1:Document)-[:HAS_ARTICLE]->(article_for_clause)
        OPTIONAL MATCH (doc_c2:Document)-[:HAS_CHAPTER]->(:Chapter)-[:HAS_ARTICLE]->(article_for_clause)
        OPTIONAL MATCH (clause_for_point:Clause)-[:HAS_POINT]->(node)
        OPTIONAL MATCH (article_for_point:Article)-[:HAS_CLAUSE]->(clause_for_point)
        OPTIONAL MATCH (doc_p1:Document)-[:HAS_ARTICLE]->(article_for_point)
        OPTIONAL MATCH (doc_p2:Document)-[:HAS_CHAPTER]->(:Chapter)-[:HAS_ARTICLE]->(article_for_point)
        WITH row, node,
             coalesce(doc_a, doc_ch, doc_c1, doc_c2, doc_p1, doc_p2) AS doc,
             coalesce(article_for_clause, article_for_point, CASE WHEN node:Article THEN node ELSE null END) AS article,
             coalesce(clause_for_point, CASE WHEN node:Clause THEN node ELSE null END) AS clause
        RETURN row, node, labels(node) AS labels, doc, article, clause
        ORDER BY row.idx
        """
        with self._driver.session(default_access_mode="READ", database=NEO4J_DATABASE) as session:
            records = list(session.run(cypher, rows=node_rows))

        candidates: list[LegalCandidate] = []
        for record in records:
            row = record["row"]
            node = dict(record["node"])
            doc = dict(record["doc"]) if record["doc"] else {}
            article = dict(record["article"]) if record["article"] else {}
            clause = dict(record["clause"]) if record["clause"] else {}
            labels = list(record["labels"] or row.get("labels") or [])
            factors = ScoreFactors(authority=AUTHORITY_WEIGHTS.get(doc.get("loai_van_ban", ""), 1.0))
            score = float(row.get("score") or 0.0)
            if score_kind == "vector":
                # Neo4j vector index returns cosine similarity (0-1)
                factors.vector = score
            elif score_kind == "lexical":
                # Neo4j fulltext returns BM25 score — normalize using sigmoid
                # BM25 scores typically range 5-15 for legal text
                # sigmoid(x/5) maps: 0→0.5, 5→0.73, 10→0.88, 15→0.95
                factors.lexical = 1.0 / (1.0 + 2.71828 ** (-score / 5.0)) - 0.5
                # Re-scale to 0-1: sigmoid gives 0.5-1.0 for positive scores
                # Subtract 0.5 and double to get 0-1 range
                factors.lexical = max(0.0, min(1.0, factors.lexical * 2.0))
            elif score_kind == "graph":
                factors.graph = 1.25

            candidates.append(
                LegalCandidate(
                    uid=node.get("uid", ""),
                    labels=labels,
                    segment_type=node.get("segment_type") or self._segment_type(labels),
                    text=node.get("clean_text") or node.get("text_content") or "",
                    title=node.get("title") or "",
                    index=node.get("index"),
                    document_id=str(doc.get("id", "")),
                    document_title=doc.get("title", ""),
                    document_so_ky_hieu=doc.get("so_ky_hieu", ""),
                    document_type=doc.get("loai_van_ban", ""),
                    article_uid=article.get("uid", node.get("uid") if "Article" in labels else ""),
                    article_index=article.get("index", node.get("index") if "Article" in labels else None),
                    article_title=article.get("title", node.get("title") if "Article" in labels else ""),
                    clause_uid=clause.get("uid", node.get("uid") if "Clause" in labels else ""),
                    clause_index=clause.get("index", node.get("index") if "Clause" in labels else None),
                    point_letter=node.get("letter", "") if "Point" in labels else "",
                    score_factors=factors,
                )
            )
        return candidates

    def _apply_exact_boosts(self, candidates: dict[str, LegalCandidate], plan: LegalRetrievalPlan) -> None:
        keywords = [kw.lower() for kw in [*plan.keywords, *plan.search_queries] if kw]
        title_hints = [hint.lower() for hint in [*plan.title_hints, *plan.expected_domains] if hint]
        for candidate in candidates.values():
            haystack = " ".join([
                candidate.text,
                candidate.title,
                candidate.document_title,
                candidate.document_so_ky_hieu,
            ]).lower()
            exact_hits = sum(1 for kw in keywords if kw and kw in haystack)
            title_hits = sum(1 for hint in title_hints if hint and hint in haystack)
            candidate.score_factors.exact = min(exact_hits * 0.08, 0.24)
            candidate.score_factors.title = min(title_hits * 0.12, 0.24)

    def _rerank(self, candidates) -> list[LegalCandidate]:
        ranked = list(candidates)
        for candidate in ranked:
            f = candidate.score_factors
            base = (f.vector * 0.50) + (f.lexical * 0.25) + f.exact + f.title
            candidate.combined_score = base * f.graph * f.authority * f.validity
        return sorted(ranked, key=lambda item: item.combined_score, reverse=True)

    def _sanitize_fulltext_query(self, query: str) -> str:
        cleaned = re.sub(r"[+\\!(){}\[\]^\"~*?:/|-]", " ", query or "")
        cleaned = re.sub(r"\s+", " ", cleaned).strip()
        return cleaned[:300]

    def _segment_type(self, labels: list[str]) -> str:
        for label in ("Point", "Clause", "Article"):
            if label in labels:
                return label
        return "LegalSegment"
