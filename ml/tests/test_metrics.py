"""Тесты ML-части: метрики 6.7, набор с разметкой, demo-режим, контракт.

Запуск: ``.venv/Scripts/python.exe -m pytest ml -q`` из корня репозитория.
Пути к данным строятся от каталога ``ml/``, а не от текущего каталога
процесса, поэтому тесты не зависят от места запуска.
"""
import json
from pathlib import Path

import pytest

from lakmus.dataset import (
    DATASET_MINIMUMS,
    MIN_TOTAL,
    LabeledCase,
    dataset_stats,
    load_dataset,
    to_binary_label,
    validate_dataset,
)
from lakmus.demo import (
    MAX_DELAY_MS,
    MIN_DELAY_MS,
    list_demo,
    load_demo,
    replay_delays,
    save_demo,
)
from lakmus.metrics import (
    DECISION_THRESHOLD,
    auc,
    brier,
    ece,
    normalize_score,
    reliability_table,
    risk_coverage_curve,
    selective_accuracy,
    summarize_benchmark,
    to_binary,
)
from lakmus.schemas import CheckResult

ML_ROOT = Path(__file__).resolve().parents[1]
DATA = ML_ROOT / "data"
DEMO_DIR = DATA / "demo"
LABELS_PATH = DATA / "labels_example.jsonl"
RESULTS_PATH = DATA / "results_example.jsonl"


def demo_result(name: str) -> CheckResult:
    """Читает демо-файл как валидный контракт."""
    return CheckResult.model_validate_json(
        (DEMO_DIR / f"{name}.json").read_text(encoding="utf-8")
    )


def calibrated_sample() -> tuple[list[float], list[int]]:
    """Три группы с точным попаданием accuracy в confidence: ECE = 0."""
    scores = [0.2] * 20 + [0.6] * 20 + [0.85] * 20
    labels = [1] * 4 + [0] * 16 + [1] * 12 + [0] * 8 + [1] * 17 + [0] * 3
    return scores, labels


def synthetic_cases(total_per_category: dict[str, int] | None = None) -> list[LabeledCase]:
    """Полный набор по минимумам ТЗ 6.7 (210 объектов)."""
    counts = total_per_category or DATASET_MINIMUMS
    labels = {
        "real_photo": "real",
        "generated": "fake",
        "edited": "edited",
        "mislabelled": "mislabelled",
    }
    cases: list[LabeledCase] = []
    for category, count in counts.items():
        for index in range(count):
            case_id = f"{category}_{index:03d}"
            cases.append(
                LabeledCase(
                    id=case_id,
                    path=f"data/samples/{category}/{case_id}.jpg",
                    kind="text" if category == "text" else "image",
                    category=category,
                    label=labels.get(category, "real"),
                )
            )
    return cases


# --- метрики: AUC --------------------------------------------------------


def test_auc_ideal_and_inverted_ranking():
    """Все настоящие выше всех поддельных — 1.0, наоборот — 0.0."""
    labels = [1, 1, 0, 0]
    assert auc([0.9, 0.8, 0.3, 0.1], labels) == 1.0
    assert auc([0.1, 0.2, 0.7, 0.9], labels) == 0.0


def test_auc_ties_and_constant_scores():
    """Ничьи считаются за половину, константа даёт ровно 0.5."""
    labels = [1, 1, 0, 0]
    assert auc([0.5, 0.5, 0.5, 0.5], labels) == 0.5
    # одна пара из четырёх выиграна, две ничьи, одна проиграна:
    # (1 + 0.5 + 0.5 + 0) / 4 = 0.5
    assert auc([0.4, 0.6, 0.4, 0.6], labels) == 0.5


def test_auc_single_class_is_undefined_half():
    """Один класс в выборке — метрика не определена, отдаём 0.5."""
    assert auc([0.2, 0.4], [1, 1]) == 0.5
    assert auc([0.2, 0.4], [0, 0]) == 0.5


def test_auc_rejects_length_mismatch():
    with pytest.raises(ValueError):
        auc([0.1, 0.2, 0.3], [1, 0])


# --- метрики: Brier и калибровка ----------------------------------------


def test_brier_extremes():
    """Идеальные вероятности — 0.0, максимально уверенные и неверные — 1.0."""
    assert brier([1.0, 0.0, 1.0, 0.0], [1, 0, 1, 0]) == 0.0
    assert brier([0.0, 1.0, 0.0, 1.0], [1, 0, 1, 0]) == 1.0


def test_brier_middle_is_quarter():
    """Уверенно 0.5 на любом ответе — штраф 0.25 на объект."""
    assert brier([0.5, 0.5], [0, 1]) == 0.25


def test_ece_small_on_calibrated_scores():
    scores, labels = calibrated_sample()
    assert ece(scores, labels) <= 0.10


def test_ece_large_on_biased_scores():
    """Все ответы «0.9 настоящее», а верно лишь в половине случаев."""
    scores = [0.9] * 20
    labels = [1] * 10 + [0] * 10
    assert ece(scores, labels) > 0.20


def test_reliability_table_counts_and_gaps():
    scores, labels = calibrated_sample()
    table = reliability_table(scores, labels, bins=10)
    assert [row["bin"] for row in table] == [2, 6, 8]
    assert [row["count"] for row in table] == [20, 20, 20]
    for row in table:
        assert row["gap"] <= 0.01
    weighted = sum(row["count"] * row["gap"] for row in table) / len(scores)
    assert round(weighted, 4) == ece(scores, labels)


# --- метрики: отказ от ответа -------------------------------------------


def test_selective_accuracy_skips_fog():
    """«Туман» не попадает в точность, но уменьшает покрытие."""
    scores = [0.9, 0.8, 0.2, 0.1]
    labels = [0, 0, 1, 0]
    uncertainty = [0.1, 0.2, 0.9, 0.95]
    accuracy, coverage = selective_accuracy(scores, labels, uncertainty, fog_threshold=0.4)
    # остались первые два объекта, оба отвечены неверно
    assert accuracy == 0.0
    assert coverage == 0.5


def test_selective_accuracy_all_fog():
    """Если ответить нечем, точность не определена — нули, а не 1.0."""
    assert selective_accuracy([0.9], [1], [1.0], fog_threshold=0.4) == (0.0, 0.0)


def test_risk_coverage_curve_is_monotone():
    """Покрытие растёт, риск не убывает: спорные случаи добавляются позже."""
    # первые пять объектов размечены «настоящее», последние пять — «подделка»,
    # но score у всех высокий: ошибки начинаются там, где выше неопределённость
    scores = [0.9] * 10
    labels = [1] * 5 + [0] * 5
    uncertainty = [0.05, 0.06, 0.07, 0.08, 0.09, 0.50, 0.51, 0.52, 0.53, 0.54]
    curve = risk_coverage_curve(scores, labels, uncertainty, steps=10)

    assert len(curve) == 10
    coverages = [row["coverage"] for row in curve]
    risks = [row["risk"] for row in curve]
    thresholds = [row["uncertainty_threshold"] for row in curve]
    assert coverages == sorted(coverages)
    assert coverages[0] == 0.1
    assert coverages[-1] == 1.0
    assert risks == sorted(risks)
    assert thresholds == sorted(thresholds)
    # на самом уверенном префиксе ошибок нет, к концу набора риск максимален
    assert curve[0]["risk"] == 0.0
    assert curve[-1]["risk"] == 0.5


def test_risk_coverage_drops_duplicate_sizes():
    """Когда объектов меньше шагов, дубли покрытия убираются."""
    curve = risk_coverage_curve([0.9, 0.1], [1, 0], [0.1, 0.2], steps=10)
    assert [row["coverage"] for row in curve] == [0.5, 1.0]


# --- приведение меток и score -------------------------------------------


def test_to_binary_understands_tz_labels():
    assert to_binary("real") == 1
    assert to_binary(True) == 1
    assert to_binary(1) == 1
    for label in ("fake", "edited", "mislabelled", 0, False):
        assert to_binary(label) == 0
    with pytest.raises(ValueError):
        to_binary("неизвестно")


def test_normalize_score_converts_percent():
    assert normalize_score(84) == 0.84
    assert normalize_score(0.3253) == 0.3253
    assert normalize_score(-1) == 0.0
    assert normalize_score(250) == 1.0


def test_decision_threshold_is_half():
    assert DECISION_THRESHOLD == 0.5


# --- сводка по прогону ---------------------------------------------------


def test_summarize_benchmark_keys_and_counts():
    records = [json.loads(line) for line in RESULTS_PATH.read_text(encoding="utf-8").splitlines() if line.strip()]
    summary = summarize_benchmark(records)

    assert summary["n"] == 8
    assert summary["positives"] == 3
    assert summary["negatives"] == 5
    for key in (
        "auc",
        "brier",
        "ece",
        "selective_accuracy",
        "coverage",
        "fog_share",
        "fog_share_ambiguous",
        "fog_threshold",
    ):
        assert key in summary
    assert 0.0 <= summary["auc"] <= 1.0
    assert 0.0 <= summary["brier"] <= 1.0
    assert 0.0 <= summary["coverage"] <= 1.0
    # два неоднозначных объекта (edited, mislabelled) оба в Тумане
    assert summary["fog_share_ambiguous"] == 1.0


# --- набор с разметкой ---------------------------------------------------


def test_example_dataset_is_below_tz_minimums():
    cases = load_dataset(LABELS_PATH)
    report = validate_dataset(cases)

    assert report["total"] == 14
    assert report["by_category"] == {
        "real_photo": 3,
        "generated": 3,
        "edited": 2,
        "mislabelled": 2,
        "text": 4,
    }
    assert report["ok"] is False
    assert report["duplicate_ids"] == []
    assert report["warnings"]
    assert set(report["below_minimum"]) == set(DATASET_MINIMUMS)
    assert report["missing_categories"] == []


def test_example_dataset_stats_and_binary_labels():
    stats = dataset_stats(load_dataset(LABELS_PATH))
    assert stats["total"] == 14
    assert stats["images"] == 10
    assert stats["texts"] == 4
    assert stats["ambiguous"] == 4
    assert stats["unique_paths"] == 14
    assert dataset_stats([])["ambiguous_share"] == 0.0

    assert to_binary_label("real") == 1
    for label in ("fake", "edited", "mislabelled"):
        assert to_binary_label(label) == 0
    with pytest.raises(ValueError):
        to_binary_label("unknown")


def test_full_synthetic_dataset_passes():
    """Набор ровно по минимумам ТЗ проходит сверку без предупреждений."""
    report = validate_dataset(synthetic_cases())
    assert report["total"] == sum(DATASET_MINIMUMS.values()) == 210
    assert report["total"] >= MIN_TOTAL
    assert report["ok"] is True
    assert report["warnings"] == []
    assert report["below_minimum"] == {}


def test_duplicate_ids_break_the_verdict():
    cases = synthetic_cases()
    cases.append(cases[0].model_copy())
    report = validate_dataset(cases)
    assert report["ok"] is False
    assert report["duplicate_ids"] == [cases[0].id]
    assert any("повторяющиеся id" in text for text in report["warnings"])


def test_mismatched_label_is_a_warning():
    broken = LabeledCase(
        id="gen_001",
        path="data/samples/generated/gen_001.jpg",
        kind="image",
        category="generated",
        label="real",
    )
    report = validate_dataset([broken])
    assert any("ожидалась метка fake" in text for text in report["warnings"])


def test_load_dataset_skips_comments_and_reports_bad_line(tmp_path):
    manifest = tmp_path / "labels.jsonl"
    manifest.write_text(
        "# комментарий\n"
        "\n"
        '{"id": "a", "path": "data/samples/a.jpg", "kind": "image", '
        '"category": "real_photo", "label": "real"}\n',
        encoding="utf-8",
    )
    assert [case.id for case in load_dataset(manifest)] == ["a"]

    manifest.write_text('{"id": "a"}\n', encoding="utf-8")
    with pytest.raises(ValueError) as error:
        load_dataset(manifest)
    assert ":1:" in str(error.value)

    manifest.write_text("{не json}\n", encoding="utf-8")
    with pytest.raises(ValueError) as error:
        load_dataset(manifest)
    assert ":1: невалидный JSON" in str(error.value)

    with pytest.raises(FileNotFoundError):
        load_dataset(tmp_path / "нет.jsonl")


# --- demo-режим ----------------------------------------------------------


@pytest.mark.parametrize("name", ["demo_image_001", "demo_text_001"])
def test_demo_files_match_contract(name):
    result = demo_result(name)
    result.validate_contract()

    assert result.id == name
    assert len(result.signals) == 11
    signal_ids = {signal.id for signal in result.signals}
    assert {"I1", "I2", "I3", "I4", "I5", "I6", "T1", "T2", "T3", "T4", "T5"} == signal_ids

    theses = result.debate.for_real + result.debate.for_fake
    assert theses
    for thesis in theses:
        assert thesis.text
        assert set(thesis.signal_ids) <= signal_ids

    assert 0 <= result.trust.score <= 100
    assert 0.0 <= result.trust.uncertainty <= 1.0


def test_demo_text_is_fog_with_conflict():
    """Текст с ссылкой на «подтверждение» уходит в Туман из-за конфликта.

    Конфликт сам по себе делает уровень ``fog`` (``lakmus.fusion.level_for``),
    даже когда неопределённость ниже порога: система не должна выбирать
    сторону, когда сигналы спорят.
    """
    result = demo_result("demo_text_001")
    assert result.trust.conflict is True
    assert result.trust.level.value == "fog"
    assert result.trust.uncertainty < 0.40


def test_demo_image_is_not_fog():
    result = demo_result("demo_image_001")
    assert result.trust.conflict is False
    assert result.trust.level.value == "likely_real"
    assert result.trust.uncertainty <= 0.40


def test_demo_roundtrip(tmp_path):
    original = demo_result("demo_image_001")
    path = save_demo(original, tmp_path)

    assert path == tmp_path / "demo_image_001.json"
    assert list_demo(tmp_path) == ["demo_image_001"]
    restored = load_demo("demo_image_001", tmp_path)
    assert restored is not None
    assert restored.model_dump() == original.model_dump()
    assert load_demo("нет_такого", tmp_path) is None
    assert list_demo(tmp_path / "нет_каталога") == []


def test_load_demo_rejects_broken_file(tmp_path):
    (tmp_path / "broken.json").write_text("{}", encoding="utf-8")
    with pytest.raises(ValueError) as error:
        load_demo("broken", tmp_path)
    assert "не соответствует контракту" in str(error.value)


def test_save_demo_validates_contract(tmp_path):
    """Демо с тезисом без сигналов не должно попадать на диск."""
    result = demo_result("demo_image_001")
    result.debate.for_real[0].signal_ids = []
    with pytest.raises(ValueError):
        save_demo(result, tmp_path)
    assert list_demo(tmp_path) == []


@pytest.mark.parametrize("name", ["demo_image_001", "demo_text_001"])
def test_replay_delays_are_bounded_and_deterministic(name):
    result = demo_result(name)
    delays = replay_delays(result)

    assert [row["signal_id"] for row in delays] == [signal.id for signal in result.signals]
    elapsed = 0
    for row in delays:
        assert MIN_DELAY_MS <= row["delay_ms"] <= MAX_DELAY_MS
        elapsed += row["delay_ms"]
        assert row["at_ms"] == elapsed
    assert replay_delays(result) == delays


def test_replay_delays_empty_for_no_signals():
    result = demo_result("demo_image_001")
    result.signals = []
    assert replay_delays(result) == []
