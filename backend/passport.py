"""Публичная страница «паспорта утверждения».

Одна проверка = одна постоянная ссылка. Её кидают в чат, и получатель
видит вердикт, цитату из первоисточника и дату проверки — без входа,
без JS, без приложения.

Страница собирается на сервере: так работают превью в Telegram и
WhatsApp, где клиент читает только первые килобайты HTML и не исполняет
скрипты.
"""

from __future__ import annotations

import html
import json
from typing import Any, Optional

#: Сколько раз показывать текст утверждения в превью.
PREVIEW_CHARS = 120


def _esc(value: Any) -> str:
    return html.escape(str(value or ""), quote=True)


def _level_style(level: str) -> tuple[str, str, str]:
    """Цвет, иконка и подпись уровня."""
    return {
        "confirmed": ("#1a6b4a", "#e3f2ea", "✓", "Подтверждено"),
        "likely_real": ("#1a6b4a", "#e3f2ea", "✓", "Скорее правда"),
        "fog": ("#5a5f68", "#e9ebee", "?", "Туман"),
        "doubtful": ("#8a5a10", "#f6ebd8", "!", "Сомнительно"),
        "likely_fake": ("#9d2b2b", "#f7e2e2", "✕", "Скорее фейк"),
    }.get(level, ("#5a5f68", "#e9ebee", "?", "Непонятно"))


def passport_html(
    *,
    text: str,
    verdict: str,
    level: str,
    score: int,
    claims: list[dict[str, Any]],
    checks_count: int,
    checked_at: str,
    canonical_url: str,
    hash_value: str = "",
    site_name: str = "Ревизор",
) -> str:
    """Полная HTML-страница паспорта."""
    color, bg, icon, label = _level_style(level)

    # Цитата-основание: первая найденная в проверке.
    quote = ""
    source_title = ""
    source_url = ""
    for claim in claims:
        if claim.get("quote"):
            quote = str(claim["quote"])
            source_title = str(claim.get("source_title") or "")
            source_url = str(claim.get("source_url") or "")
            break

    preview_text = text[:PREVIEW_CHARS] + ("…" if len(text) > PREVIEW_CHARS else "")
    title = f"{label}: {preview_text}"
    description = (
        f"Ревизор: проверено {checked_at}. {score} из 100."
        + (f" Источник: {source_title}." if source_title else "")
    )

    claims_html = ""
    for claim in claims:
        status = str(claim.get("status", ""))
        mark = {
            "supported": "✓",
            "contradicted": "✕",
            "context": "!",
            "insufficient": "?",
        }.get(status, "?")
        explanation = _esc(claim.get("explanation", ""))
        claim_text = _esc(claim.get("text", ""))
        claims_html += f"""
        <li class="claim">
          <span class="claim__mark claim__mark--{_esc(status)}">{mark}</span>
          <div>
            <p class="claim__text">{claim_text}</p>
            <p class="claim__why">{explanation}</p>
          </div>
        </li>"""

    # Ссылка «где именно в источнике» — на первое утверждение с цитатой.
    quote_index = next(
        (i for i, c in enumerate(claims) if c.get("quote")), None
    )
    quote_link = (
        f'<a class="source" href="/p/{hash_value}/quote/{quote_index}">'
        "где именно в источнике →</a>"
        if quote_index is not None and hash_value
        else ""
    )

    quote_html = ""
    if quote:
        link = (
            f'<a class="source" href="{_esc(source_url)}" rel="noreferrer noopener" '
            f'target="_blank">{_esc(source_title or source_url)} →</a>'
            if source_url
            else f'<span class="source">{_esc(source_title)}</span>'
        )
        quote_html = f"""
      <section class="quote-block">
        <p class="eyebrow">Чем подтверждено</p>
        <blockquote>{_esc(quote)}</blockquote>
        {link}
        {quote_link}
      </section>"""

    return f"""<!doctype html>
<html lang="ru">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{_esc(title)}</title>
<meta name="description" content="{_esc(description)}">
<link rel="canonical" href="{_esc(canonical_url)}">
<meta property="og:type" content="article">
<meta property="og:site_name" content="{_esc(site_name)}">
<meta property="og:title" content="{_esc(title)}">
<meta property="og:description" content="{_esc(description)}">
<meta property="og:url" content="{_esc(canonical_url)}">
<meta name="twitter:card" content="summary">
<meta name="twitter:title" content="{_esc(title)}">
<meta name="twitter:description" content="{_esc(description)}">
<style>
:root {{
  --bg: #f7f7f5; --surface: #fff; --fg: #17191b; --muted: #62666c;
  --line: #dedfdc; --accent: {color};
  color-scheme: light;
}}
@media (prefers-color-scheme: dark) {{
  :root {{
    --bg: #101214; --surface: #191c1f; --fg: #e9ebed; --muted: #979da5;
    --line: #2b3036; color-scheme: dark;
  }}
}}
* {{ box-sizing: border-box; }}
body {{
  margin: 0; background: var(--bg); color: var(--fg);
  font: 16px/1.55 -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
  padding: 24px 16px 56px;
}}
.wrap {{ max-width: 620px; margin: 0 auto; }}
.head {{ display: flex; align-items: center; gap: 8px; margin-bottom: 24px;
  font-size: 15px; font-weight: 600; }}
.head a {{ color: var(--fg); text-decoration: none; }}
.dot {{ width: 16px; height: 16px; border-radius: 50%; border: 2px solid var(--accent);
  position: relative; }}
.dot::after {{ content: ''; position: absolute; inset: 3px; border-radius: 50%;
  background: var(--accent); }}
.card {{ background: var(--surface); border: 1px solid var(--line); border-radius: 14px;
  padding: 22px; margin-bottom: 16px; }}
.verdict {{ border-left: 4px solid var(--accent); }}
.eyebrow {{ font-size: 11px; letter-spacing: .12em; text-transform: uppercase;
  color: var(--muted); margin: 0 0 6px; font-weight: 500; }}
.badge {{ display: inline-flex; align-items: center; gap: 7px; background: {bg};
  color: {color}; border-radius: 999px; padding: 5px 13px; font-size: 13px;
  font-weight: 600; margin-bottom: 12px; }}
.score {{ float: right; text-align: right; line-height: 1; }}
.score b {{ font-size: 30px; font-variant-numeric: tabular-nums; }}
.score span {{ display: block; font-size: 11px; color: var(--muted); margin-top: 3px; }}
blockquote {{ margin: 8px 0 10px; padding-left: 14px; border-left: 3px solid var(--line);
  color: var(--fg); font-style: italic; }}
.source {{ font-size: 14px; color: var(--accent); text-decoration: none; }}
.source:hover {{ text-decoration: underline; }}
.claims {{ list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column;
  gap: 14px; }}
.claim {{ display: flex; gap: 11px; }}
.claim__mark {{ flex: 0 0 20px; height: 20px; border-radius: 50%; display: grid;
  place-items: center; font-size: 12px; font-weight: 700; margin-top: 2px; }}
.claim__mark--supported {{ background: #e3f2ea; color: #1a6b4a; }}
.claim__mark--contradicted {{ background: #f7e2e2; color: #9d2b2b; }}
.claim__mark--insufficient, .claim__mark--context {{ background: #e9ebee; color: #5a5f68; }}
.claim__text {{ margin: 0 0 3px; font-size: 15px; }}
.claim__why {{ margin: 0; font-size: 14px; color: var(--muted); }}
.meta {{ display: flex; flex-wrap: wrap; gap: 6px 18px; font-size: 13px; color: var(--muted); }}
.cta {{ display: block; text-align: center; background: var(--accent); color: #fff;
  text-decoration: none; border-radius: 10px; padding: 13px; font-weight: 600;
  font-size: 15px; }}
@media (prefers-color-scheme: dark) {{ .cta {{ color: #0e1210; }} }}
.foot {{ margin-top: 22px; font-size: 12.5px; color: var(--muted); text-align: center; }}
</style>
</head>
<body>
<div class="wrap">
  <div class="head"><span class="dot"></span><a href="/">{_esc(site_name)}</a></div>

  <section class="card verdict">
    <div class="score"><b>{score}</b><span>из 100</span></div>
    <p class="eyebrow">Вердикт</p>
    <span class="badge">{icon} {_esc(label)}</span>
    <p style="margin:0;font-size:17px;line-height:1.5">{_esc(text)}</p>
  </section>
{quote_html}
  <section class="card">
    <p class="eyebrow">Разбор</p>
    <ul class="claims">{claims_html}
    </ul>
  </section>

  <section class="card">
    <div class="meta">
      <span>Проверено: {_esc(checked_at)}</span>
      <span>Проверок этого утверждения: {checks_count}</span>
    </div>
  </section>

  <a class="cta" href="/">Проверить своё сообщение</a>
  <p class="foot">Ревизор — сверяем утверждения с первоисточниками.
  Если данных нет, говорим «непонятно», а не угадываем.</p>
</div>
</body>
</html>"""
