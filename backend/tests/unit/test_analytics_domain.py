import uuid
from datetime import date, timedelta
from decimal import Decimal

from app.domain.analytics import (
    AnomalyType,
    MetricTotals,
    MetricValue,
    aggregate_metrics,
    calculate_kpis,
    detect_anomalies,
    evaluate_detections,
    round_money,
    round_rate,
)

RUN_ID = uuid.UUID("10000000-0000-0000-0000-000000000001")
CAMPAIGN_ID = uuid.UUID("20000000-0000-0000-0000-000000000001")
START = date(2026, 9, 1)


def metric(
    day: int,
    *,
    impressions: int = 1_000,
    clicks: int = 100,
    conversions: int = 10,
    spend_krw: int = 100_000,
    revenue_krw: int = 300_000,
) -> MetricValue:
    return MetricValue(
        dataset_run_id=RUN_ID,
        campaign_id=CAMPAIGN_ID,
        date=START + timedelta(days=day),
        impressions=impressions,
        clicks=clicks,
        conversions=conversions,
        spend_krw=spend_krw,
        revenue_krw=revenue_krw,
    )


def test_kpis_use_raw_totals_and_decimal_formulas() -> None:
    totals = aggregate_metrics(
        [
            metric(0, impressions=1_000, clicks=100, conversions=10, spend_krw=50_000),
            metric(1, impressions=3_000, clicks=150, conversions=15, spend_krw=150_000),
        ]
    )
    kpis = calculate_kpis(totals)

    assert totals == MetricTotals(4_000, 250, 25, 200_000, 600_000)
    assert kpis.ctr == Decimal("0.0625")
    assert kpis.cvr == Decimal("0.1")
    assert kpis.cpm_krw == Decimal("50000")
    assert kpis.cpc_krw == Decimal("800")
    assert kpis.cpa_krw == Decimal("8000")
    assert kpis.roas == Decimal("3")


def test_all_zero_denominators_return_none_without_changing_raw_values() -> None:
    kpis = calculate_kpis(MetricTotals())

    assert kpis.ctr is None
    assert kpis.cvr is None
    assert kpis.cpm_krw is None
    assert kpis.cpc_krw is None
    assert kpis.cpa_krw is None
    assert kpis.roas is None


def test_rounding_policy_and_large_integer_precision() -> None:
    totals = MetricTotals(
        impressions=9_000_000_000_000_003,
        clicks=3_000_000_000_000_001,
        conversions=1,
        spend_krw=10_000_000_000_000_001,
        revenue_krw=20_000_000_000_000_003,
    )
    kpis = calculate_kpis(totals)

    assert round_rate(kpis.ctr) == Decimal("0.333333")
    assert round_rate(kpis.roas) == Decimal("2.000000")
    assert round_money(Decimal("1.005")) == Decimal("1.01")


def test_detector_fires_all_rules_at_inclusive_thresholds() -> None:
    baseline = [metric(index) for index in range(7)]
    current_metrics = [
        metric(7, clicks=60, conversions=6),
        metric(7, conversions=5),
        metric(7, spend_krw=180_000),
        metric(7, impressions=500, clicks=50, conversions=5, spend_krw=50_000),
    ]
    expected = [
        AnomalyType.CTR_DROP,
        AnomalyType.CVR_DROP,
        AnomalyType.SPEND_SPIKE,
        AnomalyType.IMPRESSION_DROP,
    ]

    for current, anomaly_type in zip(current_metrics, expected, strict=True):
        detections = detect_anomalies([*baseline, current])
        assert anomaly_type in {item.anomaly_type for item in detections}


def test_detector_holds_when_baseline_or_minimum_sample_is_insufficient() -> None:
    assert detect_anomalies([metric(index) for index in range(6)]) == []

    zero_baseline = [
        metric(index, impressions=0, clicks=0, conversions=0, spend_krw=0) for index in range(7)
    ]
    assert detect_anomalies([*zero_baseline, metric(7)]) == []

    low_impression = metric(7, impressions=99, clicks=1, conversions=0)
    low_click = metric(7, impressions=1_000, clicks=19, conversions=0)
    normal_baseline = [metric(index) for index in range(7)]
    assert AnomalyType.CTR_DROP not in {
        item.anomaly_type for item in detect_anomalies([*normal_baseline, low_impression])
    }
    assert AnomalyType.CVR_DROP not in {
        item.anomaly_type for item in detect_anomalies([*normal_baseline, low_click])
    }


def test_evaluation_counts_tp_fp_fn_and_zero_denominators() -> None:
    truth = {(RUN_ID, CAMPAIGN_ID, START, AnomalyType.CTR_DROP)}
    false_key = (RUN_ID, CAMPAIGN_ID, START, AnomalyType.CVR_DROP)
    result = evaluate_detections({*truth, false_key}, truth)

    assert result.true_positive == 1
    assert result.false_positive == 1
    assert result.false_negative == 0
    assert result.precision == Decimal("0.500000")
    assert result.recall == Decimal("1.000000")
    assert result.f1 == Decimal("0.666667")
    empty = evaluate_detections(set(), set())
    assert empty.precision is None
    assert empty.recall is None
    assert empty.f1 is None
