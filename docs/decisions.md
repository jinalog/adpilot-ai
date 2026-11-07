# Architecture Decisions

## ADR-001: 모듈형 Monolith

선택: 하나의 저장소와 FastAPI deployment 안에서 계층/기능 모듈을 분리한다.

대안: 초기부터 microservice. MVP의 작은 팀/트래픽에서 운영 비용과 분산 장애만 늘어나므로 제외했다. 서비스 경계가 실측으로 확인되면 분리한다.

## ADR-002: PostgreSQL을 단일 운영 DB로 사용

선택: campaign과 초기 analytics 모두 PostgreSQL에서 시작한다.

대안: PostgreSQL + DuckDB 동시 도입. 기존 Copilot 코드가 현재 workspace에 없고 MVP 데이터 규모가 작아 중복 persistence를 피한다. 분석 부하/재사용 이점이 확인되면 DuckDB를 다시 평가한다.

## ADR-003: Streamlit은 REST client

선택: Streamlit은 FastAPI만 호출한다.

대안: UI에서 DB/Agent 직접 호출. transaction, 권한, validation이 우회되고 배포 경계가 흐려져 제외했다.

## ADR-004: Python 3.12와 pip-compatible pyproject

선택: 표준 `pyproject.toml`과 setuptools를 사용하며 Docker image로 Python 3.12를 고정한다.

대안: Poetry/uv 전용 lock workflow. 환경에 추가 도구가 필요하고 Phase 0 복잡도를 높여 보류했다. 재현성 강화가 필요하면 lock 도구를 ADR로 추가한다.

## ADR-005: Liveness는 DB와 분리

선택: `/api/v1/health`는 process와 API contract 상태만 확인한다.

대안: health에서 매번 DB query. DB 장애가 API process liveness와 섞이고 restart loop를 만들 수 있다. Phase 1에 dependency readiness endpoint를 별도 추가한다.

## ADR-006: LLM과 LangGraph는 Phase 2에 도입

선택: Phase 0에는 extension package만 두고 의존성과 workflow는 구현하지 않는다.

근거: domain/API 기반과 provider contract가 준비되기 전에 framework 추상화를 만들지 않으며, 외부 API key 없이 초기 환경을 검증한다.

## ADR-007: 명시적 승인과 terminal soft delete

선택: 새 캠페인은 항상 `DRAFT`로 생성하고 별도 승인 API만 `APPROVED`로 변경한다. `ACTIVE` 전환에는 승인 시각이 필요하다. 승인된 설정을 수정하면 승인을 무효화하고 `DRAFT`로 되돌린다. DELETE는 행을 지우지 않고 terminal `INACTIVE` 상태와 비활성화 시각을 기록한다.

대안: CRUD 요청에서 status를 자유롭게 지정하거나 실제 행을 삭제하는 방식. 승인 우회와 변경 이력 손실 위험이 있어 제외했다. 활성/일시정지/비활성 캠페인 설정은 직접 수정하지 않고 명시적 상태 전이를 요구한다.

## ADR-008: 원화 예산은 BIGINT로 저장

선택: `total_budget_krw`, `daily_budget_krw`를 원화 최소 단위의 양수 `BIGINT`로 저장한다.

대안: 부동소수점은 금액 오차가 발생하며, 초기 MVP에서 다중 통화 decimal 모델은 불필요하다. 다중 통화를 지원할 때 currency와 decimal minor-unit 정책을 별도 설계한다.

## ADR-009: Streamlit 화면과 공통 REST client 분리

선택: `frontend/views`는 표시와 사용자 상호작용만 담당하고, 모든 HTTP 호출·timeout·오류 해석·JSON 형태 확인은 `frontend/api_client`에서 처리한다. Dashboard 집계는 기존 목록 API를 상태별 `limit=1`로 호출해 `total`만 사용한다.

대안: Streamlit 화면에서 직접 `requests`를 호출하거나 Dashboard용 Backend endpoint를 추가하는 방식. 전자는 중복 오류 처리와 테스트 어려움을 만들고, 후자는 Phase 1 Backend contract 변경이 필요해 제외했다. 캠페인 규모나 호출 비용이 증가하면 전용 stats endpoint를 다시 검토한다.

## ADR-010: 관리자 UI 상태 전이는 Domain 정책을 그대로 반영

선택: UI는 현재 상태에서 허용된 승인/활성화/일시정지/재활성화 버튼만 표시하고, 비활성화는 명시적 확인 후 실행한다. Backend가 최종 권한과 전이를 검증하며 409를 사용자에게 전달한다.

근거: UI 검증은 우회 가능하므로 보안 경계가 아니다. 화면 편의성과 Backend의 결정론적 규칙을 분리한다.
