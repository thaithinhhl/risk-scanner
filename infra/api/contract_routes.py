"""Contract review API routes."""
from __future__ import annotations

import asyncio
import logging
import os
import tempfile
import uuid
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, File, HTTPException, Response, UploadFile
from neo4j import GraphDatabase

from infra.api.contract_store import (
    ContractStoreError,
    get_contract_store,
    infer_source_format,
)
from infra.api.models import (
    CitationResponse,
    ComplianceResultResponse,
    ContractClauseResponse,
    JobStatusResponse,
    LegalMatchResponse,
    UploadResponse,
)
from src.auth import CurrentUser, get_current_user
from src.config import NEO4J_URI, neo4j_auth
from src.contract.parser import repair_mojibake_text
from src.contract.review_pipeline import ContractReviewPipeline, ContractReviewPipelineError

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/upload", response_model=UploadResponse)
async def upload_contract(
    file: UploadFile = File(...),
    user: CurrentUser = Depends(get_current_user),
):
    """Upload a contract file for persisted review."""
    allowed_types = {".pdf", ".docx", ".doc", ".txt", ".md"}
    file_ext = Path(file.filename or "").suffix.lower()
    if file_ext not in allowed_types:
        raise HTTPException(status_code=400, detail=f"Unsupported file type: {file_ext}. Allowed: {allowed_types}")

    content = await file.read()
    if len(content) > 10 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="File too large. Maximum size: 10MB")

    document_id = str(uuid.uuid4())
    version_id = str(uuid.uuid4())
    run_id = str(uuid.uuid4())

    try:
        store = get_contract_store()
        storage_path = store.upload_file(
            user_id=user.id,
            document_id=document_id,
            version_number=1,
            filename=file.filename or "unknown",
            content=content,
            content_type=file.content_type,
        )
        document = store.create_document(
            user_id=user.id,
            original_filename=file.filename or "unknown",
            display_name=file.filename or "unknown",
            document_id=document_id,
        )
        version = store.create_version(
            document_id=document["id"],
            user_id=user.id,
            filename=file.filename or "unknown",
            content_type=file.content_type,
            file_size_bytes=len(content),
            storage_path=storage_path,
            version_number=1,
            source_type="original_upload",
            source_format=infer_source_format(file.filename or "", file.content_type),
            version_id=version_id,
        )
        run = store.create_run(
            document_id=document["id"],
            version_id=version["id"],
            user_id=user.id,
            status="uploading",
            progress=0,
            run_id=run_id,
        )
    except ContractStoreError as exc:
        logger.error("Could not create persisted contract review run: %s", exc)
        raise HTTPException(status_code=500, detail="Could not persist contract review") from exc

    asyncio.create_task(
        process_contract(
            run_id=run["id"],
            version_id=version["id"],
            document_id=document["id"],
            user_id=user.id,
            content=content,
            filename=file.filename or "unknown",
        )
    )

    return UploadResponse(jobId=run["id"], documentId=document["id"], versionId=version["id"])


@router.get("/{job_id}/status", response_model=JobStatusResponse)
async def get_job_status(job_id: str, user: CurrentUser = Depends(get_current_user)):
    """Get persisted status of a contract review run."""
    try:
        store = get_contract_store()
        bundle = store.get_run_bundle(job_id, user.id)
    except ContractStoreError as exc:
        logger.error("Could not load contract run %s: %s", job_id, exc)
        raise HTTPException(status_code=500, detail="Could not load contract review run") from exc

    if not bundle:
        raise HTTPException(status_code=404, detail="Job not found")

    run = bundle["run"]
    version = bundle["version"]
    snapshot = bundle["snapshot"]
    snapshot_result = snapshot.get("result_json") if snapshot else {}
    file_url = None
    try:
        file_url = store.create_signed_file_url(version.get("storage_path", ""))
    except ContractStoreError:
        logger.warning("Could not create signed URL for contract run %s", job_id)

    return job_status_from_bundle(
        run=run,
        version=version,
        snapshot_result=snapshot_result if isinstance(snapshot_result, dict) else {},
        file_url=file_url,
    )


@router.get("/history", response_model=list[JobStatusResponse])
async def get_job_history(user: CurrentUser = Depends(get_current_user)):
    """Get persisted contract review runs for the current user."""
    try:
        store = get_contract_store()
        bundles = store.list_runs(user.id)
    except ContractStoreError as exc:
        logger.error("Could not list contract runs: %s", exc)
        raise HTTPException(status_code=500, detail="Could not load contract review history") from exc

    return [
        job_status_from_bundle(run=bundle["run"], version=bundle["version"], snapshot_result={}, file_url=None)
        for bundle in bundles
    ]


@router.delete("/documents/{document_id}", status_code=204)
async def delete_contract_document(document_id: str, user: CurrentUser = Depends(get_current_user)):
    """Soft-delete a persisted contract document."""
    try:
        store = get_contract_store()
        store.soft_delete_document(document_id, user.id)
    except ContractStoreError as exc:
        if "not found" in str(exc).lower():
            raise HTTPException(status_code=404, detail="Document not found") from exc
        logger.error("Could not delete contract document %s: %s", document_id, exc)
        raise HTTPException(status_code=500, detail="Could not delete contract document") from exc
    return Response(status_code=204)


@router.get("/documents/{doc_title}")
async def get_document_content(doc_title: str):
    """Get full content of a legal document by title."""
    driver = GraphDatabase.driver(NEO4J_URI, auth=neo4j_auth())
    try:
        with driver.session(default_access_mode="READ", database="neo4j") as session:
            result = session.run(
                """
                MATCH (doc:Document)
                WHERE doc.title = $title
                OPTIONAL MATCH (doc)-[:HAS_ARTICLE]->(article:Article)
                OPTIONAL MATCH (article)-[:HAS_CLAUSE]->(clause:Clause)
                OPTIONAL MATCH (clause)-[:HAS_POINT]->(point:Point)
                RETURN doc, collect(DISTINCT article) as articles, collect(DISTINCT clause) as clauses, collect(DISTINCT point) as points
                """,
                title=doc_title,
            )

            record = result.single()
            if not record:
                raise HTTPException(status_code=404, detail="Document not found")

            doc = dict(record["doc"])
            articles = [dict(a) for a in record["articles"] if a]
            clauses = [dict(c) for c in record["clauses"] if c]
            points = [dict(p) for p in record["points"] if p]

            content = {
                "title": doc.get("title", ""),
                "so_ky_hieu": doc.get("so_ky_hieu", ""),
                "loai_van_ban": doc.get("loai_van_ban", ""),
                "ngay_ban_hanh": doc.get("ngay_ban_hanh", ""),
                "co_quan_ban_hanh": doc.get("co_quan_ban_hanh", ""),
                "articles": [],
            }

            article_map = {}
            for article in articles:
                article_map[article["uid"]] = {
                    "uid": article["uid"],
                    "index": article.get("index", 0),
                    "title": article.get("title", ""),
                    "text": article.get("clean_text", ""),
                    "clauses": [],
                }

            for clause in clauses:
                article_uid = clause.get("article_uid", "")
                if article_uid in article_map:
                    article_map[article_uid]["clauses"].append(
                        {
                            "uid": clause["uid"],
                            "index": clause.get("index", 0),
                            "text": clause.get("clean_text", ""),
                            "points": [],
                        }
                    )

            for point in points:
                clause_uid = point.get("clause_uid", "")
                for article_data in article_map.values():
                    for clause_data in article_data["clauses"]:
                        if clause_data["uid"] == clause_uid:
                            clause_data["points"].append(
                                {
                                    "uid": point["uid"],
                                    "letter": point.get("letter", ""),
                                    "text": point.get("clean_text", ""),
                                }
                            )

            content["articles"] = list(article_map.values())
            content["articles"].sort(key=lambda x: x["index"])
            return content
    finally:
        driver.close()


async def process_contract(
    *,
    run_id: str,
    version_id: str,
    document_id: str,
    user_id: str,
    content: bytes,
    filename: str,
):
    """Process a contract file asynchronously and persist results."""
    store = get_contract_store()
    progress_state = {"value": 0}

    async def report_progress(status: str, progress: int) -> None:
        progress_state["value"] = max(progress_state["value"], max(0, min(100, progress)))
        store.update_run(run_id=run_id, user_id=user_id, status=status, progress=progress_state["value"])

    try:
        if os.getenv("CONTRACT_REVIEW_USE_MOCK", "").lower() in {"1", "true", "yes"}:
            await process_contract_mock(run_id=run_id, version_id=version_id, document_id=document_id, user_id=user_id)
            return

        suffix = Path(filename).suffix.lower() or ".txt"
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            tmp.write(content)
            tmp_path = tmp.name

        await report_progress("uploading", 10)
        pipeline = ContractReviewPipeline(progress_callback=report_progress)
        result = await pipeline.review_file(tmp_path)
        payload = serialize_review_result(result)
        store.save_snapshot(run_id=run_id, user_id=user_id, result_json=payload)
        store.update_run(run_id=run_id, user_id=user_id, status="completed", progress=100, completed=True, error=None)
    except ContractReviewPipelineError as exc:
        logger.error("Run %s failed at %s: %s", run_id, exc.stage, exc)
        try:
            failed_progress = 100 if exc.stage == "guardrail" else progress_state["value"]
            store.update_run(run_id=run_id, user_id=user_id, status="failed", progress=failed_progress, error=str(exc), completed=True)
        except ContractStoreError:
            logger.exception("Could not persist failed status for run %s", run_id)
    except Exception as exc:  # noqa: BLE001
        logger.error("Run %s failed: %s", run_id, exc)
        try:
            store.update_run(run_id=run_id, user_id=user_id, status="failed", progress=progress_state["value"], error=str(exc), completed=True)
        except ContractStoreError:
            logger.exception("Could not persist failed status for run %s", run_id)


def serialize_review_result(result) -> dict[str, Any]:
    clauses = []
    matches = []
    citations = []
    all_violations = []
    all_risks = []
    all_suggestions = []
    clause_compliance = []

    for item in result.clauses:
        violations = item.compliance.violations if item.compliance else []
        severities = [v.severity for v in violations if hasattr(v, "severity")]
        if "high" in severities:
            risk_level = "high"
        elif "medium" in severities:
            risk_level = "medium"
        elif violations:
            risk_level = "low"
        else:
            risk_level = "low"

        clause_data = {
            "id": item.clause.id,
            "type": item.clause.clause_type,
            "text": item.clause.text_content,
            "riskLevel": risk_level,
        }

        if item.compliance:
            clause_data["compliance"] = {
                "status": item.compliance.compliance_status,
                "summary": item.compliance.summary,
                "violations": [
                    {
                        "clause": v.clause,
                        "description": v.description,
                        "citation": v.citation,
                        "severity": v.severity,
                        "verified": v.verified,
                        "contractClauseId": item.clause.id,
                        "contractClauseType": item.clause.clause_type,
                    }
                    for v in item.compliance.violations
                ],
                "risks": item.compliance.risks,
                "suggestions": item.compliance.suggestions,
            }
            clause_compliance.append(clause_data["compliance"])

        clauses.append(clause_data)

        for match in item.matches:
            matches.append(
                {
                    "clauseId": item.clause.id,
                    "uid": match.uid,
                    "citation": match.display_citation,
                    "documentTitle": match.document_title,
                    "segmentType": match.segment_type,
                    "text": repair_mojibake_text(match.effective_text or match.text or ""),
                    "score": display_match_score(match),
                    "rankingScore": match.score,
                    "validitySignal": match.validity.status,
                    "scoreFactors": match.score_factors,
                }
            )

        for citation, verification in zip(item.citations, item.verification_results):
            citations.append(
                {
                    "displayText": citation.display_text,
                    "uid": citation.uid,
                    "verified": verification.verified,
                    "reason": verification.reason,
                    "documentTitle": verification.document_title or citation.document_title,
                }
            )

        if item.compliance:
            for violation in item.compliance.violations:
                all_violations.append(
                    {
                        "clause": violation.clause,
                        "description": violation.description,
                        "citation": violation.citation,
                        "verified": violation.verified,
                        "contractClauseId": item.clause.id,
                        "contractClauseType": item.clause.clause_type,
                    }
                )
            all_risks.extend(item.compliance.risks)
            all_suggestions.extend(item.compliance.suggestions)

    return {
        "clauses": clauses,
        "matches": matches,
        "citations": citations,
        "compliance": {
            "violations": all_violations,
            "risks": all_risks,
            "suggestions": all_suggestions,
            "citations": citations,
            "clauseResults": clause_compliance,
        },
        "previewText": repair_mojibake_text(result.contract.raw_text),
        "sourceFormat": result.contract.source_format,
    }


def display_match_score(match) -> float:
    """Return a UI-safe relevance score in 0..1, excluding ranking boosts."""
    factors = match.score_factors if isinstance(match.score_factors, dict) else {}

    def factor(name: str) -> float:
        try:
            return float(factors.get(name, 0.0) or 0.0)
        except (TypeError, ValueError):
            return 0.0

    base_relevance = max(factor("vector"), factor("lexical")) + factor("exact") + factor("title")
    if base_relevance <= 0:
        base_relevance = float(getattr(match, "score", 0.0) or 0.0)
    return max(0.0, min(1.0, base_relevance))


async def process_contract_mock(*, run_id: str, version_id: str, document_id: str, user_id: str):
    store = get_contract_store()
    store.update_run(run_id=run_id, user_id=user_id, status="uploading", progress=10)
    await asyncio.sleep(0.1)
    store.update_run(run_id=run_id, user_id=user_id, status="parsing", progress=25)
    await asyncio.sleep(0.1)
    store.update_run(run_id=run_id, user_id=user_id, status="extracting", progress=40)
    await asyncio.sleep(0.1)
    store.update_run(run_id=run_id, user_id=user_id, status="retrieving", progress=65)
    await asyncio.sleep(0.1)
    store.update_run(run_id=run_id, user_id=user_id, status="analyzing", progress=85)
    await asyncio.sleep(0.1)
    store.update_run(run_id=run_id, user_id=user_id, status="verifying", progress=95)
    await asyncio.sleep(0.1)
    payload = {
        "clauses": [
            {"id": "c1", "type": "Tiền lương", "text": "Người lao động được trả lương 10.000.000 VNĐ/tháng.", "riskLevel": "low"},
            {"id": "c2", "type": "Kỷ luật lao động", "text": "Người lao động bị phạt 01 tháng lương nếu vi phạm nội quy.", "riskLevel": "high"},
        ],
        "compliance": {
            "violations": [
                {
                    "clause": "Kỷ luật lao động",
                    "description": "Điều khoản phạt tiền người lao động có dấu hiệu vi phạm quy định về kỷ luật lao động.",
                    "citation": "Điều 127 Bộ luật Lao động",
                    "verified": True,
                }
            ],
            "risks": ["Điều khoản xử lý kỷ luật bằng phạt tiền có rủi ro cao."],
            "suggestions": ["Thay thế bằng hình thức xử lý kỷ luật lao động phù hợp Bộ luật Lao động."],
            "citations": [],
            "clauseResults": [],
        },
        "matches": [],
        "citations": [],
        "previewText": "",
        "sourceFormat": "pdf",
    }
    store.save_snapshot(run_id=run_id, user_id=user_id, result_json=payload)
    store.update_run(run_id=run_id, user_id=user_id, status="completed", progress=100, completed=True)


def job_status_from_bundle(
    *,
    run: dict[str, Any],
    version: dict[str, Any],
    snapshot_result: dict[str, Any],
    file_url: str | None,
) -> JobStatusResponse:
    compliance = snapshot_result.get("compliance") if isinstance(snapshot_result, dict) else None
    return JobStatusResponse(
        jobId=run["id"],
        status=run.get("status", "uploading"),
        progress=int(run.get("progress", 0) or 0),
        filename=version.get("filename", ""),
        createdAt=run.get("created_at") or run.get("started_at") or "",
        documentId=run.get("document_id"),
        versionId=run.get("version_id"),
        fileUrl=file_url,
        previewText=repair_mojibake_text(snapshot_result.get("previewText", "")) if isinstance(snapshot_result, dict) else None,
        sourceFormat=version.get("source_format"),
        clauses=[ContractClauseResponse(**c) for c in snapshot_result.get("clauses", [])] if snapshot_result.get("clauses") else None,
        matches=[LegalMatchResponse(**m) for m in snapshot_result.get("matches", [])] if snapshot_result.get("matches") else None,
        compliance=ComplianceResultResponse(**compliance) if compliance else None,
        citations=[CitationResponse(**c) for c in snapshot_result.get("citations", [])] if snapshot_result.get("citations") else None,
        error=run.get("error"),
    )
