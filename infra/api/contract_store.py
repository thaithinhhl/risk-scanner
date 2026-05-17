"""Supabase-backed persistence for Contract Review documents and runs."""
from __future__ import annotations

import mimetypes
import os
import posixpath
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional
from urllib.parse import quote

import requests
from dotenv import load_dotenv


_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(_ROOT / ".env", override=False)
load_dotenv(_ROOT / "frontend" / ".env.local", override=False)


class ContractStoreError(RuntimeError):
    """Raised when contract persistence cannot complete."""


class ContractStore:
    """Small PostgREST and Storage client for persisted contract review data."""

    def __init__(self) -> None:
        self.supabase_url = os.getenv("NEXT_PUBLIC_SUPABASE_URL", "").rstrip("/")
        self.service_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")
        self.storage_bucket = os.getenv("SUPABASE_CONTRACT_REVIEW_BUCKET", "contract-review-files")
        if not self.supabase_url or not self.service_key:
            raise ContractStoreError("Supabase URL or service role key is not configured")
        self.rest_url = f"{self.supabase_url}/rest/v1"
        self.storage_url = f"{self.supabase_url}/storage/v1"

    @property
    def _headers(self) -> dict[str, str]:
        return {
            "apikey": self.service_key,
            "Authorization": f"Bearer {self.service_key}",
            "Content-Type": "application/json",
        }

    def _request(
        self,
        method: str,
        path: str,
        *,
        params: Optional[dict[str, Any]] = None,
        json: Any = None,
        prefer: Optional[str] = None,
    ) -> Any:
        headers = dict(self._headers)
        if prefer:
            headers["Prefer"] = prefer
        response = requests.request(
            method,
            f"{self.rest_url}/{path}",
            headers=headers,
            params=params,
            json=json,
            timeout=20,
        )
        if response.status_code >= 400:
            raise ContractStoreError(f"Supabase {method} {path} failed: {response.status_code} {response.text}")
        if not response.text:
            return None
        return response.json()

    def upload_file(
        self,
        *,
        user_id: str,
        document_id: str,
        version_number: int,
        filename: str,
        content: bytes,
        content_type: Optional[str] = None,
    ) -> str:
        safe_name = self._sanitize_filename(filename)
        storage_path = posixpath.join(user_id, document_id, f"v{version_number}", safe_name)
        headers = {
            "apikey": self.service_key,
            "Authorization": f"Bearer {self.service_key}",
            "Content-Type": content_type or mimetypes.guess_type(filename)[0] or "application/octet-stream",
            "x-upsert": "false",
        }
        response = requests.post(
            f"{self.storage_url}/object/{self.storage_bucket}/{quote(storage_path, safe='/')}",
            headers=headers,
            data=content,
            timeout=60,
        )
        if response.status_code >= 400:
            raise ContractStoreError(
                f"Supabase storage upload failed: {response.status_code} {response.text}"
            )
        return storage_path

    def create_signed_file_url(self, storage_path: str, expires_in: int = 3600) -> Optional[str]:
        if not storage_path:
            return None
        response = requests.post(
            f"{self.storage_url}/object/sign/{self.storage_bucket}/{quote(storage_path, safe='/')}",
            headers=self._headers,
            json={"expiresIn": expires_in},
            timeout=20,
        )
        if response.status_code >= 400:
            raise ContractStoreError(
                f"Supabase signed URL failed: {response.status_code} {response.text}"
            )
        body = response.json()
        signed_path = body.get("signedURL") or body.get("signedUrl")
        if not signed_path:
            return None
        if signed_path.startswith("http"):
            return signed_path
        return f"{self.supabase_url}/storage/v1{signed_path}"

    def create_document(
        self,
        *,
        user_id: str,
        original_filename: str,
        display_name: Optional[str] = None,
        document_id: Optional[str] = None,
    ) -> dict[str, Any]:
        rows = self._request(
            "POST",
            "contract_documents",
            json={
                "id": document_id or str(uuid.uuid4()),
                "user_id": user_id,
                "original_filename": original_filename,
                "display_name": display_name or original_filename,
            },
            prefer="return=representation",
        )
        return rows[0]

    def create_version(
        self,
        *,
        document_id: str,
        user_id: str,
        filename: str,
        content_type: Optional[str],
        file_size_bytes: int,
        storage_path: str,
        version_number: int = 1,
        source_type: str = "original_upload",
        source_format: str = "unknown",
        parent_version_id: Optional[str] = None,
        source_run_id: Optional[str] = None,
        version_id: Optional[str] = None,
    ) -> dict[str, Any]:
        rows = self._request(
            "POST",
            "contract_document_versions",
            json={
                "id": version_id or str(uuid.uuid4()),
                "document_id": document_id,
                "user_id": user_id,
                "version_number": version_number,
                "source_type": source_type,
                "parent_version_id": parent_version_id,
                "source_run_id": source_run_id,
                "filename": filename,
                "content_type": content_type,
                "source_format": source_format,
                "file_size_bytes": file_size_bytes,
                "storage_path": storage_path,
            },
            prefer="return=representation",
        )
        return rows[0]

    def create_run(
        self,
        *,
        document_id: str,
        version_id: str,
        user_id: str,
        status: str = "uploading",
        progress: int = 0,
        run_id: Optional[str] = None,
    ) -> dict[str, Any]:
        rows = self._request(
            "POST",
            "contract_review_runs",
            json={
                "id": run_id or str(uuid.uuid4()),
                "document_id": document_id,
                "version_id": version_id,
                "user_id": user_id,
                "status": status,
                "progress": progress,
                "started_at": datetime.now(timezone.utc).isoformat(),
            },
            prefer="return=representation",
        )
        return rows[0]

    def update_run(
        self,
        *,
        run_id: str,
        user_id: str,
        status: Optional[str] = None,
        progress: Optional[int] = None,
        error: Optional[str] = None,
        completed: bool = False,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {}
        if status is not None:
            payload["status"] = status
        if progress is not None:
            payload["progress"] = progress
        if error is not None:
            payload["error"] = error
        if completed:
            payload["completed_at"] = datetime.now(timezone.utc).isoformat()
        rows = self._request(
            "PATCH",
            "contract_review_runs",
            params={"id": f"eq.{run_id}", "user_id": f"eq.{user_id}", "deleted_at": "is.null"},
            json=payload,
            prefer="return=representation",
        )
        if not rows:
            raise ContractStoreError("Run not found")
        return rows[0]

    def save_snapshot(
        self,
        *,
        run_id: str,
        user_id: str,
        result_json: dict[str, Any],
        schema_version: int = 1,
    ) -> dict[str, Any]:
        existing = self.get_snapshot(run_id, user_id)
        if existing:
            rows = self._request(
                "PATCH",
                "contract_review_snapshots",
                params={"run_id": f"eq.{run_id}", "user_id": f"eq.{user_id}"},
                json={"result_json": result_json, "schema_version": schema_version},
                prefer="return=representation",
            )
        else:
            rows = self._request(
                "POST",
                "contract_review_snapshots",
                json={
                    "run_id": run_id,
                    "user_id": user_id,
                    "schema_version": schema_version,
                    "result_json": result_json,
                },
                prefer="return=representation",
            )
        return rows[0]

    def get_snapshot(self, run_id: str, user_id: str) -> Optional[dict[str, Any]]:
        rows = self._request(
            "GET",
            "contract_review_snapshots",
            params={
                "select": "*",
                "run_id": f"eq.{run_id}",
                "user_id": f"eq.{user_id}",
                "limit": "1",
            },
        )
        return rows[0] if rows else None

    def get_run(self, run_id: str, user_id: str) -> Optional[dict[str, Any]]:
        rows = self._request(
            "GET",
            "contract_review_runs",
            params={
                "select": "*",
                "id": f"eq.{run_id}",
                "user_id": f"eq.{user_id}",
                "deleted_at": "is.null",
                "limit": "1",
            },
        )
        return rows[0] if rows else None

    def get_document(self, document_id: str, user_id: str) -> Optional[dict[str, Any]]:
        rows = self._request(
            "GET",
            "contract_documents",
            params={
                "select": "*",
                "id": f"eq.{document_id}",
                "user_id": f"eq.{user_id}",
                "deleted_at": "is.null",
                "limit": "1",
            },
        )
        return rows[0] if rows else None

    def get_document_any_state(self, document_id: str, user_id: str) -> Optional[dict[str, Any]]:
        rows = self._request(
            "GET",
            "contract_documents",
            params={
                "select": "*",
                "id": f"eq.{document_id}",
                "user_id": f"eq.{user_id}",
                "limit": "1",
            },
        )
        return rows[0] if rows else None

    def get_version(self, version_id: str, user_id: str) -> Optional[dict[str, Any]]:
        rows = self._request(
            "GET",
            "contract_document_versions",
            params={
                "select": "*",
                "id": f"eq.{version_id}",
                "user_id": f"eq.{user_id}",
                "deleted_at": "is.null",
                "limit": "1",
            },
        )
        return rows[0] if rows else None

    def get_run_bundle(self, run_id: str, user_id: str) -> Optional[dict[str, Any]]:
        run = self.get_run(run_id, user_id)
        if not run:
            return None
        document = self.get_document(run["document_id"], user_id)
        if not document:
            return None
        version = self.get_version(run["version_id"], user_id)
        if not version:
            return None
        snapshot = self.get_snapshot(run_id, user_id)
        return {
            "run": run,
            "document": document,
            "version": version,
            "snapshot": snapshot,
        }

    def list_runs(self, user_id: str, limit: int = 25) -> list[dict[str, Any]]:
        runs = self._request(
            "GET",
            "contract_review_runs",
            params={
                "select": "*",
                "user_id": f"eq.{user_id}",
                "deleted_at": "is.null",
                "order": "created_at.desc",
                "limit": str(limit),
            },
        )
        if not runs:
            return []

        document_ids = self._dedupe_ids(run.get("document_id") for run in runs)
        version_ids = self._dedupe_ids(run.get("version_id") for run in runs)
        documents = self._request(
            "GET",
            "contract_documents",
            params={
                "select": "*",
                "user_id": f"eq.{user_id}",
                "deleted_at": "is.null",
                "id": f"in.({','.join(document_ids)})",
            },
        ) if document_ids else []
        versions = self._request(
            "GET",
            "contract_document_versions",
            params={
                "select": "*",
                "user_id": f"eq.{user_id}",
                "deleted_at": "is.null",
                "id": f"in.({','.join(version_ids)})",
            },
        ) if version_ids else []
        documents_by_id = {document["id"]: document for document in documents or []}
        versions_by_id = {version["id"]: version for version in versions or []}

        bundles: list[dict[str, Any]] = []
        for run in runs:
            document = documents_by_id.get(run["document_id"])
            if not document:
                continue
            version = versions_by_id.get(run["version_id"])
            if not version:
                continue
            bundles.append({"run": run, "document": document, "version": version})
        return bundles

    def _dedupe_ids(self, values) -> list[str]:
        seen: set[str] = set()
        ids: list[str] = []
        for value in values:
            if not value or value in seen:
                continue
            seen.add(value)
            ids.append(str(value))
        return ids

    def soft_delete_document(self, document_id: str, user_id: str) -> None:
        document = self.get_document_any_state(document_id, user_id)
        if not document:
            raise ContractStoreError("Document not found")
        if document.get("deleted_at"):
            return
        now = datetime.now(timezone.utc).isoformat()
        self._request(
            "PATCH",
            "contract_documents",
            params={"id": f"eq.{document_id}", "user_id": f"eq.{user_id}", "deleted_at": "is.null"},
            json={"deleted_at": now},
            prefer="return=minimal",
        )
        self._request(
            "PATCH",
            "contract_document_versions",
            params={"document_id": f"eq.{document_id}", "user_id": f"eq.{user_id}", "deleted_at": "is.null"},
            json={"deleted_at": now},
            prefer="return=minimal",
        )
        self._request(
            "PATCH",
            "contract_review_runs",
            params={"document_id": f"eq.{document_id}", "user_id": f"eq.{user_id}", "deleted_at": "is.null"},
            json={"deleted_at": now},
            prefer="return=minimal",
        )

    @staticmethod
    def _sanitize_filename(filename: str) -> str:
        keep = []
        for char in filename:
            if char.isalnum() or char in {".", "-", "_"}:
                keep.append(char)
            else:
                keep.append("_")
        return "".join(keep).strip("._") or f"contract_{uuid.uuid4().hex[:8]}"


def infer_source_format(filename: str, content_type: Optional[str] = None) -> str:
    suffix = Path(filename).suffix.lower()
    if suffix == ".pdf":
        return "pdf"
    if suffix in {".docx", ".doc"}:
        return "docx"
    if suffix in {".txt", ".md"}:
        return "text"
    if content_type == "application/pdf":
        return "pdf"
    if content_type and "word" in content_type:
        return "docx"
    if content_type and content_type.startswith("text/"):
        return "text"
    return "unknown"


def get_contract_store() -> ContractStore:
    return ContractStore()
