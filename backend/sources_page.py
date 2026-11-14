"""Публичная витрина базы фактов: что система умеет проверять.

Обычно такие проекты прячут ограничения. Здесь наоборот: список тем с
первоисточниками открыт. Это работает на доверие — видно, где система
знает, а где честно скажет «непонятно».

Страница серверная: индексируется, открывается без JS, ссылку можно
дать жюри и любому пользователю.
"""

from __future__ import annotations

import html
import json
import pathlib
from typing import Any, Optional

KB_PATH = (
    pathlib.Path(__file__).resolve().parent.parent
    / "ml"
    / "lakmus"
    / "data"
    / "kb_facts.json"
)


def _esc(value: Any) -> str:
    return html.escape(str(value or ""), quote=True)


def load_topics(path: Optional[pathlib.Path] = None) -> list[dict[str, Any]]:
    """Темы из базы. Пустой список, если база недоступна — страница не падает."""
    target = path or KB_PATH
    try:
        data = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    return [t for t in data.get("topics", []) if isinstance(t, dict)]


def topics_html(topics: list[dict[str, Any]]) -> str:
    """Карточки тем с фактами и ссылками на первоисточники."""
    if not topics:
        return (
            '<p class="empty">База фактов недоступна. Проверка работает, '
            "но список тем показать не можем.</p>"
        )

    cards = []
    for topic in topics:
        facts = topic.get("facts", [])
        rows = []
        for fact in facts:
            url = str(fact.get("url", ""))
            source = str(fact.get("source", ""))
            link = (
                f'<a href="{_esc(url)}" target="_blank" rel="noreferrer noopener">'
                f"{_esc(source or url)}</a>"
                if url
                else f"<span>{_esc(source)}</span>"
            )
            verdict = str(fact.get("verdict", ""))
            mark = "✓" if verdict == "true" else "✕"
            tone = "ok" if verdict == "true" else "bad"
            rows.append(
                f'<li class="fact">'
                f'<span class="fact__mark fact__mark--{tone}">{mark}</span>'
                f'<div><p class="fact__text">{_esc(fact.get("claim", ""))}</p>'
                f'<p class="fact__src">{link}</p></div></li>'
            )
        cards.append(
            f'<article class="topic">'
            f'<h3 class="topic__name">{_esc(topic.get("topic", ""))}</h3>'
            f'<ul class="facts">{"".join(rows)}</ul>'
            f"</article>"
        )

    return '<div class="topics">' + "".join(cards) + "</div>"


def page_html(topics: list[dict[str, Any]], canonical_url: str) -> str:
    total_facts = sum(len(t.get("facts", [])) for t in topics)
    count_text = (
        f"{len(topics)} тем · {total_facts} фактов с первоисточниками"
        if topics
        else "база недоступна"
    )

    return f"""<!doctype html>
<html lang="ru">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Что мы проверяем</title>
<meta name="description" content="Открытый список тем и первоисточников, по которым система проверяет утверждения.">
<link rel="canonical" href="{_esc(canonical_url)}">
<style>
:root {{
  --bg: #f7f7f5; --surface: #fff; --fg: #17191b; --muted: #62666c;
  --line: #dedfdc; --accent: #1a5f4a; --ok: #1a6b4a; --bad: #9d2b2b;
  color-scheme: light;
}}
@media (prefers-color-scheme: dark) {{
  :root {{
    --bg: #101214; --surface: #191c1f; --fg: #e9ebed; --muted: #979da5;
    --line: #2b3036; --accent: #6fc9ab; --ok: #7fd6ae; --bad: #e88b8b;
    color-scheme: dark;
  }}
}}
* {{ box-sizing: border-box; }}
body {{
  margin: 0; background: var(--bg); color: var(--fg);
  font: 16px/1.6 -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
  padding: 24px 16px 64px;
}}
.wrap {{ max-width: 760px; margin: 0 auto; }}
.head {{ display: flex; align-items: center; gap: 8px; margin-bottom: 28px;
  font-size: 15px; font-weight: 600; }}
.head a {{ color: var(--fg); text-decoration: none; }}
.dot {{ width: 16px; height: 16px; border-radius: 50%; border: 2px solid var(--accent);
  position: relative; }}
.dot::after {{ content: ''; position: absolute; inset: 3px; border-radius: 50%;
  background: var(--accent); }}
.eyebrow {{ font-size: 11px; letter-spacing: .12em; text-transform: uppercase;
  color: var(--muted); margin: 0 0 8px; font-weight: 500; }}
h1 {{ margin: 0 0 10px; font-size: clamp(26px, 4vw, 34px); line-height: 1.15;
  letter-spacing: -.02em; text-wrap: balance; }}
.lead {{ margin: 0 0 8px; color: var(--muted); max-width: 62ch; }}
.count {{ font-size: 13px; color: var(--muted); font-variant-numeric: tabular-nums; }}
.honest {{
  background: var(--surface); border: 1px solid var(--line); border-radius: 12px;
  padding: 16px 18px; margin: 22px 0 26px; font-size: 14px; color: var(--muted);
  line-height: 1.6;
}}
.honest b {{ color: var(--fg); font-weight: 600; }}
.topics {{ display: grid; gap: 12px; grid-template-columns: repeat(auto-fill, minmax(320px, 1fr)); }}
.topic {{
  background: var(--surface); border: 1px solid var(--line); border-radius: 12px;
  padding: 16px 18px;
}}
.topic__name {{ margin: 0 0 10px; font-size: 15px; font-weight: 600; }}
.facts {{ list-style: none; margin: 0; padding: 0; display: flex;
  flex-direction: column; gap: 10px; }}
.fact {{ display: flex; gap: 9px; align-items: flex-start; }}
.fact__mark {{ flex: 0 0 18px; height: 18px; border-radius: 50%; display: grid;
  place-items: center; font-size: 11px; font-weight: 700; margin-top: 3px; }}
.fact__mark--ok {{ background: rgba(26, 107, 74, .12); color: var(--ok); }}
.fact__mark--bad {{ background: rgba(157, 43, 43, .12); color: var(--bad); }}
.fact__text {{ margin: 0 0 3px; font-size: 14px; line-height: 1.5; }}
.fact__src {{ margin: 0; font-size: 12.5px; }}
.fact__src a {{ color: var(--accent); text-decoration: none; }}
.fact__src a:hover {{ text-decoration: underline; }}
.fact__src span {{ color: var(--muted); }}
.empty {{ color: var(--muted); }}
.cta {{ display: block; text-align: center; background: var(--accent); color: #fff;
  text-decoration: none; border-radius: 10px; padding: 13px; font-weight: 600;
  margin-top: 28px; }}
@media (prefers-color-scheme: dark) {{ .cta {{ color: #0e1210; }} }}
@media (max-width: 680px) {{ .topics {{ grid-template-columns: 1fr; }} }}
</style>
</head>
<body>
<div class="wrap">
  <div class="head"><span class="dot"></span><a href="/">Ревизор</a></div>

  <p class="eyebrow">Открытая база</p>
  <h1>Что мы проверяем</h1>
  <p class="lead">Список тем, по которым у нас есть первоисточники. Всё остальное
  система честно помечает как непроверенное — и это не сбой, а правило.</p>
  <p class="count">{_esc(count_text)}</p>

  <div class="honest">
    <b>Почему мы это публикуем.</b> Фактчекер, который отвечает на всё, обычно
    врёт на половине вопросов. Мы показываем границы своей базы, чтобы было
    видно, где ответу можно доверять, а где нужно идти к первоисточнику самому.
    Знак <b>✕</b> — запись, которая опровергает распространённое утверждение.
  </div>

  {topics_html(topics)}

  <a class="cta" href="/">Проверить своё сообщение</a>
</div>
</body>
</html>"""
