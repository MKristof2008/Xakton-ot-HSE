"""FastAPI API «Свидетель» — маркетплейс проверенных свидетельств.

Запуск: `py -3 -m uvicorn backend.main:app --reload --port 8000` из корня repo.
Все ответы с ошибками — в формате контракта `{error: {code, message}}`.
Пайплайн ML работает без ключа LLM: недоступные сигналы честно помечаются
`unavailable`.
"""

from __future__ import annotations

import asyncio
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

# Модули backend — плоские: работаем и из корня (`backend.main:app`), и из backend/.
_BACKEND_DIR = Path(__file__).resolve().parent
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

from fastapi import BackgroundTasks, FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from starlette.datastructures import UploadFile
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.formparsers import MultiPartException

import store
from errors import (
    ApiError,
    api_error_handler,
    http_error_handler,
    internal_error_handler,
    validation_error_handler,
)
from events import broker, sse_frame, status_event
from ml_bridge import build_context, has_llm, run_check
from paths import (
    CORS_ORIGINS,
    MAX_REQUEST_BYTES,
    MAX_UPLOAD_BYTES,
    MEDIA_DIR,
    demo_listings_path,
)
from pricing import build_listing, iso as iso_dt, parse_dt
from uploads import UploadError, prepare_upload

#: Поля формы, которые допустимо отправлять вместе с файлом.
MAX_FORM_FIELDS = 8
#: Интервал heartbeat в SSE, сек.
SSE_HEARTBEAT = 15.0

MEDIA_DIR.mkdir(parents=True, exist_ok=True)

app = FastAPI(title="Свидетель — маркетплейс свидетельств", version="1.0.0")

app.add_exception_handler(ApiError, api_error_handler)
app.add_exception_handler(StarletteHTTPException, http_error_handler)
app.add_exception_handler(RequestValidationError, validation_error_handler)
app.add_exception_handler(Exception, internal_error_handler)


class RequestTooLarge(Exception):
    """Тело запроса превысило лимит (обрабатывается middleware)."""


class RequestBodyLimitMiddleware:
    """Жёсткий лимит тела запроса: 413 по Content-Length или при чтении.

    Срабатывает до разбора multipart, поэтому гигантский файл не долетает
    до диска. Ответ — в контрактном формате, поэтому свой, а не звездовый
    PlainTextResponse.
    """

    def __init__(self, inner: Any, max_bytes: int) -> None:
        self.inner = inner
        self.max_bytes = max_bytes

    async def __call__(self, scope: dict, receive: Any, send: Any) -> None:
        if scope.get("type") != "http":
            await self.inner(scope, receive, send)
            return

        headers = dict(scope.get("headers") or [])
        raw_length = headers.get(b"content-length")
        if raw_length is not None:
            try:
                too_big = int(raw_length) > self.max_bytes
            except ValueError:
                too_big = True
            if too_big:
                await _send_too_large(send)
                return

        received = 0

        async def limited_receive() -> dict:
            nonlocal received
            message = await receive()
            if message.get("type") == "http.request":
                received += len(message.get("body", b""))
                if received > self.max_bytes:
                    raise RequestTooLarge
            return message

        try:
            await self.inner(scope, limited_receive, send)
        except RequestTooLarge:
            await _send_too_large(send)


def _error_json(code: str, message: str, status: int) -> JSONResponse:
    return JSONResponse(status_code=status, content={"error": {"code": code, "message": message}})


async def _send_too_large(send: Any) -> None:
    body = json.dumps(
        {"error": {"code": "TOO_LARGE", "message": "тело запроса слишком большое"}},
        ensure_ascii=False,
    ).encode("utf-8")
    await send({
        "type": "http.response.start",
        "status": 413,
        "headers": [
            (b"content-type", b"application/json; charset=utf-8"),
            (b"content-length", str(len(body)).encode("ascii")),
        ],
    })
    await send({"type": "http.response.body", "body": body})


app.add_middleware(RequestBodyLimitMiddleware, max_bytes=MAX_REQUEST_BYTES)
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type", "Accept"],
)

# Превью и оригиналы отдаются только из каталога медиа.
app.mount("/media", StaticFiles(directory=str(MEDIA_DIR)), name="media")


# --------------------------------------------------------------------------
# Вспомогательные функции
# --------------------------------------------------------------------------

def _require_text(form: Any, name: str, limit: int) -> str:
    value = form.get(name)
    if value is None:
        return ""
    if isinstance(value, UploadFile):
        raise ApiError("BAD_INPUT", f"поле {name} должно быть текстом", 400)
    text = str(value).strip()
    if len(text) > limit:
        raise ApiError("BAD_INPUT", f"поле {name} длиннее {limit} символов", 400)
    return text


async def _read_form(request: Request) -> Any:
    """Разбор multipart с ограничением числа полей; ошибки — в контрактном виде."""
    try:
        return await request.form(max_files=1, max_fields=MAX_FORM_FIELDS)
    except MultiPartException:
        raise ApiError("BAD_INPUT", "некорректный multipart-запрос", 400)
    except TypeError:
        # Старые версии Starlette не принимают лимиты в form().
        return await request.form()
    except ApiError:
        raise
    except Exception:
        raise ApiError("BAD_INPUT", "не удалось разобрать форму", 400)


def _clean_shot_at(value: str) -> Optional[str]:
    if not value:
        return None
    parsed = parse_dt(value)
    if parsed is None:
        raise ApiError("BAD_INPUT", "shot_at должен быть ISO-датой", 400)
    return iso_dt(parsed)


def _offer_or_404(offer_id: str) -> dict[str, Any]:
    offer = store.get_offer(offer_id)
    if offer is None:
        raise ApiError("NOT_FOUND", f"заявка {offer_id} не найдена", 404)
    return offer


# --------------------------------------------------------------------------
# Фоновая проверка
# --------------------------------------------------------------------------

async def process_offer(
    *,
    offer_id: str,
    check_id: str,
    raw: bytes,
    preview_url: str,
    sha256: str,
    caption: str,
    location: str,
    shot_at: Optional[str],
) -> None:
    """Проверка в фоне: события в SSE, результат в БД, лот — по цене из контракта."""
    broker.publish(offer_id, status_event(
        "status", status="checking", message="Проверка началась",
    ))
    for stage in ("provenance", "artifacts", "sources", "context"):
        broker.publish(offer_id, {
            "kind": "status",
            "event": "stage_started",
            "stage": stage,
            "status": "running",
        })

    ctx = build_context(
        check_id=check_id,
        sha256=sha256,
        preview_url=preview_url,
        data=raw,
        text=caption,
        caption=caption,
        location=location,
        shot_at=shot_at,
    )

    async def on_signal_done(event: Any) -> None:
        broker.publish(offer_id, {
            "kind": "signal",
            "event": "signal_done",
            "signal": event.signal.model_dump(mode="json"),
        })

    try:
        result = await run_check(ctx, on_signal_done=on_signal_done)
        payload = result.model_dump(mode="json")
    except Exception as exc:  # пайплайн не должен ронять API
        store.save_check(offer_id, check_id, None, status="failed",
                         error=f"{type(exc).__name__}")
        store.set_offer_status(offer_id, "rejected")
        broker.publish(offer_id, {
            "kind": "error", "event": "error", "code": "CHECK_FAILED",
            "message": "проверка не удалась",
        })
        return

    payload["offer_id"] = offer_id
    store.save_check(offer_id, check_id, payload, status="done")

    offer = store.get_offer(offer_id) or {}
    plan, reject_reason = build_listing(payload, {
        "caption": offer.get("caption", caption),
        "location": offer.get("location", location),
        "shot_at": offer.get("shot_at", shot_at),
    })

    if plan is None:
        store.set_offer_status(offer_id, "rejected")
        broker.publish(offer_id, {
            "kind": "status", "status": "rejected", "message": reject_reason,
        })
        broker.publish(offer_id, {"kind": "done", "event": "done", "check": payload})
        return

    listing = None
    try:
        listing = store.create_listing(
            offer_id=offer_id,
            check_id=check_id,
            title=plan["title"],
            price_rub=plan["price_rub"],
            trust=plan["trust"],
            facts=plan["facts"],
            why_price=plan["why_price"],
            preview_url=preview_url,
        )
        store.set_offer_status(offer_id, "listed")
    except Exception:
        store.set_offer_status(offer_id, "rejected")
        broker.publish(offer_id, {
            "kind": "error", "event": "error", "code": "INTERNAL",
            "message": "не удалось выставить лот",
        })
        return

    broker.publish(offer_id, {
        "kind": "trust", "event": "status", "trust": plan["trust"],
    })
    broker.publish(offer_id, {
        "kind": "status", "status": "listed",
        "message": f"Материал выставлен за {listing['price_rub']} ₽",
        "listing_id": listing["id"],
    })
    broker.publish(offer_id, {"kind": "done", "event": "done", "check": payload})


# --------------------------------------------------------------------------
# Offer
# --------------------------------------------------------------------------

@app.post("/api/offers", status_code=201)
async def create_offer(request: Request, background: BackgroundTasks) -> dict[str, Any]:
    """Загрузка файла: валидация → Offer → фоновая проверка."""
    form = await _read_form(request)
    upload = form.get("file")
    if upload is None or not isinstance(upload, UploadFile):
        raise ApiError("BAD_INPUT", "нужен файл в поле file", 400)

    caption = _require_text(form, "caption", 1000)
    location = _require_text(form, "location", 200)
    shot_at = _clean_shot_at(_require_text(form, "shot_at", 64))

    try:
        raw = await upload.read()
    except Exception:
        raise ApiError("BAD_INPUT", "не удалось прочитать файл", 400)

    if len(raw) > MAX_UPLOAD_BYTES:
        raise ApiError("TOO_LARGE", "файл больше 15 МБ", 413)

    try:
        prepared = prepare_upload(raw, upload.content_type, upload.filename)
    except UploadError as exc:
        raise ApiError(exc.code, exc.message, exc.status_code)

    offer_id = store.new_id("off")
    check_id = store.new_id("chk")
    offer_dir = MEDIA_DIR / offer_id
    offer_dir.mkdir(parents=True, exist_ok=True)

    # На диск — только свои имена: пользовательское имя остаётся лишь в метаданных.
    original_path = offer_dir / f"original.{prepared.original_ext}"
    preview_path = offer_dir / "preview.jpg"
    original_path.write_bytes(prepared.data)
    preview_path.write_bytes(prepared.preview_jpeg)
    preview_url = f"/media/{offer_id}/preview.jpg"

    offer = store.create_offer(
        offer_id=offer_id,
        file_name=prepared.safe_name,
        file_size=len(prepared.data),
        file_mime=prepared.mime,
        sha256=prepared.sha256,
        preview_url=preview_url,
        caption=caption,
        location=location,
        shot_at=shot_at,
    )

    background.add_task(
        process_offer,
        offer_id=offer_id,
        check_id=check_id,
        raw=prepared.data,
        preview_url=preview_url,
        sha256=prepared.sha256,
        caption=caption,
        location=location,
        shot_at=shot_at,
    )
    return offer


@app.get("/api/offers/{offer_id}")
async def get_offer(offer_id: str) -> dict[str, Any]:
    return _offer_or_404(offer_id)


@app.get("/api/offers/{offer_id}/check")
async def get_offer_check(offer_id: str) -> dict[str, Any]:
    _offer_or_404(offer_id)
    row = store.get_check_row(offer_id)
    if row is None:
        raise ApiError("CHECK_FAILED", "проверка ещё не начиналась", 409)
    if row["status"] != "done" or row["result"] is None:
        raise ApiError(
            "CHECK_FAILED",
            f"проверка не завершена (статус {row['status']})",
            409,
        )
    return row["result"]


@app.get("/api/offers/{offer_id}/events")
async def offer_events(offer_id: str) -> StreamingResponse:
    """SSE прогресса проверки.

    Подписчик получает историю событий из буфера брокера и новые события из
    своей очереди; поток закрывается на `done`/`error`.
    """
    _offer_or_404(offer_id)
    queue = broker.subscribe(offer_id)

    async def stream():
        try:
            while True:
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=SSE_HEARTBEAT)
                except asyncio.TimeoutError:
                    if broker.is_finished(offer_id):
                        break
                    yield ": heartbeat\n\n"
                    continue
                name = str(event.get("event") or "status")
                yield sse_frame(name, event)
                if event.get("kind") in ("done", "error"):
                    break
        finally:
            broker.unsubscribe(offer_id, queue)

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# --------------------------------------------------------------------------
# Listings
# --------------------------------------------------------------------------

LISTING_STATES = {"available", "reserved", "sold"}


@app.get("/api/listings")
async def list_listings(
    state: Optional[str] = None,
    min_price: Optional[int] = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    if state is not None and state not in LISTING_STATES:
        raise ApiError("BAD_INPUT", "state: available, reserved или sold", 400)
    if min_price is not None and min_price < 0:
        raise ApiError("BAD_INPUT", "min_price не может быть отрицательным", 400)
    if limit < 1:
        raise ApiError("BAD_INPUT", "limit должен быть больше нуля", 400)
    return store.list_listings(state=state, min_price=min_price, limit=limit)


@app.get("/api/listings/{listing_id}")
async def get_listing(listing_id: str) -> dict[str, Any]:
    listing = store.get_listing(listing_id)
    if listing is None:
        raise ApiError("NOT_FOUND", f"лот {listing_id} не найден", 404)
    return listing


@app.post("/api/listings/{listing_id}/buy")
async def buy_listing(listing_id: str, request: Request) -> dict[str, Any]:
    """Сделка: комиссия 20 %, повторная покупка — 409."""
    buyer_id, buyer_name = "org_mash", "Mash"
    try:
        body = await request.json()
    except Exception:
        body = None
    if isinstance(body, dict):
        buyer_id = str(body.get("buyer_id") or buyer_id)[:64]
        buyer_name = str(body.get("buyer_name") or buyer_name)[:100]

    try:
        deal = store.buy_listing(listing_id, buyer_id=buyer_id, buyer_name=buyer_name)
    except store.NotFound:
        raise ApiError("NOT_FOUND", f"лот {listing_id} не найден", 404)
    except store.AlreadySold:
        raise ApiError("ALREADY_SOLD", "лот уже продан", 409)
    return {"deal_id": deal["id"], "status": deal["status"], **deal}


@app.get("/api/deals")
async def get_deals() -> list[dict[str, Any]]:
    return store.list_deals()


@app.get("/api/stats")
async def get_stats() -> dict[str, int]:
    return store.stats()


@app.get("/api/market/demo")
async def market_demo() -> dict[str, Any]:
    """Предзаполненные лоты из ml/data/demo_listings.json. Нет файла — пустой список."""
    path = demo_listings_path()
    if not path.is_file():
        return {"items": [], "source": "none"}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        raise ApiError("INTERNAL", "демо-данные не читаются", 500)
    if isinstance(payload, dict):
        items = payload.get("items") or payload.get("listings") or []
    elif isinstance(payload, list):
        items = payload
    else:
        items = []
    return {"items": [item for item in items if isinstance(item, dict)], "source": str(path.name)}


@app.get("/api/health")
async def health() -> dict[str, Any]:
    """Статус сервиса и наличие LLM (не секрет — только флаг)."""
    return {"status": "ok", "llm": has_llm(), "time": datetime.now(timezone.utc).isoformat()}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("backend.main:app", host="127.0.0.1", port=8000, reload=True)