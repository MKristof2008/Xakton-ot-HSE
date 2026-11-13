# Контракт «Свидетель» — заморожен

Единственный источник истины для обмена между ML, backend и frontend.
Меняется только с согласия всех четырёх зон.

## Три сущности

```
Заявка (Offer)  →  Проверка (Check)  →  Лот (Listing)  →  Сделка (Deal)
что снял автор     подлинно? сколько   что продаём         кто купил
                   стоит?
```

## 1. Offer — что загрузил автор

`POST /api/offers` (multipart: `file`, поля `caption`, `location`, `shot_at`)

```json
{
  "id": "off_7f3a91",
  "status": "checking | listed | rejected | sold",
  "created_at": "2026-11-13T16:40:00Z",
  "author": { "id": "usr_12ab", "display_name": "Аноним", "payout": 0 },
  "file": {
    "name": "photo.jpg",
    "size": 1843200,
    "mime": "image/jpeg",
    "sha256": "…",
    "preview_url": "/media/off_7f3a91/preview.jpg"
  },
  "caption": "Дым над заводом, Люберцы",
  "location": "Люберцы",
  "shot_at": "2026-11-13T15:12:00Z"
}
```

## 2. Check — результат проверки

Ровно `contracts/check_result.schema.json` (уже существует, не меняем поля).
Расширяем только `details` внутри сигналов — они свободные.

Дополнительно backend добавляет к ответу `offer_id` — связка заявки и проверки.

## 3. Listing — лот на продажу

```json
{
  "id": "lst_2c81",
  "offer_id": "off_7f3a91",
  "check_id": "chk_9d02",
  "title": "Дым над заводом, Люберцы — фото с места",
  "price_rub": 4200,
  "currency": "RUB",
  "state": "available | reserved | sold",
  "created_at": "2026-11-13T16:41:10Z",
  "expires_at": "2026-11-20T16:41:10Z",
  "trust": { "score": 84, "uncertainty": 0.12, "coverage": 0.9, "level": "confirmed" },
  "facts": {
    "origin": "снято на камеру",
    "shot_at": "2026-11-13T15:12:00Z",
    "geo": "Люберцы, Московская область",
    "unique": true,
    "similar_in_archive": 0
  },
  "why_price": [
    "Свежесть: снято 1.5 часа назад",
    "Уникальность: нет совпадений в архиве",
    "Метаданные целы, геолокация совпадает с подписью"
  ],
  "preview_url": "/media/off_7f3a91/preview.jpg"
}
```

### Правило цены (детерминированное, объяснимое)

`price_rub = base × freshness × uniqueness × provenance × demand`, округление до 100.

| Множитель | Значение |
|---|---|
| base | 1500 ₽ |
| freshness | <1 ч ×3.0 · <6 ч ×2.0 · <24 ч ×1.5 · <72 ч ×1.0 · иначе ×0.5 |
| uniqueness | нет совпадений ×2.0 · есть похожие ×1.0 · дубликат ×0 (не выставляется) |
| provenance | метаданные целы и гео совпадает ×1.5 · частично ×1.0 · нет данных ×0.7 |
| demand | по категории события: ЧП/происшествие ×1.8 · городское ×1.2 · остальное ×1.0 |

Множители и итог обязаны попадать в `why_price` человеческим языком.
Никакого «AI решил» — каждая цифра объясняется.

## 4. Deal — покупка

`POST /api/listings/{id}/buy` → `{ "deal_id": "deal_55e1", "status": "paid" }`

```json
{
  "id": "deal_55e1",
  "listing_id": "lst_2c81",
  "buyer": { "id": "org_mash", "name": "Mash" },
  "amount_rub": 4200,
  "commission_rub": 840,
  "author_payout_rub": 3360,
  "status": "paid | delivered | refunded",
  "created_at": "2026-11-13T16:44:00Z"
}
```

Комиссия платформы — 20 %. Это и есть модель дохода: NMH не платит авторам из
своего кармана, а берёт процент с оборота.

## Эндпоинты (backend)

| Метод | Путь | Что делает |
|---|---|---|
| POST | `/api/offers` | загрузить файл → создаёт Offer, запускает проверку |
| GET | `/api/offers/{id}` | заявка + статус |
| GET | `/api/offers/{id}/check` | результат проверки (контракт CheckResult) |
| GET | `/api/offers/{id}/events` | SSE прогресс сигналов |
| GET | `/api/listings` | лента лотов, фильтры `?state=&min_price=` |
| GET | `/api/listings/{id}` | лот целиком |
| POST | `/api/listings/{id}/buy` | сделка |
| GET | `/api/deals` | сделки (для экрана редакции) |
| GET | `/api/stats` | сводка: заявок, лотов, оборот, комиссия |
| GET | `/api/market/demo` | предзаполненные лоты для демо |

## Ошибки

Единый вид: `{ "error": { "code": "…", "message": "…" } }`, HTTP 4xx/5xx.

Коды: `BAD_INPUT`, `TOO_LARGE`, `UNSUPPORTED_TYPE`, `NOT_FOUND`,
`ALREADY_SOLD`, `CHECK_FAILED`, `INTERNAL`.

## Статусы и переходы

```
Offer:   checking ──► listed ──► sold
              └────► rejected
Listing: available ──► reserved ──► sold
                 └──► expired (по expires_at)
Deal:    paid ──► delivered
            └──► refunded
```
