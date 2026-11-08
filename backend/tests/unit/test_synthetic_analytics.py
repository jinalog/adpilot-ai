from dataclasses import replace

from app.domain.analytics import AnomalyType
from app.domain.synthetic_analytics import SyntheticDatasetConfig, build_synthetic_dataset


def test_same_seed_and_config_produce_identical_plan() -> None:
    config = SyntheticDatasetConfig()

    assert build_synthetic_dataset(config) == build_synthetic_dataset(config)


def test_different_seed_changes_metrics_and_identity() -> None:
    first = build_synthetic_dataset(SyntheticDatasetConfig(seed=1))
    second = build_synthetic_dataset(SyntheticDatasetConfig(seed=2))

    assert first.id != second.id
    assert first.metrics != second.metrics


def test_default_dataset_meets_duration_invariants_and_truth_contract() -> None:
    plan = build_synthetic_dataset(SyntheticDatasetConfig())

    assert plan.config.days >= 60
    assert len(plan.campaigns) >= 6
    assert len(plan.metrics) == plan.config.days * len(plan.campaigns)
    assert {item.anomaly_type for item in plan.truth_labels} == set(AnomalyType)
    for metric in plan.metrics:
        campaign = next(item for item in plan.campaigns if item.id == metric.campaign_id)
        assert campaign.start_date <= metric.date <= campaign.end_date
        assert 0 <= metric.conversions <= metric.clicks <= metric.impressions
        assert metric.spend_krw >= 0
        assert metric.revenue_krw >= 0


def test_minimum_generation_limits_are_enforced() -> None:
    for config in (
        replace(SyntheticDatasetConfig(), days=59),
        replace(SyntheticDatasetConfig(), campaign_count=5),
    ):
        try:
            build_synthetic_dataset(config)
        except ValueError:
            pass
        else:
            raise AssertionError("invalid synthetic generation config must be rejected")
