"""Страница «цитата в контексте»: показывает, где именно в источнике
находится фраза, на которую опирается вердикт.

Это визуальное доказательство. Пользователь видит не «система так решила»,
а конкретное место в документе: вот источник, вот абзац, вот фраза.

Работает без JavaScript: подсветка встроена в HTML при рендере.
"""

from __future__ import annotations

import html
import re
from typing import Any, Optional

#: Сколько символов контекста показывать вокруг цитаты.
CONTEXT_CHARS = 700
#: Максимум символов от источника.
MAX_TEXT = 6000


def _esc(value: Any) -> str:
    return html.escape(str(value or ""), quote=True)


def _norm(value: str) -> str:
    """Нормализация для поиска: кавычки, тире, регистр, пробелы."""
    value = value.translate(
        str.maketrans({
            "«": '"', "»": '"', "„": '"', "“": '"', "”": '"',
            "—": "-", "–": "-", "’": "'", "‘": "'",
        })
    )
    value = value.lower().replace("ё", "е")
    return re.sub(r"\s+", " ", value).strip()


def _find_span(haystack: str, needle: str) -> Optional[tuple[int, int]]:
    """Позиция цитаты в исходном тексте, с учётом нормализации.

    Ищем по нормализованной копии, но возвращаем индексы в исходной строке:
    нормализация меняет длину, поэтому строим карту соответствия.
    """
    norm_needle = _norm(needle)
    if len(norm_needle) < 8:
        return None

    # Строим нормализованный текст и карту «норм-индекс → исходный индекс».
    out_chars: list[str] = []
    index_map: list[int] = []
    prev_space = False
    for i, ch in enumerate(haystack):
        translated = ch.translate(
            str.maketrans({
                "«": '"', "»": '"', "„": '"', "“": '"', "”": '"',
                "—": "-", "–": "-", "’": "'", "‘": "'",
            })
        ).lower().replace("ё", "е")
        for sub in translated:
            if sub.isspace():
                if prev_space:
                    continue
                prev_space = True
                out_chars.append(" ")
                index_map.append(i)
            else:
                prev_space = False
                out_chars.append(sub)
                index_map.append(i)

    norm_haystack = "".join(out_chars).strip()
    pos = norm_haystack.find(norm_needle)
    if pos < 0:
        return None
    start = index_map[pos]
    end = index_map[min(pos + len(norm_needle) - 1, len(index_map) - 1)] + 1
    return start, end


def quote_context(
    source_text: str,
    quote: str,
    *,
    before: int = CONTEXT_CHARS,
    after: int = CONTEXT_CHARS,
) -> Optional[dict[str, Any]]:
    """Найти цитату и вернуть контекст до/после с подсветкой.

    Возвращает None, если дословной цитаты в тексте нет. Это не ошибка
    отображения, а результат проверки: цитата модели может быть
    пересказом, и тогда подсвечивать нечего — так и покажем.
    """
    if not source_text or not quote:
        return None
    span = _find_span(source_text, quote)
    if span is None:
        return None

    start, end = span
    left = max(0, start - before)
    right = min(len(source_text), end + after)

    return {
        "before": source_text[left:start],
        "quote": source_text[start:end],
        "after": source_text[end:right],
        "truncated_left": left > 0,
        "truncated_right": right < len(source_text),
        "position": start,
        "total": len(source_text),
        "verbatim": True,
    }


def nearest_fragment(
    source_text: str, quote: str, *, window: int = 260
) -> Optional[dict[str, Any]]:
    """Ближайший фрагмент источника, если дословной цитаты нет.

    Ищем абзац с наибольшим числом общих значимых слов — это честный
    ответ «вот место, о котором речь», без утверждения «цитата дословна».
    """
    if not source_text or not quote:
        return None

    def words(text: str) -> set[str]:
        return {w for w in re.findall(r"[а-яa-z]{5,}", _norm(text))}

    quote_words = words(quote)
    if not quote_words:
        return None

    best_pos = -1
    best_score = 0.0
    for match in re.finditer(r"[^.!?]+[.!?]?", source_text):
        fragment = match.group(0)
        if len(fragment.strip()) < 40:
            continue
        overlap = len(quote_words & words(fragment)) / len(quote_words)
        if overlap > best_score:
            best_score, best_pos = overlap, match.start()

    if best_pos < 0 or best_score < 0.4:
        return None

    start = max(0, best_pos - window // 2)
    end = min(len(source_text), best_pos + window * 2)
    return {
        "fragment": source_text[start:end],
        "score": round(best_score, 2),
        "verbatim": False,
        "truncated_left": start > 0,
        "truncated_right": end < len(source_text),
    }


def highlight_html(
    *,
    claim_text: str,
    quote: str,
    source_title: str,
    source_url: str,
    context: Optional[dict[str, Any]],
    fragment: Optional[dict[str, Any]],
    verdict_label: str,
    level: str,
    canonical_url: str,
) -> str:
    """Страница с подсвеченной цитатой.

    Два честных состояния:
      * цитата найдена дословно — подсвечиваем её;
      * дословной нет — показываем ближайшее место и прямо пишем, что
        это пересказ, а не цитата.
    """
    color = {
        "confirmed": "#1a6b4a",
        "likely_real": "#1a6b4a",
        "fog": "#5a5f68",
        "doubtful": "#8a5a10",
        "likely_fake": "#9d2b2b",
    }.get(level, "#5a5f68")

    if context:
        body = (
            ("…" if context["truncated_left"] else "")
            + _esc(context["before"])
            + "<mark>" + _esc(context["quote"]) + "</mark>"
            + _esc(context["after"])
            + ("…" if context["truncated_right"] else "")
        )
        note = ("Подсвеченная фраза найдена в тексте источника дословно. "
                "Это и есть основание вердикта.")
        label = "В источнике"
    elif fragment:
        body = (
            ("…" if fragment["truncated_left"] else "")
            + _esc(fragment["fragment"])
            + ("…" if fragment["truncated_right"] else "")
        )
        note = ("Дословной цитаты в источнике нет: система пересказала смысл. "
                f"Ниже — ближайшее место, совпадение по словам "
                f"{int(fragment['score'] * 100)}%. Считайте это ориентиром, "
                "а не доказательством.")
        label = "Ближайшее место в источнике"
    else:
        body = "В источнике не нашлось места, о котором говорит утверждение."
        note = "Сверять не с чем: источник не содержит нужного фрагмента."
        label = "В источнике"

    quote_block = ""
    if quote and not context:
        quote_block = (
            '<div class="quote-aside">'
            '<p class="eyebrow">Что сформулировала система</p>'
            f'<p class="quote-aside__text">{_esc(quote)}</p>'
            "</div>"
        )

    return f"""<!doctype html>
<html lang="ru">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Цитата в источнике — {_esc(source_title[:60])}</title>
<meta name="description" content="Где именно в источнике сказано то, на чём основан вердикт.">
<link rel="canonical" href="{_esc(canonical_url)}">
<style>
:root {{
  --bg: #f7f7f5; --surface: #fff; --fg: #17191b; --muted: #62666c;
  --line: #dedfdc; --accent: {color}; --mark: #fff3c4; --mark-fg: #3a2f00;
  color-scheme: light;
}}
@media (prefers-color-scheme: dark) {{
  :root {{
    --bg: #101214; --surface: #191c1f; --fg: #e9ebed; --muted: #979da5;
    --line: #2b3036; --mark: #4a3d12; --mark-fg: #ffe9a8; color-scheme: dark;
  }}
}}
* {{ box-sizing: border-box; }}
body {{
  margin: 0; background: var(--bg); color: var(--fg);
  font: 16px/1.65 -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
  padding: 24px 16px 56px;
}}
.wrap {{ max-width: 680px; margin: 0 auto; }}
.head {{ display: flex; align-items: center; gap: 8px; margin-bottom: 22px;
  font-size: 15px; font-weight: 600; }}
.head a {{ color: var(--fg); text-decoration: none; }}
.dot {{ width: 16px; height: 16px; border-radius: 50%; border: 2px solid var(--accent);
  position: relative; }}
.dot::after {{ content: ''; position: absolute; inset: 3px; border-radius: 50%;
  background: var(--accent); }}
.card {{ background: var(--surface); border: 1px solid var(--line); border-radius: 14px;
  padding: 20px; margin-bottom: 16px; }}
.eyebrow {{ font-size: 11px; letter-spacing: .12em; text-transform: uppercase;
  color: var(--muted); margin: 0 0 8px; font-weight: 500; }}
.claim {{ margin: 0; font-size: 16px; }}
.badge {{ display: inline-block; background: var(--accent); color: #fff;
  border-radius: 999px; padding: 3px 11px; font-size: 12px; font-weight: 600;
  margin-bottom: 10px; }}
@media (prefers-color-scheme: dark) {{ .badge {{ color: #0e1210; }} }}
.source-text {{
  font-size: 16px; line-height: 1.75; margin: 0;
  white-space: pre-wrap; overflow-wrap: anywhere;
}}
mark {{
  background: var(--mark); color: var(--mark-fg);
  padding: 2px 3px; border-radius: 3px; font-weight: 600;
  box-decoration-break: clone; -webkit-box-decoration-break: clone;
}}
.quote-aside {{
  margin-top: 16px; padding-top: 14px; border-top: 1px dashed var(--line);
}}
.quote-aside__text {{
  margin: 0; font-style: italic; color: var(--muted); font-size: 15px;
}}
.src {{ display: flex; flex-wrap: wrap; gap: 6px 14px; align-items: baseline;
  font-size: 13.5px; color: var(--muted); margin-top: 14px; }}
.src a {{ color: var(--accent); text-decoration: none; }}
.src a:hover {{ text-decoration: underline; }}
.cta {{ display: block; text-align: center; background: var(--accent); color: #fff;
  text-decoration: none; border-radius: 10px; padding: 13px; font-weight: 600; }}
@media (prefers-color-scheme: dark) {{ .cta {{ color: #0e1210; }} }}
.note {{ font-size: 12.5px; color: var(--muted); margin-top: 14px; text-align: center;
  line-height: 1.55; }}
</style>
</head>
<body>
<div class="wrap">
  <div class="head"><span class="dot"></span><a href="/">Ревизор</a></div>

  <section class="card">
    <p class="eyebrow">Утверждение</p>
    <span class="badge">{_esc(verdict_label)}</span>
    <p class="claim">{_esc(claim_text)}</p>
  </section>

  <section class="card">
    <p class="eyebrow">{_esc(label)}</p>
    <p class="source-text">{body}</p>
    <div class="src">
      <span>{_esc(source_title)}</span>
      <a href="{_esc(source_url)}" target="_blank" rel="noreferrer noopener">открыть источник →</a>
    </div>
    {quote_block}
  </section>

  <a class="cta" href="/">Проверить своё сообщение</a>
  <p class="note">{note}</p>
</div>
</body>
</html>"""


def build_page(
    *,
    claim_text: str,
    quote: str,
    source_title: str,
    source_url: str,
    source_text: str,
    verdict_label: str,
    level: str,
    canonical_url: str,
    fallback_text: str = "",
    fallback_title: str = "",
) -> str:
    """Собрать страницу: дословная цитата → ближайший фрагмент → запасной текст.

    Скачанная страница часто оказывается не тем документом: ссылка ведёт
    на раздел, а не на пресс-релиз. Тогда честнее показать локальную
    запись базы фактов, чем свалку навигации с чужого сайта.
    """
    context = quote_context(source_text, quote)
    fragment = None if context else nearest_fragment(source_text, quote)

    if context is None and fallback_text:
        fb_context = quote_context(fallback_text, quote)
        if fb_context is not None:
            context, fragment = fb_context, None
            source_text, source_title = fallback_text, fallback_title or source_title
        elif fragment is None:
            fb_fragment = nearest_fragment(fallback_text, quote)
            if fb_fragment is not None:
                fragment = fb_fragment
                source_text, source_title = fallback_text, fallback_title or source_title
    return highlight_html(
        claim_text=claim_text,
        quote=quote,
        source_title=source_title,
        source_url=source_url,
        context=context,
        fragment=fragment,
        verdict_label=verdict_label,
        level=level,
        canonical_url=canonical_url,
    )
