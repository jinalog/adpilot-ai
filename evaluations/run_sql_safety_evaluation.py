import json
from pathlib import Path

from app.domain.analyst_sql import SQLASTValidator, SQLSafetyError

DATASET = Path(__file__).with_name("datasets") / "sql_safety_corpus.json"


def main() -> int:
    cases = json.loads(DATASET.read_text())
    validator = SQLASTValidator()
    passed = 0
    failures: list[str] = []
    for case in cases:
        allowed = True
        try:
            validator.validate(case["sql"])
        except SQLSafetyError:
            allowed = False
        if allowed == case["allowed"]:
            passed += 1
        else:
            failures.append(f"{case['id']}: expected allowed={case['allowed']}, got {allowed}")
    print(f"SQL safety corpus: {passed}/{len(cases)} passed")
    print("Deterministic AST result; no SQL in this corpus was executed.")
    for failure in failures:
        print(f"FAIL {failure}")
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
