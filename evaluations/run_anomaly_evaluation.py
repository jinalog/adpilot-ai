import argparse
import uuid

from app.db.session import SessionLocal
from app.domain.analytics import (
    AnomalyType,
    EvaluationResult,
    detect_anomalies,
    evaluate_detections,
)
from app.infrastructure.analytics_repository import AnalyticsRepository


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate deterministic anomaly rules")
    parser.add_argument("--dataset-run-id", type=uuid.UUID)
    parser.add_argument("--dataset-name", default="phase3-default")
    args = parser.parse_args()

    with SessionLocal() as session:
        repository = AnalyticsRepository(session)
        dataset = (
            repository.get_dataset(args.dataset_run_id)
            if args.dataset_run_id
            else repository.get_dataset_by_name(args.dataset_name)
        )
        if dataset is None:
            parser.error("dataset was not found")
        metrics = repository.list_metrics(
            dataset_run_id=dataset.id,
            start_date=dataset.start_date,
            end_date=dataset.end_date,
        )
        truth = repository.list_truth_labels(dataset.id)

    detections = detect_anomalies(metrics)
    predicted_keys = {item.key for item in detections}
    truth_keys = {
        (item.dataset_run_id, item.campaign_id, item.date, AnomalyType(item.anomaly_type))
        for item in truth
    }
    for anomaly_type in AnomalyType:
        result = evaluate_detections(
            {key for key in predicted_keys if key[3] is anomaly_type},
            {key for key in truth_keys if key[3] is anomaly_type},
        )
        _print_result(anomaly_type.value, result)
    _print_result("OVERALL", evaluate_detections(predicted_keys, truth_keys))
    print("Synthetic regression evaluation; this is not real-advertising accuracy.")
    return 0


def _print_result(label: str, result: EvaluationResult) -> None:
    print(
        f"{label}: TP={result.true_positive} FP={result.false_positive} "
        f"FN={result.false_negative} precision={result.precision} "
        f"recall={result.recall} f1={result.f1}"
    )


if __name__ == "__main__":
    raise SystemExit(main())
