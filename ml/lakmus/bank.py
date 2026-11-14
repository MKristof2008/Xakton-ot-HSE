"""Банк знаний: то, что система уже проверила и запомнила.

Идея простая. Каждая проверка, где вердикт опирается на источник, — это
знание. Раньше оно жило только в таблице проверок и никому не помогало:
следующий человек с тем же утверждением проходил весь путь заново.
Теперь такие проверки складываются в банк с тегом темы. Перед походом в
интернет система смотрит в банк: если это уже разобрано — отвечает быстро
и одинаково.

Что попадает в банк:
  * только утверждения, у которых есть источник;
  * только supported или contradicted — «непонятно» знанием не является;
  * с тегом темы.

Чего в банке нет и не будет:
  * «фактов» без источника;
  * вердиктов без объяснения;
  * записей, которые нельзя проверить: у каждой есть ссылка.

Банк пополняется сам, но редактор может его править: ручная запись
помечается ``origin: human`` и моделью не перетирается.
"""

from __future__ import annotations

import json
import os
import re
import tempfile
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Optional

from . import tags as tag_module

#: Путь можно переопределить переменной окружения — нужно тестам, чтобы
#: проверки не писали в рабочий банк, и стенду, чтобы банк был отдельным.
BANK_PATH = Path(
    os.environ.get("VERDICT_BANK")
    or Path(__file__).resolve().parent / "data" / "knowledge_bank.json"
)

#: Потолок: банк не должен превратиться в свалку на защите.
MAX_RECORDS = 2000
#: Сколько записей отдаём как подсказку.
TOP_K = 5


@dataclass
class Entry:
    """Одна запись банка: утверждение, тег, вердикт и основание."""

    claim: str
    tag: str
    status: str  # supported | contradicted
    explanation: str = ""
    quote: str = ""
    source_title: str = ""
    source_url: str = ""
    #: model — выведено проверкой, human — поправлено человеком.
    origin: str = "model"
    #: Сколько раз подтверждалось.
    confirmations: int = 1
    updated_at: str = ""

    def key(self) -> str:
        return _norm(self.claim)

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def _norm(text: str) -> str:
    """Нормализация для сравнения: регистр, «ё», пунктуация, пробелы."""
    low = (text or "").lower().replace("ё", "е")
    low = re.sub(r"[^\w\s]", " ", low, flags=re.UNICODE)
    return " ".join(low.split())


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class Bank:
    """Банк знаний: чтение, поиск, запись. Файл читается один раз."""

    def __init__(self, path: Optional[Path] = None) -> None:
        self.path = Path(path) if path else BANK_PATH
        self._entries: list[Entry] = []
        self._by_key: dict[str, Entry] = {}
        self._loaded = False

    def _load(self) -> None:
        if self._loaded:
            return
        self._loaded = True
        if not self.path.is_file():
            return
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return
        items = raw.get("entries", []) if isinstance(raw, dict) else []
        for item in items:
            if not isinstance(item, dict):
                continue
            status = str(item.get("status", ""))
            claim = str(item.get("claim", "")).strip()
            if not claim or status not in ("supported", "contradicted"):
                continue
            entry = Entry(
                claim=claim[:500],
                tag=str(item.get("tag", tag_module.UNKNOWN.key)),
                status=status,
                explanation=str(item.get("explanation", ""))[:800],
                quote=str(item.get("quote", ""))[:500],
                source_title=str(item.get("source_title", ""))[:300],
                source_url=str(item.get("source_url", ""))[:500],
                origin=str(item.get("origin", "model")),
                confirmations=int(item.get("confirmations", 1) or 1),
                updated_at=str(item.get("updated_at", "")),
            )
            self._entries.append(entry)
            self._by_key[entry.key()] = entry

    def __len__(self) -> int:
        self._load()
        return len(self._entries)

    def stats(self) -> dict[str, Any]:
        self._load()
        by_tag: dict[str, int] = {}
        for entry in self._entries:
            by_tag[entry.tag] = by_tag.get(entry.tag, 0) + 1
        return {
            "total": len(self._entries),
            "supported": sum(1 for e in self._entries if e.status == "supported"),
            "contradicted": sum(
                1 for e in self._entries if e.status == "contradicted"
            ),
            "by_tag": by_tag,
        }

    def lookup(self, claim: str, tag: str = "") -> Optional[Entry]:
        """Точное совпадение утверждения после нормализации.

        Именно точное. Похожее утверждение — это другое утверждение:
        «ставка 21%» и «ставка 20%» совпадают на три слова из четырёх,
        но вердикт у них противоположный.
        """
        self._load()
        return self._by_key.get(_norm(claim))

    def search(self, text: str, tag: str = "", limit: int = TOP_K) -> list[Entry]:
        """Похожие записи — подсказка, а не готовый ответ.

        Сравнение идёт по основам слов (первые 5 символов): в русском
        «ставка» и «ставку» — одно слово, и точное совпадение строк здесь
        не годится.
        """
        self._load()
        stems = {w[:5] for w in _norm(text).split() if len(w) >= 4}
        if not stems:
            return []

        scored: list[tuple[float, Entry]] = []
        for entry in self._entries:
            if tag and entry.tag != tag:
                continue
            claim_stems = {w[:5] for w in _norm(entry.claim).split() if len(w) >= 4}
            overlap = len(stems & claim_stems)
            if not overlap:
                continue
            score = overlap / max(len(stems), 1)
            if entry.origin == "human":
                score += 0.15
            score += min(entry.confirmations, 5) * 0.01
            scored.append((score, entry))

        scored.sort(key=lambda pair: pair[0], reverse=True)
        return [entry for score, entry in scored[:limit] if score >= 0.25]

    def by_tag(self, tag: str, limit: int = TOP_K) -> list[Entry]:
        self._load()
        items = [e for e in self._entries if e.tag == tag]
        items.sort(key=lambda e: e.updated_at, reverse=True)
        return items[:limit]

    def learn(
        self,
        claim: str,
        status: str,
        *,
        tag: str = "",
        explanation: str = "",
        quote: str = "",
        source_title: str = "",
        source_url: str = "",
        origin: str = "model",
    ) -> Optional[Entry]:
        """Запомнить проверку. None — если запоминать нечего."""
        claim = (claim or "").strip()
        if not claim or status not in ("supported", "contradicted"):
            return None
        if not (source_url or "").strip():
            return None

        self._load()
        stamp = _now()
        existing = self._by_key.get(_norm(claim))

        if existing is not None:
            # Ручная правка не перетирается моделью: человек — истина.
            if existing.origin == "human" and origin != "human":
                existing.confirmations += 1
                existing.updated_at = stamp
                return existing
            existing.status = status
            existing.explanation = (explanation or existing.explanation)[:800]
            existing.quote = (quote or existing.quote)[:500]
            existing.source_title = (
                source_title or existing.source_title
            )[:300]
            existing.source_url = (source_url or existing.source_url)[:500]
            if origin == "human":
                existing.origin = "human"
            existing.confirmations += 1
            existing.updated_at = stamp
            return existing

        entry = Entry(
            claim=claim[:500],
            tag=tag or tag_module.UNKNOWN.key,
            status=status,
            explanation=(explanation or "")[:800],
            quote=(quote or "")[:500],
            source_title=(source_title or "")[:300],
            source_url=(source_url or "")[:500],
            origin=origin,
            confirmations=1,
            updated_at=stamp,
        )
        self._entries.append(entry)
        self._by_key[entry.key()] = entry
        self._trim()
        return entry

    def learn_from_claims(self, claims: Iterable[Any], tag: str) -> int:
        """Запомнить все пригодные утверждения проверки."""
        saved = 0
        for claim in claims:
            entry = self.learn(
                getattr(claim, "text", ""),
                getattr(claim, "status", ""),
                tag=tag,
                explanation=getattr(claim, "explanation", ""),
                quote=getattr(claim, "quote", ""),
                source_title=getattr(claim, "source_title", ""),
                source_url=getattr(claim, "source_url", ""),
            )
            if entry is not None:
                saved += 1
        return saved

    def _trim(self) -> None:
        """Вытеснить старые записи модели, сохранив ручные."""
        if len(self._entries) <= MAX_RECORDS:
            return
        human = [e for e in self._entries if e.origin == "human"]
        auto = [e for e in self._entries if e.origin != "human"]
        auto.sort(key=lambda e: (e.confirmations, e.updated_at), reverse=True)
        keep = human + auto[: max(0, MAX_RECORDS - len(human))]
        keep.sort(key=lambda e: e.updated_at)
        self._entries = keep
        self._by_key = {e.key(): e for e in self._entries}

    def save(self) -> bool:
        """Записать банк на диск атомарно.

        Ошибка записи не должна ронять проверку: банк — ускоритель, а не
        единственный источник правды.
        """
        self._load()
        payload = {
            "version": 1,
            "note": (
                "Банк проверенных утверждений. Пополняется проверками; "
                "ручные записи помечены origin=human и не перетираются."
            ),
            "updated_at": _now(),
            "entries": [e.as_dict() for e in self._entries],
        }
        temp_path: Optional[Path] = None
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(
                "w",
                encoding="utf-8",
                dir=str(self.path.parent),
                prefix=".bank-",
                suffix=".tmp",
                delete=False,
            ) as handle:
                json.dump(payload, handle, ensure_ascii=False, indent=2)
                temp_path = Path(handle.name)
            os.replace(temp_path, self.path)
            return True
        except OSError:
            if temp_path is not None:
                try:
                    temp_path.unlink(missing_ok=True)
                except OSError:
                    pass
            return False


#: Общий экземпляр для процесса.
_SHARED = Bank()


def shared() -> Bank:
    return _SHARED


def reset(path: Optional[Path] = None) -> Bank:
    """Пересоздать общий банк — нужно тестам и смене файла."""
    global _SHARED
    _SHARED = Bank(path)
    return _SHARED
