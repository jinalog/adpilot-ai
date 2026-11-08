import argparse
import uuid
from datetime import date

from app.core.exceptions import ApplicationError
from app.db.session import SessionLocal
from app.domain.synthetic_analytics import (
    DEFAULT_CAMPAIGN_COUNT,
    DEFAULT_DAYS,
    DEFAULT_SEED,
    DEFAULT_START_DATE,
    SyntheticDatasetConfig,
    build_synthetic_dataset,
)
from app.infrastructure.analytics_repository import AnalyticsRepository
from app.services.analytics_service import SyntheticDatasetService


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate deterministic synthetic ad analytics")
    parser.add_argument("--name", default="phase3-default")
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument("--start-date", type=date.fromisoformat, default=DEFAULT_START_DATE)
    parser.add_argument("--days", type=int, default=DEFAULT_DAYS)
    parser.add_argument("--campaign-count", type=int, default=DEFAULT_CAMPAIGN_COUNT)
    parser.add_argument("--replace-dataset-id", type=uuid.UUID)
    args = parser.parse_args()

    plan = build_synthetic_dataset(
        SyntheticDatasetConfig(
            name=args.name,
            seed=args.seed,
            start_date=args.start_date,
            days=args.days,
            campaign_count=args.campaign_count,
        )
    )
    try:
        with SessionLocal() as session:
            saved = SyntheticDatasetService(AnalyticsRepository(session)).create(
                plan,
                replace_dataset_id=args.replace_dataset_id,
            )
    except ApplicationError as exc:
        print(f"error: {exc.message}")
        return 2
    print(f"dataset_run_id={saved.id}")
    print(
        f"name={saved.name} seed={saved.seed} schema={saved.schema_version} "
        f"period={saved.start_date}..{saved.end_date}"
    )
    print(
        f"campaigns={len(plan.campaigns)} metrics={len(plan.metrics)} "
        f"truth_labels={len(plan.truth_labels)}"
    )
    print("All rows are synthetic; no real advertising data was used.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
