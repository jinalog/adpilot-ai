# Backlog

상태 표기: `DONE`, `NEXT`, `LATER`.

| 상태 | 우선순위 | 작업 | 검증 |
|---|---:|---|---|
| DONE | P0 | Phase 0 디렉터리와 Python 패키지 구성 | import/build |
| DONE | P0 | FastAPI health endpoint와 OpenAPI | API unit test |
| DONE | P0 | Streamlit REST client 화면 | backend 연결 확인 |
| DONE | P0 | PostgreSQL/Docker Compose | config 및 container health |
| DONE | P0 | pytest/Ruff 구성 | test/lint command |
| DONE | P0 | 제품·아키텍처·평가 문서 | 범위 교차 검토 |
| DONE | P0 | Campaign aggregate와 상태 전이 정의 | domain unit tests |
| DONE | P0 | Campaign SQLAlchemy model/initial migration | upgrade/downgrade |
| DONE | P0 | Campaign repository/service | API 및 migration integration tests |
| DONE | P0 | CRUD/deactivate/approve API | API normal/error/boundary tests |
| DONE | P0 | Streamlit Campaign Dashboard와 sidebar navigation | 실제 Backend 연결 |
| DONE | P0 | Campaign 목록/생성/상세/수정 UI | API client mock 및 E2E |
| DONE | P0 | 승인/상태/확인형 비활성화 UI | 상태 lifecycle E2E |
| DONE | P0 | API 오류 분류와 표시 | 404/409/422/timeout/connection tests |
| NEXT | P1 | idempotency 및 optimistic concurrency 결정 | conflict tests/ADR |
| LATER | P1 | Mock/real LLM provider interface | contract tests |
| LATER | P1 | Campaign Setup workflow와 draft | golden dataset |
| LATER | P1 | 합성 데이터/KPI/anomaly | deterministic tests |
| LATER | P1 | Safe SQL Analyst | security/evaluation suite |
| LATER | P2 | observability와 load test | measured report |

## Phase 1 세부 수용 기준

- Campaign 필드와 상태 enum이 API, domain, DB에서 일관된다.
- 예산은 양수이고 일예산/총예산 관계 규칙이 테스트된다.
- 종료일은 시작일보다 빠를 수 없으며 timezone/date 정책이 명시된다.
- 허용되지 않은 상태 전이와 승인되지 않은 활성화가 차단된다.
- 삭제 정책은 기본적으로 soft delete/deactivate이며 감사 필드를 남긴다.
- create/list/get/update/deactivate/approve API의 status code와 error body가 테스트된다.
- migration을 빈 PostgreSQL에 적용하고 되돌리는 검증을 수행한다.
- 실제 검증 결과만 README 또는 작업 보고에 기록한다.
