"""Контракты данных проекта «До репоста».

Схемы согласованы с backend/frontend по ТЗ. Не менять без команды.
"""
from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class ContentKind(str, Enum):
    page = "page"
    snippet = "snippet"
    user_text = "user_text"


class Origin(str, Enum):
    retrieved = "retrieved"
    user_provided = "user_provided"


class Source(BaseModel):
    """Источник от backend."""
    id: str
    title: str = ""
    url: str = ""
    published_at: Optional[str] = None
    retrieved_at: Optional[str] = None
    content: str = ""
    content_kind: ContentKind = ContentKind.page
    origin: Origin = Origin.retrieved


# ---------- extract_claims ----------

class Claim(BaseModel):
    id: str
    original_span: str = Field(description="Точный фрагмент сообщения")
    text: str = Field(description="Самостоятельно понятное утверждение")
    queries: list[str] = Field(default_factory=list, max_length=2)
    missing_context: list[str] = Field(default_factory=list)


class ExtractionResult(BaseModel):
    claims: list[Claim] = Field(default_factory=list, max_length=3)
    uncheckable_reason: Optional[str] = None


# ---------- evaluate_claims ----------

class Status(str, Enum):
    supported = "supported"
    contradicted = "contradicted"
    context = "context"
    insufficient = "insufficient"


class Relation(str, Enum):
    supports = "supports"
    contradicts = "contradicts"
    adds_context = "adds_context"


class Evidence(BaseModel):
    source_id: str
    quote: str
    relation: Relation
    explanation: str = ""


class ClaimResult(BaseModel):
    id: str
    text: str
    status: Status
    explanation: str = ""
    evidence: list[Evidence] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    next_action: str = ""


class EvaluationResult(BaseModel):
    claims: list[ClaimResult] = Field(default_factory=list)
    share_text: str = ""


# ---------- ошибки ----------

class PipelineError(Exception):
    """Базовая ошибка пайплайна."""


class ModelTimeout(PipelineError):
    """Технический сбой: модель не ответила вовремя. НЕ маскировать под insufficient."""


class InvalidResponse(PipelineError):
    """Модель вернула ответ, который не удалось привести к схеме."""


class ModelCallError(PipelineError):
    """Прочий технический сбой вызова модели."""
