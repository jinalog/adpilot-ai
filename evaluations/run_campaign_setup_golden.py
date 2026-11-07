import argparse
import json
from pathlib import Path

from app.agents.campaign_setup import CampaignSetupWorkflow
from app.agents.providers import MockCampaignProvider


def evaluate(dataset_path: Path) -> tuple[int, int, list[str]]:
    cases = json.loads(dataset_path.read_text())
    workflow = CampaignSetupWorkflow(MockCampaignProvider(), timeout_seconds=1, max_retries=2)
    passed = 0
    failures: list[str] = []
    for case in cases:
        result = workflow.run(case["prompt"])
        checks = [result["status"] == case["expected_status"]]
        checks.extend(
            result["draft"].get(key) == value for key, value in case["expected_fields"].items()
        )
        checks.extend(field in result["missing_fields"] for field in case["missing_fields"])
        errors = " ".join(result["validation_errors"])
        checks.extend(error in errors for error in case["error_types"])
        if all(checks):
            passed += 1
        else:
            failures.append(case["id"])
    return passed, len(cases), failures


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate deterministic Mock campaign extraction")
    parser.add_argument(
        "dataset",
        nargs="?",
        type=Path,
        default=Path("evaluations/datasets/campaign_setup_golden.json"),
    )
    args = parser.parse_args()
    passed, total, failures = evaluate(args.dataset)
    print(f"Mock golden dataset: {passed}/{total} passed")
    if failures:
        print("Failed cases: " + ", ".join(failures))
        return 1
    print("This deterministic Mock result is not real-LLM accuracy.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
