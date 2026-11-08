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
| DONE | P0 | AI draft 단위 save idempotency | 반복 save API/DB test와 ADR |
| DONE | P0 | Mock/real LLM provider interface | retry/schema/opt-in contract tests |
| DONE | P0 | LangGraph Campaign Setup workflow와 draft/run 저장 | conditional branch/API/migration tests |
| DONE | P0 | AI Campaign Setup Streamlit REST 화면 | preview/clarification/error/save tests 및 E2E |
| DONE | P0 | Campaign Setup Mock golden dataset 22건 | deterministic runner 22/22 |
| DONE | P0 | Phase 2.1 구조화 refine provider skip 및 실패 초안 보존 | workflow/service/API regression tests |
| DONE | P0 | PostgreSQL 동시 AI draft save 및 rollback 검증 | 독립 Session 경쟁/실패 주입 integration tests |
| DONE | P0 | 재현 가능한 합성 성과 generator와 소유권 분리 | seed/schema/row count 및 안전한 conflict·replace tests |
| DONE | P0 | 결정론적 KPI와 Analytics REST API | 0 분모, 합계 우선, 기간·Campaign 필터 API tests |
| DONE | P0 | 7일 baseline 규칙 anomaly detector와 truth 분리 | known anomaly 4건 precision/recall/F1 evaluation |
| DONE | P0 | Streamlit Performance Dashboard | 실제 격리 Docker API 연결 및 Playwright captures |
| LATER | P1 | Campaign 전반 optimistic concurrency | version/conflict ADR 및 tests |
| DONE | P0 | Safe SQL Performance Analyst | plan/compiler/AST/read-only 및 golden/safety suite |
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

## Phase 2 완료 결과

- 부분 초안과 필수 `CampaignCreate`를 분리하고 누락·검증·provider 실패를 별도 상태로 반환한다.
- transient provider failure만 최대 2회 재시도하며 Mock이 기본값이다.
- 자연어/provider 원문과 비밀은 DB·로그에 저장하지 않는다.
- generate/refine은 Campaign을 만들지 않고, READY save만 기존 Campaign Service를 통해 DRAFT를 만든다.
- draft 단위 중복 저장은 방지했다. Campaign 전체 optimistic concurrency는 범위 밖이며 후속 항목이다.
- 구조화 필드 수정만 있는 refine은 provider를 호출하지 않고도 동일한 누락·검증 경로를 통과한다.
- Provider 실패 시 기존 초안과 실제 누락 필드를 보존하며 상태는 `PROVIDER_ERROR`로 유지한다.
- 전용 PostgreSQL의 독립 Session 경쟁에서 동일 draft save가 Campaign 하나와 일관된 연결만 남기는 것을 검증했다.

## Phase 3 완료 결과

- 기본 dataset은 `analytics-v1`, seed `20261107`, 70일, Campaign 6개, 일별 metric 420행과 truth 4건이다.
- 기존 Campaign은 ownership이 `NULL`이며 generator의 명시적 replace가 삭제하지 않는다.
- KPI는 raw 합계를 먼저 집계하고 0 분모를 `null`로 반환한다.
- detector는 truth를 읽지 않고 이전 7일 raw metric만으로 CTR/CVR/spend/impression 규칙을 계산한다.
- 실제 합성 회귀 결과는 TP 4, FP 0, FN 0, precision/recall/F1 1.0이다. 실제 운영 정확도 주장은 아니다.
- Phase 4의 자연어 SQL, AI 해석, RAG는 구현하지 않았다.

## Phase 4 완료 결과

- Provider는 자연어를 구조화 `AnalysisPlan`으로만 변환하고 SQL/DB/tool 권한을 갖지 않는다.
- 결정론적 compiler와 sqlglot AST validator를 분리해 named parameter, dataset scope, allowlist와 강제 limit을 검증한다.
- PostgreSQL read-only transaction, statement timeout, rollback, 기본 100·절대 500행과 명시적 `truncated`를 적용한다.
- Phase 3 raw totals/KPI를 재사용해 facts와 evidence를 연결하고 hypotheses/recommendations를 물리적으로 분리한다.
- Mock Analyst golden 22/22, SQL safety corpus 40/40이며 실제 LLM 정확도·token·비용 평가는 미실행이다.
- Streamlit은 Analyst REST API만 호출하고 raw SQL 입력이나 Campaign 자동 변경 기능을 제공하지 않는다.
