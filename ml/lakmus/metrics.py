"""Метрики качества «настоящее / подделка» (раздел 6.7 ТЗ).

Только stdlib: numpy и sklearn в проекте нет и не должно появляться
(``ml/requirements.txt`` — pydantic + pytest). Поэтому AUC считается через
ранги Манна–Уитни, а калибровка — через ручную раскладку по бинам.

Соглашения
----------
* ``scores01`` — вероятность класса «настоящее», 0..1 (значения вне
  диапазона подрезаются);
* ``labels`` — 1 для настоящего, 0 для подделки
  (см. :func:`lakmus.dataset.to_binary_label`);
* бинарное решение принимается по порогу :data:`DECISION_THRESHOLD`;
* все публичные функции возвращают числа, округлённые до 4 знаков.
  Документ «Методология» и UI показывают те же 4 знака.

«Туман» (``fog``) — уровень, который система ставит, когда неопределённость
слияния выше ``fog_threshold`` (по умолчанию 0.40 из
``lakmus.fusion.FUSION_CONFIG``). Метрики ниже считают «Туман» отказом от
ответа: он выпадает из selective accuracy и входит в риск–покрытие как
самая неопределённая часть набора.
"""

from __future__ import annotations

from typing import Any, Mapping, Sequence

from .fusion import FUSION_CONFIG

#: Порог бинарного решения: score >= 0.5 → «настоящее».
DECISION_THRESHOLD: float = 0.5

#: Порог Тумана берём из единственного источника истины — конфига слияния.
FOG_THRESHOLD: float = float(FUSION_CONFIG["fog_threshold"])

#: Категории ТЗ 6.7, которые по определению неоднозначны.
AMBIGUOUS_TAGS: frozenset[str] = frozenset({"edited", "mislabelled"})

#: Метки, которые в бинарной задаче считаются «настоящим».
POSITIVE_LABELS: frozenset[str] = frozenset({"real", "1", "true", "настоящее"})


def _round(value: float) -> float:
    return round(float(value), 4)


def _clamp01(value: float) -> float:
    if value < 0.0:
        return 0.0
    if value > 1.0:
        return 1.0
    return float(value)


def _same_length(**sequences: Sequence[Any]) -> int:
    lengths = {name: len(seq) for name, seq in sequences.items()}
    if len(set(lengths.values())) > 1:
        raise ValueError(f"Разная длина рядов: {lengths}")
    return next(iter(lengths.values()))


def to_binary(label: Any) -> int:
    """Приводит метку к 0/1: 1 — настоящее, 0 — всё остальное.

    Понимает числа (0/1), bool и строки разметки ТЗ
    (``real`` / ``fake`` / ``edited`` / ``mislabelled``).
    """
    if isinstance(label, bool):
        return 1 if label else 0
    if isinstance(label, (int, float)):
        return 1 if float(label) >= 0.5 else 0
    text = str(label).strip().lower()
    if text in POSITIVE_LABELS:
        return 1
    if text in {"0", "false", "fake", "edited", "mislabelled", "подделка"}:
        return 0
    raise ValueError(f"Неизвестная метка: {label!r}")


def normalize_score(value: Any) -> float:
    """Приводит score к 0..1.

    В контракте ``trust.score`` — целое 0..100, в метриках удобнее 0..1.
    Поэтому значения > 1 трактуются как проценты и делятся на 100.
    """
    number = float(value)
    if number > 1.0:
        number = number / 100.0
    return _clamp01(number)


def auc(scores: Sequence[float], labels: Sequence[int]) -> float:
    """ROC-AUC через статистику Манна–Уитни (без numpy).

    ::

        AUC = (1 / (n_pos * n_neg)) * sum_{i: y=1, j: y=0} [s_i > s_j]
              + 0.5 * [s_i == s_j]

    То есть вероятность, что случайный «настоящий» объект получил score
    выше случайного «поддельного», ничьи считаются за половину.

    Границы:

    * все оценки «настоящих» выше — ``1.0``, наоборот — ``0.0``;
    * константные scores (все пары — ничьи) дают ровно ``0.5``;
    * если в выборке только один класс, метрика не определена — ``0.5``.
    """
    values = [float(s) for s in scores]
    target = [int(y) for y in labels]
    n = _same_length(scores=values, labels=target)
    positives = sum(1 for y in target if y == 1)
    negatives = n - positives
    if positives == 0 or negatives == 0:
        return 0.5

    order = sorted(range(n), key=lambda i: values[i])
    ranks = [0.0] * n
    i = 0
    while i < n:
        j = i
        while j + 1 < n and values[order[j + 1]] == values[order[i]]:
            j += 1
        midrank = (i + j) / 2.0 + 1.0  # ранги 1-based, ничьи — средний ранг
        for k in range(i, j + 1):
            ranks[order[k]] = midrank
        i = j + 1

    rank_sum = sum(ranks[i] for i in range(n) if target[i] == 1)
    u_stat = rank_sum - positives * (positives + 1) / 2.0
    return _round(u_stat / (positives * negatives))


def brier(scores01: Sequence[float], labels: Sequence[int]) -> float:
    """Brier score: среднеквадратичная ошибка вероятности.

    ::

        Brier = (1 / N) * sum_i (p_i - y_i)^2

    ``0.0`` — идеальные вероятности, ``1.0`` — максимально уверенные и
    максимально неверные. Метрика «правильная» (proper scoring rule):
    её нельзя улучшить, выдавая завышенные вероятности.
    """
    scores = [_clamp01(float(s)) for s in scores01]
    target = [int(y) for y in labels]
    n = _same_length(scores01=scores, labels=target)
    if n == 0:
        return 0.0
    total = sum((p - y) ** 2 for p, y in zip(scores, target))
    return _round(total / n)


def _bin_index(score: float, bins: int) -> int:
    index = int(score * bins)
    return min(max(index, 0), bins - 1)


def reliability_table(
    scores01: Sequence[float], labels: Sequence[int], bins: int = 10
) -> list[dict]:
    """Таблица надёжности по равным бинам ширины ``1 / bins``.

    Для каждого непустого бина ``k`` (интервал ``[k/bins, (k+1)/bins)``,
    последний бин включает 1.0):

    * ``confidence`` — средняя предсказанная вероятность в бине;
    * ``accuracy`` — доля настоящих объектов в бине;
    * ``gap`` — ``|accuracy - confidence|``;
    * ``count`` — сколько объектов попало.

    ECE — среднее ``gap`` с весом ``count / N``: бины с большим числом
    объектов важнее. Идеальная калибровка: accuracy == confidence.
    """
    scores = [_clamp01(float(s)) for s in scores01]
    target = [int(y) for y in labels]
    n = _same_length(scores01=scores, labels=target)
    if bins <= 0:
        raise ValueError("bins должен быть положительным")
    if n == 0:
        return []

    buckets: list[list[tuple[float, int]]] = [[] for _ in range(bins)]
    for p, y in zip(scores, target):
        buckets[_bin_index(p, bins)].append((p, y))

    table: list[dict] = []
    for index, items in enumerate(buckets):
        if not items:
            continue
        confidence = sum(p for p, _ in items) / len(items)
        accuracy = sum(y for _, y in items) / len(items)
        table.append(
            {
                "bin": index,
                "low": _round(index / bins),
                "high": _round((index + 1) / bins),
                "count": len(items),
                "confidence": _round(confidence),
                "accuracy": _round(accuracy),
                "gap": _round(abs(accuracy - confidence)),
            }
        )
    return table


def ece(scores01: Sequence[float], labels: Sequence[int], bins: int = 10) -> float:
    """Expected Calibration Error (равные по ширине бины).

    ::

        ECE = sum_k (n_k / N) * |accuracy_k - confidence_k|

    ``<= 0.10`` — хорошая калибровка для такого набора, ``> 0.20`` —
    вероятностям нельзя верить как числам (их можно читать только как
    порядок «более/менее вероятно»).
    """
    scores = [_clamp01(float(s)) for s in scores01]
    target = [int(y) for y in labels]
    n = _same_length(scores01=scores, labels=target)
    if n == 0:
        return 0.0
    table = reliability_table(scores, target, bins=bins)
    total = sum(row["count"] * row["gap"] for row in table)
    return _round(total / n)


def _correct(score: float, label: int) -> bool:
    predicted = 1 if score >= DECISION_THRESHOLD else 0
    return predicted == label


def selective_accuracy(
    scores01: Sequence[float],
    labels: Sequence[int],
    uncertainty: Sequence[float],
    fog_threshold: float = FOG_THRESHOLD,
) -> tuple[float, float]:
    """Точность на всём, что система не отправила в «Туман».

    ::

        coverage = |{i: u_i <= fog_threshold}| / N
        accuracy = |{i: u_i <= fog_threshold и решение верно}| / |...|

    Возвращает ``(accuracy, coverage)``. Если всё ушло в «Туман» —
    ``(0.0, 0.0)``: отвечать было нечем, точность не определена.
    Это главная пара чисел проекта: «насколько можно доверять тому,
    что система вообще решила ответить».
    """
    scores = [_clamp01(float(s)) for s in scores01]
    target = [int(y) for y in labels]
    unc = [float(u) for u in uncertainty]
    n = _same_length(scores01=scores, labels=target, uncertainty=unc)
    if n == 0:
        return 0.0, 0.0
    kept = [i for i in range(n) if unc[i] <= fog_threshold]
    if not kept:
        return 0.0, 0.0
    correct = sum(1 for i in kept if _correct(scores[i], target[i]))
    return _round(correct / len(kept)), _round(len(kept) / n)


def risk_coverage_curve(
    scores01: Sequence[float],
    labels: Sequence[int],
    uncertainties: Sequence[float],
    steps: int = 10,
) -> list[dict]:
    """Кривая «риск–покрытие»: что будет, если отвечать только на уверенное.

    Объекты сортируются по неопределённости по возрастанию (сначала самые
    уверенные), затем берётся префикс длины ``k`` для
    ``k = round(N * j / steps), j = 1..steps``:

    * ``coverage = k / N`` — доля набора, на которую система ответила;
    * ``accuracy`` — точность на этом префиксе;
    * ``risk = 1 - accuracy`` — цена ошибки на отвеченной части;
    * ``uncertainty_threshold`` — ``u`` последнего взятого объекта,
      то есть порог отсечения Тумана для этой точки.

    Покрытие строго не убывает вдоль списка (префиксы вложены), дубли
    ``k`` (когда ``N < steps``) убраны. Идеальная система: риск растёт
    вместе с покрытием, потому что в ответ добавляются всё более спорные
    случаи.
    """
    scores = [_clamp01(float(s)) for s in scores01]
    target = [int(y) for y in labels]
    unc = [float(u) for u in uncertainties]
    n = _same_length(scores01=scores, labels=target, uncertainties=unc)
    if n == 0 or steps <= 0:
        return []

    order = sorted(range(n), key=lambda i: (unc[i], i))
    sizes = sorted({min(n, max(1, round(n * j / steps))) for j in range(1, steps + 1)})

    curve: list[dict] = []
    for k in sizes:
        kept = order[:k]
        correct = sum(1 for i in kept if _correct(scores[i], target[i]))
        accuracy = correct / k
        curve.append(
            {
                "coverage": _round(k / n),
                "accuracy": _round(accuracy),
                "risk": _round(1.0 - accuracy),
                "uncertainty_threshold": _round(unc[order[k - 1]]),
                "count": k,
            }
        )
    return curve


def _field(record: Any, key: str, default: Any = None) -> Any:
    if isinstance(record, Mapping):
        return record.get(key, default)
    return getattr(record, key, default)


def summarize_benchmark(records: Sequence[Any]) -> dict:
    """Сводка по прогону на размеченном наборе.

    ``records`` — строки результатов: словари или объекты с полями
    ``label`` (1/0 или ``real``/``fake``/…), ``score`` (0..1 или 0..100),
    ``uncertainty`` (0..1), необязательными ``level`` и ``category``.

    Возвращает словарь (числа округлены до 4 знаков):

    * ``n``, ``positives``, ``negatives`` — размер и баланс выборки;
    * ``auc`` — разделяющая способность score;
    * ``brier`` — качество вероятностей;
    * ``ece`` — калибровка (10 бинов);
    * ``selective_accuracy`` и ``coverage`` — точность/доля ответов
      вне Тумана;
    * ``fog_share`` — доля Тумана на всём наборе;
    * ``fog_share_ambiguous`` — доля Тумана на неоднозначных объектах
      (``edited`` и ``mislabelled``): там «Туман» — правильный ответ,
      и высокая доля означает, что система честно молчит, а не гадает.
    """
    scores: list[float] = []
    labels: list[int] = []
    uncertainties: list[float] = []
    levels: list[str] = []
    ambiguous: list[bool] = []

    for record in records:
        score = normalize_score(_field(record, "score", 0.5))
        label = to_binary(_field(record, "label"))
        uncertainty = _clamp01(float(_field(record, "uncertainty", 1.0)))
        level = str(_field(record, "level", "") or "").strip().lower()
        category = str(_field(record, "category", "") or "").strip().lower()
        raw_label = str(_field(record, "label", "")).strip().lower()

        scores.append(score)
        labels.append(label)
        uncertainties.append(uncertainty)
        levels.append(level)
        ambiguous.append(category in AMBIGUOUS_TAGS or raw_label in AMBIGUOUS_TAGS)

    n = len(scores)
    positives = sum(labels)
    selective, coverage = selective_accuracy(scores, labels, uncertainties)
    fog_flags = [
        levels[i] == "fog" or uncertainties[i] > FOG_THRESHOLD for i in range(n)
    ]
    fog_total = sum(fog_flags)
    ambiguous_idx = [i for i in range(n) if ambiguous[i]]
    fog_ambiguous = sum(1 for i in ambiguous_idx if fog_flags[i])

    return {
        "n": n,
        "positives": positives,
        "negatives": n - positives,
        "auc": auc(scores, labels),
        "brier": brier(scores, labels),
        "ece": ece(scores, labels),
        "selective_accuracy": selective,
        "coverage": coverage,
        "fog_share": _round(fog_total / n) if n else 0.0,
        "fog_share_ambiguous": (
            _round(fog_ambiguous / len(ambiguous_idx)) if ambiguous_idx else 0.0
        ),
        "fog_threshold": FOG_THRESHOLD,
    }
