"""
Centralized Configuration — Vietnamese Legal Knowledge Graph
=============================================================

Loading order (highest priority first):
  1. .env file (via python-dotenv)
  2. OS environment variables
  3. Default values defined below

Usage
-----
    from src.config import settings

    # Access any setting
    uri = settings.NEO4J_URI
    api_key = settings.OPENAI_API_KEY

    # Neo4j driver
    from neo4j import GraphDatabase
    driver = GraphDatabase.driver(
        settings.NEO4J_URI,
        auth=(settings.NEO4J_USER, settings.NEO4J_PASSWORD)
    )

    # LLM client
    from src.llm.client import create_client
    client = create_client(
        api_key=settings.OPENAI_API_KEY,
        model=settings.OPENAI_MODEL,
    )
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv

# ── Load .env file ───────────────────────────────────────────────────────────
# Looks for .env in project root (one level up from this file)
_project_root = Path(__file__).resolve().parent.parent
_env_path = _project_root / ".env"
load_dotenv(_env_path, override=True)
load_dotenv(_project_root / "frontend" / ".env.local", override=False)


# ── Helper ───────────────────────────────────────────────────────────────────

def _env(key: str, default: str = "") -> str:
    """Read env var with default."""
    return os.environ.get(key, default)


def _env_int(key: str, default: int) -> int:
    """Read env var as int with default."""
    try:
        return int(os.environ.get(key, str(default)))
    except (ValueError, TypeError):
        return default


def _env_float(key: str, default: float) -> float:
    """Read env var as float with default."""
    try:
        return float(os.environ.get(key, str(default)))
    except (ValueError, TypeError):
        return default


def _env_bool(key: str, default: bool = False) -> bool:
    """Read env var as bool. Truthy: 1, true, yes, on."""
    val = os.environ.get(key, str(default)).lower()
    return val in ("1", "true", "yes", "on")


# =============================================================================
# Neo4j
# =============================================================================

NEO4J_URI: str = _env("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER: str = _env("NEO4J_USER", "neo4j")
NEO4J_PASSWORD: str = _env("NEO4J_PASSWORD", "password")
NEO4J_DATABASE: str = _env("NEO4J_DATABASE", "neo4j")
NEO4J_TIMEOUT: int = _env_int("NEO4J_TIMEOUT", 30)  # seconds

# Neo4j memory config (for docker-compose / self-hosted)
NEO4J_HEAP_SIZE: str = _env("NEO4J_HEAP_SIZE", "2G")
NEO4J_PAGE_CACHE: str = _env("NEO4J_PAGE_CACHE", "1G")


# =============================================================================
# LLM / OpenAI
# =============================================================================

LLM_PROVIDER: str = _env("LLM_PROVIDER", "openai")
OPENAI_API_KEY: str = _env("OPENAI_API_KEY", "")
OPENAI_MODEL: str = _env("OPENAI_MODEL", "gpt-5.4-mini")
OPENAI_BASE_URL: Optional[str] = _env("OPENAI_BASE_URL", "") or None

# Intent analysis thresholds
INTENT_CONFIDENCE_THRESHOLD: float = _env_float("INTENT_CONFIDENCE_THRESHOLD", 0.7)
INTENT_CLARIFICATION_THRESHOLD: float = _env_float("INTENT_CLARIFICATION_THRESHOLD", 0.4)


# =============================================================================
# Embedding Service (T6.2)
# =============================================================================

EMBED_SERVICE_URL: str = _env("EMBED_SERVICE_URL", "http://localhost:8001")
EMBED_MODEL: str = _env("EMBED_MODEL", "mainguyen9/vietlegal-harrier-0.6b")
EMBED_QUERY_INSTRUCTION: str = _env(
    "EMBED_QUERY_INSTRUCTION",
    "Given a Vietnamese legal question, retrieve relevant legal passages that answer the question",
)
EMBED_BATCH_SIZE: int = _env_int("EMBED_BATCH_SIZE", 512)
EMBED_MAX_TEXTS: int = _env_int("EMBED_MAX_TEXTS", 1000)
EMBED_DIMENSIONS: int = _env_int("EMBED_DIMENSIONS", 1024)


# =============================================================================
# Data Pipeline Paths
# =============================================================================

DATA_DIR: str = _env("DATA_DIR", "data")
OUTPUT_DIR: str = _env("OUTPUT_DIR", "output")

# Input files
METADATA_PATH: str = _env("METADATA_PATH", "data/metadata.parquet")
CONTENT_PATH: str = _env("CONTENT_PATH", "data/content.parquet")
RELATIONSHIPS_PATH: str = _env("RELATIONSHIPS_PATH", "data/relationships.parquet")

# Intermediate files
METADATA_DEDUPED_PATH: str = _env("METADATA_DEDUPED_PATH", "data/metadata_deduped.parquet")
CONTENT_ENRICHED_PATH: str = _env("CONTENT_ENRICHED_PATH", "data/content_enriched.parquet")
CONTENT_CLEAN_PATH: str = _env("CONTENT_CLEAN_PATH", "data/content_clean.parquet")

# Output files
LOOKUP_PATH: str = _env("LOOKUP_PATH", "data/so_ky_hieu_lookup.json")
SCHEMA_PATH: str = _env("SCHEMA_PATH", "output/neo4j_schema.cypher")
PIPELINE_CHECKPOINT: str = _env("PIPELINE_CHECKPOINT", "output/pipeline_checkpoint.json")


# =============================================================================
# Neo4j Vector Index
# =============================================================================

VECTOR_INDEX_NAME: str = _env("VECTOR_INDEX_NAME", "article_embeddings")


# =============================================================================
# Pipeline
# =============================================================================

PIPELINE_LOG_LEVEL: str = _env("PIPELINE_LOG_LEVEL", "INFO")
PIPELINE_LOG_PATH: str = _env("PIPELINE_LOG_PATH", "output/pipeline.log")

# Batch sizes
NEO4J_BATCH_SIZE: int = _env_int("NEO4J_BATCH_SIZE", 5000)
PARQUET_BATCH_SIZE: int = _env_int("PARQUET_BATCH_SIZE", 2000)

# Crawler
CRAWL_RATE_LIMIT: float = _env_float("CRAWL_RATE_LIMIT", 1.5)
CRAWL_TIMEOUT: int = _env_int("CRAWL_TIMEOUT", 15)
CRAWL_MAX_RETRIES: int = _env_int("CRAWL_MAX_RETRIES", 3)
CRAWL_CHECKPOINT: str = _env("CRAWL_CHECKPOINT", "output/crawl_checkpoint.json")


# =============================================================================
# Contract Parser (T4.1)
# =============================================================================

CONTRACT_PARSER_BACKEND: str = _env("CONTRACT_PARSER_BACKEND", "pipeline")
CONTRACT_PARSER_LANG: str = _env("CONTRACT_PARSER_LANG", "ch")
CONTRACT_MAX_FILE_SIZE_MB: int = _env_int("CONTRACT_MAX_FILE_SIZE_MB", 10)
OPENAI_OCR_MODEL: str = _env("OPENAI_OCR_MODEL", "gpt-4o-mini")
CONTRACT_OCR_MIN_TEXT_CHARS: int = _env_int("CONTRACT_OCR_MIN_TEXT_CHARS", 20)
CONTRACT_OCR_MAX_PAGES: int = _env_int("CONTRACT_OCR_MAX_PAGES", 20)


# =============================================================================
# Mock Bridge Layer (for parallel development)
# =============================================================================

EMBEDDING_SERVICE_MODE: str = _env("EMBEDDING_SERVICE_MODE", "real")  # "mock" | "real"
GRAPH_REPOSITORY_MODE: str = _env("GRAPH_REPOSITORY_MODE", "mock")  # "mock" | "neo4j"
EFFECTIVE_TEXT_SERVICE_MODE: str = _env("EFFECTIVE_TEXT_SERVICE_MODE", "mock")  # "mock" | "real"


# =============================================================================
# Auth
# =============================================================================

AUTH_SECRET: str = _env("AUTH_SECRET", "")


# =============================================================================
# Embedding Service (T6.2) — Server Config
# =============================================================================

EMBED_HOST: str = _env("EMBED_HOST", "0.0.0.0")
EMBED_PORT: int = _env_int("EMBED_PORT", 8001)


# =============================================================================
# Helpers
# =============================================================================

def ensure_dirs() -> None:
    """Create DATA_DIR and OUTPUT_DIR if they don't exist."""
    Path(DATA_DIR).mkdir(parents=True, exist_ok=True)
    Path(OUTPUT_DIR).mkdir(parents=True, exist_ok=True)


def neo4j_auth() -> tuple[str, str]:
    """Return (user, password) tuple for Neo4j driver."""
    return (NEO4J_USER, NEO4J_PASSWORD)


def print_config() -> None:
    """Print current config (hides secrets). Useful for debugging."""
    safe_vars = {
        k: v for k, v in globals().items()
        if k.isupper() and not k.startswith("_") and "PASSWORD" not in k and "API_KEY" not in k
    }
    print("=" * 60)
    print("Current Configuration")
    print("=" * 60)
    for key, value in sorted(safe_vars.items()):
        print(f"  {key} = {value}")
    print("=" * 60)
