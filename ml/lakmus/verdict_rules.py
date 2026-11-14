"""Правила вывода: как из признаков получается «фейк» или «не фейк».

Модель не решает вердикт «на глаз». Сначала собираются признаки — сигналы
детекторов для медиа, утверждения и источники для текста. Потом по ним
прогоняется этот модуль: набор явных правил, у каждого свой вес и своё
объяснение. Правила одинаковы для всех тарифов и не зависят от модели,
поэтому вердикт воспроизводим.

Три семейства правил:

  * **Текст и ссылки** — опора на источники: подтверждение обязано иметь
    дословную цитату, опровержение — прямое отрицание события, отсутствие
    источников не превращается в «фейк».
  * **Фото** — следы генератора, следы монтажа, артефакты ИИ, метаданные.
  * **Видео** — подпись генератора в контейнере, статичность кадров,
    следы монтажа.

Правило возвращает вклад: направление (в сторону фейка или настоящего),
силу 0–1 и фразу для человека. Итог считается взвешенно, а не «кто
громче»: слабые признаки не перебивают сильные, а противоречие ведёт к
«непонятно», а не к случайной стороне.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable, Optional, Sequence

from . import fake_markers


@dataclass
class RuleHit:
    """Сработавшее правило: что нашли и насколько это весомо."""

    key: str
    title: str
    #: fake — в сторону подделки, real — в сторону подлинности, neutral — мимо.
    direction: str
    #: 0..1. Сила довода.
    weight: float
    #: Объяснение для человека.
    reason: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "title": self.title,
            "direction": self.direction,
            "weight": round(self.weight, 3),
            "reason": self.reason,
        }


@dataclass
class RuleVerdict:
    """Итог правил: вердикт, уверенность и все сработавшие правила."""

    verdict: str = "непонятно"  # правда | фейк | непонятно
    confidence: int = 0
    hits: list[RuleHit] = field(default_factory=list)
    summary: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "verdict": self.verdict,
            "confidence": self.confidence,
            "summary": self.summary,
            "rules": [h.as_dict() for h in self.hits],
        }


#: Сила признака, при которой правило решает само, без суммы.
DECISIVE = 0.7
#: Ниже этого вес — только пометка, а не основание для вердикта.
WEAK = 0.5


# --------------------------------------------------------------- медиа

def _details(signal: Any) -> dict[str, Any]:
    return getattr(signal, "details", None) or {}


def _signal_verdict(signal: Any) -> str:
    verdict = getattr(signal, "verdict", None)
    return str(getattr(verdict, "value", verdict) or "")


def rules_for_media(signals: Sequence[Any]) -> RuleVerdict:
    """Правила для фото и видео: только по отчёту детекторов.

    Важный принцип: отсутствие метаданных — не улика. Мессенджеры стирают
    их при каждой пересылке, поэтому «нет метаданных» никогда не даёт
    «фейк». И наоборот: монтаж сам по себе не делает материал ложным.
    """
    hits: list[RuleHit] = []

    for signal in signals:
        details = _details(signal)
        verdict = _signal_verdict(signal)
        name = getattr(signal, "name", "сигнал")

        # 1. Подпись генератора в контейнере или метаданных — сильнейший
        #    признак: такую строку пишут сами инструменты генерации.
        generators = details.get("generator_hits") or []
        if generators:
            hits.append(RuleHit(
                "generator", "Следы генератора",
                "fake", 0.85,
                f"В файле есть подпись генератора: {', '.join(map(str, generators[:3]))}.",
            ))
            continue

        # 2. Статичная картинка, оформленная как видео.
        if details.get("static_video") is True:
            hits.append(RuleHit(
                "static", "Статичное видео",
                "fake", 0.55,
                "Кадры почти не отличаются: это картинка, оформленная как видео.",
            ))
            continue

        # 3. Артефакты ИИ-генерации по пикселям.
        if name and "ИИ" in str(name) and verdict == "supports_fake":
            hits.append(RuleHit(
                "ai_artifacts", "Артефакты генерации",
                "fake", 0.45,
                getattr(signal, "summary", "Найдены следы синтетического изображения."),
            ))
            continue

        # 4. Следы монтажа — нейтрально, но объясняем.
        editors = details.get("editor_hits") or []
        if editors:
            hits.append(RuleHit(
                "editor", "Монтаж",
                "neutral", 0.2,
                f"Файл обработан в редакторе ({', '.join(map(str, editors[:3]))}). "
                "Монтаж сам по себе не делает материал ложным.",
            ))
            continue

        # 5. Метаданные на месте и чистые — слабый довод в пользу подлинности.
        if details.get("metadata") and not details.get("no_metadata"):
            if verdict in ("supports_real", "neutral"):
                hits.append(RuleHit(
                    "metadata", "Метаданные",
                    "real", 0.25,
                    "Метаданные файла на месте, следов генератора в них нет. "
                    "Это не подтверждает содержание, но и не опровергает.",
                ))

        # 6. Метаданных нет — только пояснение, не улика.
        if details.get("no_metadata") is True:
            hits.append(RuleHit(
                "no_metadata", "Метаданных нет",
                "neutral", 0.0,
                "Метаданные стёрты. Мессенджеры удаляют их при пересылке — "
                "это не признак подделки.",
            ))

    return _combine(hits, kind="media")


# --------------------------------------------------------------- текст

def rules_for_text(
    *,
    claims: Sequence[Any],
    sources: int,
    trusted: int,
    kb_hit: bool = False,
    bank_hit: bool = False,
    is_future: bool = False,
    is_vague: bool = False,
    text: str = "",
) -> RuleVerdict:
    """Правила для текста и ссылок: только по найденным источникам."""
    hits: list[RuleHit] = []

    supported = [c for c in claims if getattr(c, "status", "") == "supported"]
    contradicted = [c for c in claims if getattr(c, "status", "") == "contradicted"]
    quoted_supported = [c for c in supported if getattr(c, "quote", "")]
    quoted_contradicted = [c for c in contradicted if getattr(c, "quote", "")]

    # 1. Подтверждение обязано опираться на дословную цитату.
    if quoted_supported:
        hits.append(RuleHit(
            "supported_quoted", "Подтверждение с цитатой",
            "real", 0.8 if len(quoted_supported) > 1 else 0.7,
            f"Источник дословно подтверждает: «{quoted_supported[0].quote[:120]}».",
        ))

    # 2. Опровержение — тоже с цитатой: «такого события нет» без цитаты
    #    слабее прямого «источник говорит обратное».
    if quoted_contradicted:
        hits.append(RuleHit(
            "contradicted_quoted", "Опровержение с цитатой",
            "fake", 0.8 if len(quoted_contradicted) > 1 else 0.7,
            f"Источник опровергает: «{quoted_contradicted[0].quote[:120]}».",
        ))
    elif contradicted:
        hits.append(RuleHit(
            "contradicted_plain", "Опровержение",
            "fake", 0.45,
            "Проверка пришла к опровержению, но дословной цитаты нет — "
            "довод слабее прямого отрицания.",
        ))

    # 3. Прогноз нельзя объявить ложью: событие ещё не наступило.
    #    Это правило строгое и без исключений: даже если база говорит
    #    обратное, «повысят до 70» — прогноз, а не фейк. Ошибка в сторону
    #    осторожности дешевле ошибки в сторону обвинения.
    if is_future:
        hits.append(RuleHit(
            "future", "Прогноз",
            "neutral", 0.0,
            "Это прогноз о будущем: проверить его сейчас нельзя, "
            "поэтому «фейк» не ставится.",
        ))

    # 4. Безымянное утверждение не проверить.
    if is_vague:
        hits.append(RuleHit(
            "vague", "Нет конкретики",
            "neutral", 0.0,
            "В утверждении нет имён и чисел — проверить нечего.",
        ))

    # 5. Готовое знание: курируемая база или банк.
    if kb_hit:
        hits.append(RuleHit(
            "kb", "Курируемая база",
            "real", 0.6,
            "Утверждение сверено с курируемой базой фактов редакции.",
        ))
    if bank_hit:
        hits.append(RuleHit(
            "bank", "Банк знаний",
            "real", 0.5,
            "Такое утверждение уже проверялось ранее — ответ из банка знаний.",
        ))

    # 6. Источников нет — честная причина, но не улика.
    if not sources:
        hits.append(RuleHit(
            "no_sources", "Источников нет",
            "neutral", 0.0,
            "Источников по теме не нашлось. Это не значит, что новость ложная.",
        ))
        # Признаки жанра вирусной выдумки работают только когда проверить
        # нечем: если источник есть, его слово важнее стиля текста.
        #
        # Вес зависит от того, насколько признак однозначен:
        #   * неправдоподобная мера (запрет наличных, роспуск Госдумы,
        #     комендантский час) — сильный признак, решает сама;
        #   * два и более независимых признака — весомо вместе;
        #   * один стилистический признак («учёные нашли») — только
        #     пометка, вердикт по нему не ставится.
        markers = fake_markers.find_markers(text or "")
        if markers:
            keys = {m.key for m in markers}
            if "absurd_measure" in keys:
                weight, title = 0.7, "Неправдоподобная мера"
            elif len(markers) >= 2:
                weight, title = 0.6, "Несколько признаков выдумки"
            else:
                # Один признак жанра — только пометка. Вес ниже порога
                # решения (55), иначе «Учёные нашли воду на Марсе» —
                # правдоподобная новость — получала бы «фейк».
                weight, title = 0.3, "Признак вирусной выдумки"
            hits.append(RuleHit(
                "fake_markers", title, "fake", weight,
                fake_markers.explain(markers),
            ))
    elif not trusted:
        hits.append(RuleHit(
            "no_trusted", "Недоверенные источники",
            "neutral", 0.0,
            "Все найденные источники вне списка доверенных: опираться не на что.",
        ))

    return _combine(hits, kind="text", block_fake=is_future)


# --------------------------------------------------------------- итог

def _combine(
    hits: Sequence[RuleHit], *, kind: str, block_fake: bool = False
) -> RuleVerdict:
    """Свести сработавшие правила в вердикт.

    Логика проста и объяснима:

    * сильный признак (>= DECISIVE) решает сам;
    * иначе сравниваем суммарный вес «за фейк» и «за подлинность»;
    * если обе стороны весомы — «непонятно», а не выбор наугад;
    * если весомых доводов нет — «непонятно» с честной причиной.

    ``block_fake`` — правило темы запрещает вердикт «фейк». Так работает
    прогноз: будущее событие нельзя объявить ложью, каким бы сильным ни
    казался довод. В этом случае «фейк» понижается до «непонятно» с
    объяснением, а не тихо остаётся.
    """
    result = RuleVerdict(hits=list(hits))

    fake_hits = [h for h in hits if h.direction == "fake" and h.weight > 0]
    real_hits = [h for h in hits if h.direction == "real" and h.weight > 0]

    fake_weight = sum(h.weight for h in fake_hits)
    real_weight = sum(h.weight for h in real_hits)

    strongest_fake = max((h.weight for h in fake_hits), default=0.0)
    strongest_real = max((h.weight for h in real_hits), default=0.0)

    def _blocked(reason: str) -> RuleVerdict:
        """«Фейк» запрещён правилом темы — понижаем до «непонятно»."""
        result.verdict = "непонятно"
        result.confidence = 15
        result.summary = f"Непонятно: {reason}"
        return result

    block_reason = "это прогноз о будущем — событие ещё не наступило, «фейк» не ставится."

    # Сильный признак решает сам — но только если с другой стороны нет
    # столь же сильного. Два сильных довода в разные стороны = спор.
    if strongest_fake >= DECISIVE and strongest_real < DECISIVE:
        if block_fake:
            return _blocked(block_reason)
        result.verdict = "фейк"
        result.confidence = round(min(95, 50 + strongest_fake * 50))
        result.summary = (
            f"Фейк: {fake_hits[0].reason}"
            if fake_hits else "Фейк: найден решающий признак подделки."
        )
        return result

    if strongest_real >= DECISIVE and strongest_fake < DECISIVE:
        result.verdict = "правда"
        result.confidence = round(min(95, 50 + strongest_real * 50))
        result.summary = (
            f"Правда: {real_hits[0].reason}"
            if real_hits else "Правда: найдено решающее подтверждение."
        )
        return result

    if fake_weight and real_weight:
        result.verdict = "непонятно"
        # Чем ближе стороны по весу, тем меньше уверенность.
        gap = abs(fake_weight - real_weight) / max(fake_weight, real_weight)
        result.confidence = round(min(45, 20 + gap * 25))
        result.summary = (
            "Непонятно: признаки противоречат друг другу — "
            f"за подделку {round(fake_weight, 2)}, за подлинность {round(real_weight, 2)}."
        )
        return result

    if fake_weight:
        if block_fake:
            return _blocked(block_reason)
        # Слабый признак (один стилистический маркер) — не основание для
        # приговора. Возвращаем «непонятно» с честным объяснением, что
        # именно насторожило. Так «Учёные нашли воду на Марсе» — реальная
        # новость — не превращается в «фейк» из-за слова «учёные».
        if fake_weight < WEAK:
            result.verdict = "непонятно"
            result.confidence = 25
            result.summary = (
                f"Непонятно: {fake_hits[0].reason} Но одного этого признака "
                "мало для вывода — нужны источники."
            )
            return result
        result.verdict = "фейк"
        strong = fake_weight >= DECISIVE or len(fake_hits) >= 2
        base = 55 if strong else 40
        result.confidence = round(min(85, base + fake_weight * 30))
        result.summary = f"Фейк: {fake_hits[0].reason}"
        return result

    if real_weight:
        result.verdict = "правда"
        result.confidence = round(min(85, 40 + real_weight * 40))
        result.summary = f"Правда: {real_hits[0].reason}"
        return result

    # Ни одного весомого довода.
    result.verdict = "непонятно"
    result.confidence = 10
    neutral = next((h for h in hits if h.direction == "neutral"), None)
    result.summary = (
        f"Непонятно: {neutral.reason}" if neutral
        else "Непонятно: признаков недостаточно, чтобы вынести вердикт."
    )
    return result


def describe_rules(kind: str) -> list[dict[str, str]]:
    """Каталог правил для интерфейса: что именно проверяется."""
    if kind == "media":
        return [
            {"key": "generator", "title": "Подпись генератора",
             "detail": "Строка генератора в метаданных контейнера — сильный признак подделки."},
            {"key": "static", "title": "Статичное видео",
             "detail": "Кадры не меняются: картинка оформлена как видео."},
            {"key": "ai_artifacts", "title": "Артефакты ИИ",
             "detail": "Пиксельные признаки синтетического изображения."},
            {"key": "editor", "title": "Монтаж",
             "detail": "Следы редактора — нейтрально: так обрабатывают и настоящие файлы."},
            {"key": "metadata", "title": "Метаданные",
             "detail": "Метаданные на месте и без следов генератора — слабый довод за подлинность."},
            {"key": "no_metadata", "title": "Метаданных нет",
             "detail": "Мессенджеры стирают метаданные — это не улика."},
        ]
    return [
        {"key": "supported_quoted", "title": "Подтверждение с цитатой",
         "detail": "Источник дословно говорит то же самое — сильный довод за правду."},
        {"key": "contradicted_quoted", "title": "Опровержение с цитатой",
         "detail": "Источник прямо отрицает событие — сильный довод за фейк."},
        {"key": "contradicted_plain", "title": "Опровержение без цитаты",
         "detail": "Вывод об опровержении есть, но дословной цитаты нет — довод слабее."},
        {"key": "future", "title": "Прогноз",
         "detail": "Будущее событие нельзя объявить ложью."},
        {"key": "vague", "title": "Нет конкретики",
         "detail": "Без имён и чисел проверять нечего."},
        {"key": "kb", "title": "Курируемая база",
         "detail": "Сверка с базой фактов редакции."},
        {"key": "bank", "title": "Банк знаний",
         "detail": "Утверждение уже проверялось — ответ из банка."},
        {"key": "no_sources", "title": "Источников нет",
         "detail": "Отсутствие источников не делает новость ложной."},
    ]
