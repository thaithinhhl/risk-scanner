"""
T1.7 — Ingest Document-Level Relationships
===========================================

Migrate 659K relationships từ relationships.parquet vào Neo4j.

Mapping (tiếng Việt → Neo4j relationship type):
  "Văn bản căn cứ"                    → CITES
  "Văn bản dẫn chiếu"                 → REFERRED_BY
  "Văn bản HD, QĐ chi tiết"           → DETAILS
  "Văn bản được HD, QĐ chi tiết"      → DETAILED_BY
  "Văn bản hết hiệu lực"              → SUPERSEDED_BY
  "Văn bản quy định hết hiệu lực"     → SUPERSEDES
  "Văn bản bị hết hiệu lực 1 phần"   → PARTIALLY_SUPERSEDED_BY
  "Văn bản quy định hết hiệu lực 1 phần" → PARTIALLY_SUPERSEDES
  "Văn bản sửa đổi"                   → AMENDS
  "Văn bản được sửa đổi"              → AMENDED_BY
  "Văn bản bổ sung"                   → SUPPLEMENTS
  "Văn bản được bổ sung"              → SUPPLEMENTED_BY
  "Văn bản liên quan khác"            → RELATED
  "Văn bản đình chỉ"                  → SUSPENDS
  "Văn bản bị đình chỉ"               → SUSPENDED_BY
  "Văn bản đình chỉ 1 phần"           → PARTIALLY_SUSPENDS
  "Văn bản bị đình chỉ 1 phần"        → PARTIALLY_SUSPENDED_BY

Spec: segmentation
Task: T1.7
Depends on: T1.4 (Neo4j schema phải có trước)
"""
from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Optional
from dotenv import load_dotenv

logger = logging.getLogger(__name__)

# Load environment variables from .env
load_dotenv()

# ---------------------------------------------------------------------------
# Neo4j credentials (from environment variables, with fallback to defaults)
# ---------------------------------------------------------------------------

NEO4J_URI      = os.getenv("NEO4J_URI",      "bolt://localhost:7687")
NEO4J_USER     = os.getenv("NEO4J_USER",     "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "password")

# ---------------------------------------------------------------------------
# Relationship type mapping
# ---------------------------------------------------------------------------

RELATIONSHIP_TYPE_MAP: dict[str, str] = {
    "Văn bản căn cứ":                        "CITES",
    "Văn bản dẫn chiếu":                     "REFERRED_BY",
    "Văn bản HD, QĐ chi tiết":               "DETAILS",
    "Văn bản được HD, QĐ chi tiết":          "DETAILED_BY",
    "Văn bản hết hiệu lực":                  "SUPERSEDED_BY",
    "Văn bản quy định hết hiệu lực":         "SUPERSEDES",
    "Văn bản bị hết hiệu lực 1 phần":        "PARTIALLY_SUPERSEDED_BY",
    "Văn bản quy định hết hiệu lực 1 phần":  "PARTIALLY_SUPERSEDES",
    "Văn bản sửa đổi":                       "AMENDS",
    "Văn bản được sửa đổi":                  "AMENDED_BY",
    "Văn bản bổ sung":                       "SUPPLEMENTS",
    "Văn bản được bổ sung":                  "SUPPLEMENTED_BY",
    "Văn bản liên quan khác":                "RELATED",
    "Văn bản đình chỉ":                      "SUSPENDS",
    "Văn bản bị đình chỉ":                   "SUSPENDED_BY",
    "Văn bản đình chỉ 1 phần":               "PARTIALLY_SUSPENDS",
    "Văn bản bị đình chỉ 1 phần":            "PARTIALLY_SUSPENDED_BY",
    "CAN_CU":                                "CITES",
    "SUA_DOI":                               "AMENDS",
    "HUONG_DAN":                             "DETAILS",
    "THAY_THE":                              "SUPERSEDES",
    "LIEN_QUAN":                             "RELATED",
}

# Cypher template cho MERGE relationship
_MERGE_REL_CYPHER = """
UNWIND $batch AS row
MATCH (a:Document {{id: row.doc_id}})
MATCH (b:Document {{id: row.other_doc_id}})
MERGE (a)-[r:{rel_type}]->(b)
"""

DEFAULT_BATCH_SIZE = 5_000


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

def validate_endpoints(driver, df) -> dict:
    """
    Kiểm tra cả 2 đầu của mỗi relationship tồn tại trong Neo4j.

    Parameters
    ----------
    driver : neo4j.GraphDatabase.driver
    df     : pd.DataFrame với columns: doc_id, other_doc_id

    Returns
    -------
    dict với keys: total, valid, orphan_count, orphan_doc_ids
    """
    all_ids = set(df["doc_id"].tolist()) | set(df["other_doc_id"].tolist())

    with driver.session() as session:
        result = session.run(
            "UNWIND $ids AS id MATCH (d:Document {id: id}) RETURN d.id AS id",
            ids=list(all_ids),
        )
        existing_ids = {r["id"] for r in result}

    orphans = all_ids - existing_ids
    logger.info(
        "Endpoint validation: %d unique IDs, %d exist, %d orphans",
        len(all_ids), len(existing_ids), len(orphans),
    )
    return {
        "total":          len(all_ids),
        "valid":          len(existing_ids),
        "orphan_count":   len(orphans),
        "orphan_doc_ids": sorted(orphans),
    }


def log_orphans(orphan_doc_ids: list[str], path: str | Path) -> None:
    """Ghi danh sách orphan doc_ids ra JSON."""
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"orphans": orphan_doc_ids, "count": len(orphan_doc_ids)},
                  f, ensure_ascii=False, indent=2)
    logger.info("Orphan log: %d records → %s", len(orphan_doc_ids), path)


# ---------------------------------------------------------------------------
# Ingest
# ---------------------------------------------------------------------------

def ingest_relationships(
    driver,
    df,
    *,
    batch_size: int = DEFAULT_BATCH_SIZE,
    rel_type_col: str = "relationship_type",
    doc_id_col: str   = "doc_id",
    other_id_col: str = "other_doc_id",
) -> dict:
    """
    Ingest tất cả relationships từ DataFrame vào Neo4j.

    Parameters
    ----------
    driver : neo4j.GraphDatabase.driver
    df     : pd.DataFrame với columns: doc_id, other_doc_id, relationship_type
    batch_size : int
        Số relationship mỗi transaction.

    Returns
    -------
    dict : {total, ingested, skipped_unknown_type, failed_batches}
    """
    stats = {"total": 0, "ingested": 0, "skipped_unknown_type": 0, "failed_batches": 0}

    # Nhóm theo relationship_type để dùng Cypher khác nhau
    for raw_type, group_df in df.groupby(rel_type_col):
        neo4j_type = RELATIONSHIP_TYPE_MAP.get(str(raw_type))
        if not neo4j_type:
            logger.warning("Unknown relationship type: '%s' (%d rows)", raw_type, len(group_df))
            stats["skipped_unknown_type"] += len(group_df)
            continue

        cypher = _MERGE_REL_CYPHER.format(rel_type=neo4j_type)
        rows   = group_df[[doc_id_col, other_id_col]].rename(
            columns={doc_id_col: "doc_id", other_id_col: "other_doc_id"}
        ).to_dict("records")

        # Batch ingest
        for i in range(0, len(rows), batch_size):
            batch = rows[i: i + batch_size]
            try:
                with driver.session() as session:
                    session.run(cypher, batch=batch)
                stats["ingested"] += len(batch)
                logger.debug(
                    "Ingested batch %d-%d for type %s",
                    i, i + len(batch), neo4j_type,
                )
            except Exception as exc:
                logger.error("Batch failed [%s] at %d: %s", neo4j_type, i, exc)
                stats["failed_batches"] += 1

        stats["total"] += len(rows)

    logger.info(
        "T1.7 ingest done — total: %d, ingested: %d, unknown_type: %d, failed_batches: %d",
        stats["total"], stats["ingested"],
        stats["skipped_unknown_type"], stats["failed_batches"],
    )
    return stats


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main(
    relationships_path: str = "data/relationships.parquet",
    neo4j_uri: str          = NEO4J_URI,
    neo4j_user: str         = NEO4J_USER,
    neo4j_password: str     = NEO4J_PASSWORD,
    orphan_log_path: str    = "output/orphan_relationships.json",
) -> None:
    """
    T1.7 main: Load relationships.parquet, validate, ingest vào Neo4j.
    """
    import pandas as pd  # noqa: PLC0415
    from neo4j import GraphDatabase  # noqa: PLC0415

    logger.info("T1.7 — Loading relationships from %s", relationships_path)
    df = pd.read_parquet(relationships_path)
    logger.info("Loaded %d relationships", len(df))

    # Nếu không có dữ liệu, skip gracefully
    if df.empty:
        logger.info("T1.7: relationships.parquet is empty — skipping Neo4j ingest (no data yet)")
        return

    logger.info("T1.7 — Connecting to Neo4j at %s as user '%s'", neo4j_uri, neo4j_user)
    driver = GraphDatabase.driver(neo4j_uri, auth=(neo4j_user, neo4j_password))

    try:
        # Validate endpoints
        validation = validate_endpoints(driver, df)
        log_orphans(validation["orphan_doc_ids"], orphan_log_path)

        if validation["orphan_count"] > 0:
            logger.warning(
                "%d orphan doc_ids will cause skipped relationships",
                validation["orphan_count"],
            )

        # Filter ra các rows có cả 2 endpoints tồn tại
        valid_ids = set(
            [r for r in df["doc_id"] if r not in validation["orphan_doc_ids"]] +
            [r for r in df["other_doc_id"] if r not in validation["orphan_doc_ids"]]
        )
        df_valid = df[
            df["doc_id"].isin(valid_ids) & df["other_doc_id"].isin(valid_ids)
        ]

        # Ingest
        stats = ingest_relationships(driver, df_valid)
        logger.info("T1.7 done — stats: %s", stats)

    finally:
        driver.close()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(name)s — %(message)s")
    main()
