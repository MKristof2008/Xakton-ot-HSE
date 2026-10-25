"""Генератор документа «Методология» (раздел 6.9 п.5 ТЗ).

Документ собирается из данных, а не пишется руками: реестр сигналов и
``FUSION_CONFIG`` — единственный источник цифр. Если поменялся порог
Тумана или надёжность сигнала, документ перегенерируется и не врёт.

Публичная точка входа — :func:`build_methodology`; файл пишет
``ml/tools/methodology.py``.
"""

from __future__ import annotations

from typing import Any, Mapping, Sequence

#: Этапы проверки по-русски: как в интерфейсе и в отчётах.
STAGE_TITLES: dict[str, str] = {
    "provenance": "происхождение",
    "artifacts": "артефакты",
    "sources": "источники",
    "context": "контекст",
}

#: Пять уровней доверия и то, что они значат для пользователя.
LEVEL_TITLES: list[tuple[str, str]] = [
    (
        "confirmed",
        "Подтверждено",
    ),
    (
        "likely_real",
        "Скорее настоящее",
    ),
    (
        "fog",
        "Туман",
    ),
    (
        "doubtful",
        "Сомнительно",
    ),
    (
        "likely_fake",
        "Скорее подделка",
    ),
]

#: Человеческие пояснения к уровням.
LEVEL_NOTES: dict[str, str] = {
    "confirmed": "уверенно настоящее и есть якорь происхождения (C2PA или первоисточник)",
    "likely_real": "уверенно настоящее, но происхождение не подтверждено",
    "fog": "данных не хватает или сигналы противоречат друг другу — система не отвечает «да/нет»",
    "doubtful": "перевес в сторону подделки, но уверенности мало",
    "likely_fake": "уверенно подделка или правка",
}


def _meta_field(item: Mapping[str, Any], *names: str, default: str = "") -> str:
    for name in names:
        value = item.get(name)
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    return default


def _reliability_text(value: Any) -> str:
    if value is None:
        return "—"
    try:
        return f"{float(value):.2f}"
    except (TypeError, ValueError):
        return "—"


def _limits_list(item: Mapping[str, Any]) -> list[str]:
    raw = item.get("limits") or item.get("limitations") or item.get("ограничения")
    if not raw:
        return []
    if isinstance(raw, str):
        return [part.strip() for part in raw.split(";") if part.strip()]
    return [str(part).strip() for part in raw if str(part).strip()]


def _signals_table(signals_meta: Sequence[Mapping[str, Any]]) -> list[str]:
    lines = [
        "| id | сигнал | этап | надёжность | что показывает |",
        "| --- | --- | --- | --- | --- |",
    ]
    for item in signals_meta:
        signal_id = _meta_field(item, "id", default="—")
        name = _meta_field(item, "name", "title", default="—")
        stage = _meta_field(item, "stage", default="")
        stage_title = STAGE_TITLES.get(stage, stage or "—")
        reliability = _reliability_text(item.get("reliability"))
        what = _meta_field(item, "what", "summary", "description", default="—")
        lines.append(
            f"| `{signal_id}` | {name} | {stage_title} | {reliability} | {what} |"
        )
    return lines


def _limits_section(signals_meta: Sequence[Mapping[str, Any]]) -> list[str]:
    lines: list[str] = []
    for item in signals_meta:
        limits = _limits_list(item)
        if not limits:
            continue
        signal_id = _meta_field(item, "id", default="—")
        name = _meta_field(item, "name", "title", default="—")
        joined = "; ".join(limits)
        lines.append(f"- **{signal_id}** ({name}): {joined}")
    if not lines:
        lines.append("- Ограничения по сигналам не заданы в реестре.")
    return lines


def _levels_section(fusion_config: Mapping[str, Any]) -> list[str]:
    bands = fusion_config.get("level_bands") or {}
    confirmed = fusion_config.get("confirmed_score", 80.0)
    fog = fusion_config.get("fog_threshold", 0.40)
    likely_real = bands.get("likely_real", 60.0)
    doubtful = bands.get("doubtful", 35.0)

    conditions = {
        "fog": f"`uncertainty > {fog}` **или** конфликт сигналов",
        "confirmed": f"`score >= {confirmed}` и есть якорь происхождения",
        "likely_real": f"`score >= {likely_real}`, якоря нет",
        "doubtful": f"`{doubtful} <= score < {likely_real}`",
        "likely_fake": f"`score < {doubtful}`",
    }
    lines = [
        "| уровень | код | условие | что это значит |",
        "| --- | --- | --- | --- |",
    ]
    for code, title in LEVEL_TITLES:
        lines.append(
            f"| {title} | `{code}` | {conditions[code]} | {LEVEL_NOTES[code]} |"
        )
    lines.append("")
    lines.append(
        "Порядок проверки условий важен: «Туман» проверяется первым, поэтому "
        "высокий score при конфликте всё равно даёт «Туман»."
    )
    return lines


def build_methodology(
    signals_meta: Sequence[Mapping[str, Any]], fusion_config: Mapping[str, Any]
) -> str:
    """Собирает Markdown-документ «Методология».

    ``signals_meta`` — реестр сигналов: словари с полями ``id``, ``name``,
    ``stage`` (``provenance`` / ``artifacts`` / ``sources`` / ``context``),
    ``reliability`` (0..1 или ``None``, если надёжность не измерена),
    ``what`` (одна фраза, что показывает сигнал) и ``limits`` (список или
    строка через ``;``).

    ``fusion_config`` — ``FUSION_CONFIG`` из ``lakmus.fusion``: пороги
    Тумана, якоря и полосы уровней берутся из него, а не дублируются в
    тексте.

    Документ детерминирован: одинаковый вход даёт одинаковый Markdown,
    поэтому его можно держать в git и проверять диффом.
    """
    strong = fusion_config.get("strong_belief", 0.6)
    bonus = fusion_config.get("conflict_uncertainty_bonus", 0.2)
    coverage_floor = fusion_config.get("coverage_floor", 0.5)
    uncertainty_floor = fusion_config.get("uncertainty_floor", 0.45)
    fog_threshold = fusion_config.get("fog_threshold", 0.40)
    anchor = fusion_config.get("provenance_reliability", 0.8)

    lines: list[str] = [
        "# Методология оценки доверия",
        "",
        "Документ сгенерирован `ml/tools/methodology.py` из реестра сигналов и "
        "`ml/lakmus/fusion.py`. Руками не правится: правка живёт в коде, "
        "документ перегенерируется.",
        "",
        "## 1. Что делает система",
        "",
        "«Лакмус» не выносит приговор «это правда» или «это ложь». Он собирает "
        "независимые сигналы, сливает их в одно мнение и показывает, **насколько "
        "система уверена** и **чего она не знает**. Если данных мало или сигналы "
        "противоречат друг другу, честный ответ — «Туман», а не догадка.",
        "",
        "Каждый сигнал отвечает на свой узкий вопрос: есть ли манифест "
        "происхождения, оставила ли следы генеративная модель, находится ли "
        "первоисточник, противоречат ли утверждения источникам. Сигнал, который "
        "не смог отработать, возвращает `unavailable` — он не тянет результат "
        "к нулю, но снижает покрытие.",
        "",
        "## 2. Сигналы",
        "",
        "Надёжность — насколько сигналу можно верить, когда он сработал "
        "(0 — шум, 1 — почти безошибочно). «—» означает, что надёжность не "
        "измерена: сигнал пока не участвует в score как доказательство.",
        "",
    ]
    lines.extend(_signals_table(signals_meta))
    lines.extend(["", "### Ограничения сигналов", ""])
    lines.extend(_limits_section(signals_meta))
    lines.extend(
        [
            "",
            "## 3. Формулы",
            "",
            "### 3.1 Мнение одного сигнала",
            "",
            "Сигнал превращается в субъективное мнение `(b, d, u)`: вера в "
            "«настоящее», вера в «подделку», неопределённость. Сумма всегда 1.",
            "",
            "```",
            "если verdict = supports_real:  b = strength * reliability, d = 0, u = 1 - b",
            "если verdict = supports_fake:  d = strength * reliability, b = 0, u = 1 - d",
            "если verdict = neutral или unavailable:  b = d = 0, u = 1",
            "```",
            "",
            "`strength` — насколько сигнал уверен в своём выводе, `reliability` — "
            "насколько ему можно верить в принципе. Слабое свидетельство от "
            "надёжного сигнала даёт маленькое `b` и большое `u`.",
            "",
            "### 3.2 Слияние сигналов (субъективная логика Йосанга)",
            "",
            "Мнения сливаются попарно, порядок не важен:",
            "",
            "```",
            "kappa = u1 + u2 - u1 * u2",
            "b     = (b1 * u2 + b2 * u1) / kappa",
            "d     = (d1 * u2 + d2 * u1) / kappa",
            "u     = (u1 * u2) / kappa",
            "```",
            "",
            "Если оба мнения абсолютно уверены и противоположны "
            "(`kappa = 0`), вера усредняется: `b = d = (b1 + b2) / 2`, `u = 0`.",
            "Согласные сигналы уменьшают `u` и увеличивают `b`; противоречащие "
            "оставляют `u` высоким.",
            "",
            "### 3.3 Итоговые числа",
            "",
            "```",
            "вероятность = b + 0.5 * u",
            "score       = round(100 * вероятность)            # 0..100",
            "uncertainty = u",
            f"uncertainty += {bonus} при конфликте (есть b > {strong} и d > {strong})",
            f"uncertainty  = max(uncertainty, {uncertainty_floor}) при coverage < {coverage_floor}",
            "coverage    = доля сигналов, вернувших не unavailable",
            "```",
            "",
            "`score` — это не «вероятность правды» в бытовом смысле, а положение "
            "на шкале доверия: 50 — «мнения нет», 100 — «все надёжные сигналы "
            "за настоящее». `uncertainty` отвечает за честность: пока она выше "
            f"{fog_threshold}, система отказывается от вердикта.",
            "",
            "### 3.4 Якорь происхождения",
            "",
            f"Уровень «Подтверждено» требует не только высокого score, но и якоря: "
            f"сигнал происхождения с `supports_real` и надёжностью "
            f">= {anchor} (C2PA-манифест или найденный первоисточник). Без якоря "
            "даже идеальный score остаётся «Скорее настоящее»: картинка может "
            "быть настоящей и при этом показывать не то, что написано в подписи.",
            "",
            "## 4. Пять уровней",
            "",
        ]
    )
    lines.extend(_levels_section(fusion_config))
    lines.extend(
        [
            "",
            "## 5. Ограничения метода",
            "",
            "- Ни один сигнал не является доказательством: каждый ошибается, "
            "и надёжность — это оценка частоты ошибок, а не гарантия.",
            "- Слияние не умеет вскрывать подделку, оставившую мало следов: "
            "если все сигналы молчат, результат — «Туман», а не «настоящее».",
            "- `score` не откалиброван как вероятность в статистическом смысле; "
            "калибровка измеряется отдельно на размеченном наборе "
            "(`ml/tools/eval.py`, ECE и кривая риск–покрытие).",
            "- Метка «настоящее» относится к материалу, а не к утверждению: "
            "реальное фото с ложной подписью — не «настоящее сообщение».",
            "- Сигналы, зависящие от внешних сервисов, могут быть недоступны; "
            "тогда покрытие падает, а неопределённость растёт — это видно в "
            "результате, а не скрыто.",
            "",
        ]
    )
    return "\n".join(lines)
