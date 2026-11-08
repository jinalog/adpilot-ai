import uuid
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal
from enum import StrEnum

RATE_QUANTUM = Decimal("0.000001")
MONEY_QUANTUM = Decimal("0.01")
DETECTOR_VERSION = "rules-v1"
BASELINE_DAYS = 7


class AnomalyType(StrEnum):
    CTR_DROP = "CTR_DROP"
    CVR_DROP = "CVR_DROP"
    SPEND_SPIKE = "SPEND_SPIKE"
    IMPRESSION_DROP = "IMPRESSION_DROP"


@dataclass(frozen=True, slots=True)
class MetricValue:
    dataset_run_id: uuid.UUID
    campaign_id: uuid.UUID
    date: date
    impressions: int
    clicks: int
    conversions: int
    spend_krw: int
    revenue_krw: int


@dataclass(frozen=True, slots=True)
class MetricTotals:
    impressions: int = 0
    clicks: int = 0
    conversions: int = 0
    spend_krw: int = 0
    revenue_krw: int = 0


@dataclass(frozen=True, slots=True)
class KPIValues:
    ctr: Decimal | None
    cvr: Decimal | None
    cpm_krw: Decimal | None
    cpc_krw: Decimal | None
    cpa_krw: Decimal | None
    roas: Decimal | None


@dataclass(frozen=True, slots=True)
class AnomalyDetection:
    dataset_run_id: uuid.UUID
    campaign_id: uuid.UUID
    date: date
    anomaly_type: AnomalyType
    observed_value: Decimal
    baseline_value: Decimal
    change_ratio: Decimal
    threshold: Decimal
    detector_version: str = DETECTOR_VERSION

    @property
    def key(self) -> tuple[uuid.UUID, uuid.UUID, date, AnomalyType]:
        return (self.dataset_run_id, self.campaign_id, self.date, self.anomaly_type)


@dataclass(frozen=True, slots=True)
class EvaluationResult:
    true_positive: int
    false_positive: int
    false_negative: int
    precision: Decimal | None
    recall: Decimal | None
    f1: Decimal | None


def aggregate_metrics(metrics: Iterable[MetricValue]) -> MetricTotals:
    totals = MetricTotals()
    for metric in metrics:
        totals = MetricTotals(
            impressions=totals.impressions + metric.impressions,
            clicks=totals.clicks + metric.clicks,
            conversions=totals.conversions + metric.conversions,
            spend_krw=totals.spend_krw + metric.spend_krw,
            revenue_krw=totals.revenue_krw + metric.revenue_krw,
        )
    return totals


def calculate_kpis(totals: MetricTotals) -> KPIValues:
    return KPIValues(
        ctr=_divide(totals.clicks, totals.impressions),
        cvr=_divide(totals.conversions, totals.clicks),
        cpm_krw=_divide(totals.spend_krw * 1_000, totals.impressions),
        cpc_krw=_divide(totals.spend_krw, totals.clicks),
        cpa_krw=_divide(totals.spend_krw, totals.conversions),
        roas=_divide(totals.revenue_krw, totals.spend_krw),
    )


def round_rate(value: Decimal | None) -> Decimal | None:
    return None if value is None else value.quantize(RATE_QUANTUM, rounding=ROUND_HALF_UP)


def round_money(value: Decimal | None) -> Decimal | None:
    return None if value is None else value.quantize(MONEY_QUANTUM, rounding=ROUND_HALF_UP)


def detect_anomalies(metrics: Iterable[MetricValue]) -> list[AnomalyDetection]:
    grouped: dict[uuid.UUID, list[MetricValue]] = defaultdict(list)
    for metric in metrics:
        grouped[metric.campaign_id].append(metric)

    detections: list[AnomalyDetection] = []
    for campaign_metrics in grouped.values():
        by_date = {metric.date: metric for metric in campaign_metrics}
        for current in sorted(campaign_metrics, key=lambda item: item.date):
            baseline = [
                by_date.get(current.date - timedelta(days=offset))
                for offset in range(BASELINE_DAYS, 0, -1)
            ]
            if any(item is None for item in baseline):
                continue
            complete_baseline = [item for item in baseline if item is not None]
            detections.extend(_detect_for_day(current, complete_baseline))
    return detections


def evaluate_detections(
    predicted_keys: set[tuple[uuid.UUID, uuid.UUID, date, AnomalyType]],
    truth_keys: set[tuple[uuid.UUID, uuid.UUID, date, AnomalyType]],
) -> EvaluationResult:
    true_positive = len(predicted_keys & truth_keys)
    false_positive = len(predicted_keys - truth_keys)
    false_negative = len(truth_keys - predicted_keys)
    precision = _divide(true_positive, true_positive + false_positive)
    recall = _divide(true_positive, true_positive + false_negative)
    if precision is None or recall is None or precision + recall == 0:
        f1 = None if precision is None or recall is None else Decimal(0)
    else:
        f1 = Decimal(2) * precision * recall / (precision + recall)
    return EvaluationResult(
        true_positive=true_positive,
        false_positive=false_positive,
        false_negative=false_negative,
        precision=round_rate(precision),
        recall=round_rate(recall),
        f1=round_rate(f1),
    )


def _detect_for_day(
    current: MetricValue,
    baseline: list[MetricValue],
) -> list[AnomalyDetection]:
    detections: list[AnomalyDetection] = []
    baseline_ctr = _average_ratios((item.clicks, item.impressions) for item in baseline)
    current_ctr = _divide(current.clicks, current.impressions)
    if current.impressions >= 100:
        detection = _drop_detection(
            current,
            AnomalyType.CTR_DROP,
            current_ctr,
            baseline_ctr,
            Decimal("0.60"),
        )
        if detection:
            detections.append(detection)

    baseline_cvr = _average_ratios((item.conversions, item.clicks) for item in baseline)
    current_cvr = _divide(current.conversions, current.clicks)
    if current.clicks >= 20:
        detection = _drop_detection(
            current,
            AnomalyType.CVR_DROP,
            current_cvr,
            baseline_cvr,
            Decimal("0.50"),
        )
        if detection:
            detections.append(detection)

    baseline_spend = _average(Decimal(item.spend_krw) for item in baseline)
    detection = _spike_detection(
        current,
        AnomalyType.SPEND_SPIKE,
        Decimal(current.spend_krw),
        baseline_spend,
        Decimal("1.80"),
    )
    if detection:
        detections.append(detection)

    baseline_impressions = _average(Decimal(item.impressions) for item in baseline)
    detection = _drop_detection(
        current,
        AnomalyType.IMPRESSION_DROP,
        Decimal(current.impressions),
        baseline_impressions,
        Decimal("0.50"),
    )
    if detection:
        detections.append(detection)
    return detections


def _drop_detection(
    metric: MetricValue,
    anomaly_type: AnomalyType,
    observed: Decimal | None,
    baseline: Decimal | None,
    threshold: Decimal,
) -> AnomalyDetection | None:
    if observed is None or baseline is None or baseline == 0:
        return None
    ratio = observed / baseline
    if ratio > threshold:
        return None
    return _detection(metric, anomaly_type, observed, baseline, ratio, threshold)


def _spike_detection(
    metric: MetricValue,
    anomaly_type: AnomalyType,
    observed: Decimal,
    baseline: Decimal | None,
    threshold: Decimal,
) -> AnomalyDetection | None:
    if baseline is None or baseline == 0:
        return None
    ratio = observed / baseline
    if ratio < threshold:
        return None
    return _detection(metric, anomaly_type, observed, baseline, ratio, threshold)


def _detection(
    metric: MetricValue,
    anomaly_type: AnomalyType,
    observed: Decimal,
    baseline: Decimal,
    ratio: Decimal,
    threshold: Decimal,
) -> AnomalyDetection:
    return AnomalyDetection(
        dataset_run_id=metric.dataset_run_id,
        campaign_id=metric.campaign_id,
        date=metric.date,
        anomaly_type=anomaly_type,
        observed_value=round_rate(observed) or Decimal(0),
        baseline_value=round_rate(baseline) or Decimal(0),
        change_ratio=round_rate(ratio) or Decimal(0),
        threshold=threshold,
    )


def _average(values: Iterable[Decimal]) -> Decimal | None:
    collected = list(values)
    return None if not collected else sum(collected, Decimal(0)) / Decimal(len(collected))


def _average_ratios(values: Iterable[tuple[int, int]]) -> Decimal | None:
    ratios: list[Decimal] = []
    for numerator, denominator in values:
        ratio = _divide(numerator, denominator)
        if ratio is None:
            return None
        ratios.append(ratio)
    return _average(ratios)


def _divide(numerator: int | Decimal, denominator: int | Decimal) -> Decimal | None:
    if denominator == 0:
        return None
    return Decimal(numerator) / Decimal(denominator)
