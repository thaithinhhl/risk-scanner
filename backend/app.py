"""
PhápLý — FastAPI Backend
Main application entry point.
"""
from fastapi import FastAPI, Depends, HTTPException, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from datetime import datetime
from typing import Optional

from src.auth import get_current_user, require_role, CurrentUser, UsageLimits

app = FastAPI(
    title="PhápLý API",
    description="Vietnamese Legal Knowledge Graph API",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://localhost:3001",
        "https://a20-app-104.site",
        "https://104-fe.vercel.app",
        # HuggingFace Spaces preview domains
        "https://*.hf.space",
    ],
    allow_origin_regex=r"https://.*\.hf\.space",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health_check():
    return {"status": "ok", "timestamp": datetime.utcnow().isoformat()}


@app.get("/api/me")
async def get_me(user: CurrentUser = Depends(get_current_user)):
    """Get current user info."""
    limits = UsageLimits.get_limits(user.role)
    return {
        "id": user.id,
        "email": user.email,
        "role": user.role,
        "limits": limits,
    }


# ── Contract Endpoints (Protected) ──────────────────────────────────────────

@app.post("/api/contracts/upload")
async def upload_contract(
    file: UploadFile = File(...),
    user: CurrentUser = Depends(require_role("free")),
):
    """Upload a contract for analysis. Free users limited to 5/month."""
    limits = UsageLimits.get_limits(user.role)
    max_size = limits["max_upload_size_mb"] * 1024 * 1024

    if file.size and file.size > max_size:
        raise HTTPException(
            status_code=413,
            detail=f"File too large. Max {limits['max_upload_size_mb']}MB for your tier.",
        )

    # TODO: Implement actual upload + analysis pipeline
    return {
        "jobId": f"job_{datetime.utcnow().timestamp()}",
        "status": "uploading",
        "filename": file.filename,
    }


@app.get("/api/contracts/{job_id}/status")
async def get_job_status(
    job_id: str,
    user: CurrentUser = Depends(require_role("free")),
):
    """Get contract analysis job status."""
    # TODO: Implement actual status check
    return {
        "jobId": job_id,
        "status": "completed",
        "progress": 100,
        "filename": "contract.pdf",
        "createdAt": datetime.utcnow().isoformat(),
    }


@app.get("/api/contracts/history")
async def get_job_history(
    user: CurrentUser = Depends(require_role("free")),
):
    """Get user's contract analysis history."""
    # TODO: Implement actual history from DB
    return []


# ── Q&A Endpoints (Protected) ───────────────────────────────────────────────

@app.post("/api/qa/chat")
async def qa_chat(
    user: CurrentUser = Depends(require_role("free")),
):
    """Ask a legal question (SSE streaming). Free users limited to 10/day."""
    # TODO: Implement actual SSE streaming with LLM
    return {"message": "SSE endpoint - use EventSource"}


@app.post("/api/qa/conversations")
async def create_conversation(
    user: CurrentUser = Depends(require_role("free")),
):
    """Create a new conversation."""
    return {"id": f"conv_{datetime.utcnow().timestamp()}"}


@app.get("/api/qa/conversations")
async def get_conversations(
    user: CurrentUser = Depends(require_role("free")),
):
    """Get user's conversations."""
    return []


@app.delete("/api/qa/conversations/{conversation_id}")
async def delete_conversation(
    conversation_id: str,
    user: CurrentUser = Depends(require_role("free")),
):
    """Delete a conversation."""
    return {"success": True}
