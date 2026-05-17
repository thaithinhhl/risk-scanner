"""Pydantic schemas for API request/response models."""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


# ── QA Schemas ──────────────────────────────────────────────────────────────

class ChatRequest(BaseModel):
    message: str
    conversationId: Optional[str] = None
    tabId: Optional[str] = None


class IntentResult(BaseModel):
    type: str
    confidence: float


class Provision(BaseModel):
    documentName: str
    articleNumber: str
    text: str
    verified: bool = False
    citation: str = ""


class ChatChunk(BaseModel):
    token: Optional[str] = None
    conversationId: Optional[str] = None
    intents: Optional[list[IntentResult]] = None
    provisions: Optional[list[Provision]] = None
    done: Optional[bool] = None


class ChatMessageResponse(BaseModel):
    id: str
    role: str
    content: str
    timestamp: str
    intents: list[dict] = []
    provisions: list[dict] = []
    citations: list[dict] = []
    tokenCount: int = 0


class ConversationSummary(BaseModel):
    id: str
    title: str
    lastMessage: str
    createdAt: str
    lastMessageAt: Optional[str] = None
    tabId: Optional[str] = None


class CreateConversationRequest(BaseModel):
    title: str = "New conversation"
    tabId: Optional[str] = None


class RenameConversationRequest(BaseModel):
    title: str


class ConversationDetail(BaseModel):
    id: str
    title: str
    createdAt: str
    lastMessageAt: Optional[str] = None
    messages: list[ChatMessageResponse]


# ── Contract Schemas ────────────────────────────────────────────────────────

class UploadResponse(BaseModel):
    jobId: str
    documentId: str
    versionId: str


class ContractClauseResponse(BaseModel):
    id: str
    type: str
    text: str
    riskLevel: str = "medium"


class LegalMatchResponse(BaseModel):
    clauseId: str
    uid: str
    citation: str
    documentTitle: str = ""
    segmentType: str = ""
    text: str = ""
    score: float = 0.0
    rankingScore: float = 0.0
    validitySignal: str = "latest_known"
    scoreFactors: dict = {}


class CitationResponse(BaseModel):
    displayText: str
    uid: str
    verified: bool = False
    reason: str = ""
    documentTitle: str = ""


class ComplianceViolationResponse(BaseModel):
    clause: str
    description: str
    citation: str
    verified: bool = False


class ComplianceResultResponse(BaseModel):
    violations: list[ComplianceViolationResponse] = []
    risks: list[str] = []
    suggestions: list[str] = []
    citations: list[CitationResponse] = []
    clauseResults: list[dict] = []


class JobStatusResponse(BaseModel):
    jobId: str
    status: str  # uploading, parsing, analyzing, completed, failed
    progress: int = Field(ge=0, le=100)
    filename: str
    createdAt: str
    documentId: Optional[str] = None
    versionId: Optional[str] = None
    fileUrl: Optional[str] = None
    previewText: Optional[str] = None
    sourceFormat: Optional[str] = None
    clauses: Optional[list[ContractClauseResponse]] = None
    matches: Optional[list[LegalMatchResponse]] = None
    compliance: Optional[ComplianceResultResponse] = None
    citations: Optional[list[CitationResponse]] = None
    error: Optional[str] = None
