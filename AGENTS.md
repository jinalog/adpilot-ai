# AdPilot AI Agent Guide

## 목표와 범위

이 프로젝트는 합성 광고 데이터를 사용하는 AI 광고 운영 백엔드 포트폴리오다. 목표는 Agent workflow, FastAPI, tool safety, deterministic validation, evaluation, reliability와 운영 역량을 증명하는 것이다. 실제 광고 송출, 비용 지출, 외부 광고 계정 변경을 수행하지 않는다.

현재 단계는 repository 문서와 `docs/roadmap.md`를 확인한다. 요청된 Phase 밖의 기능, 특히 Phase 6 기능을 임의로 구현하지 않는다. 기능 수보다 측정 가능성과 유지보수 비용을 우선한다.

## 아키텍처 규칙

- 계층 방향은 presentation → API → application → domain/infrastructure다.
- Streamlit은 REST API client이며 DB나 Agent를 직접 실행하지 않는다.
- API router에는 비즈니스 규칙을 넣지 않고 service/domain으로 위임한다.
- domain validation과 상태 전이는 LLM/프레임워크와 독립적으로 구현한다.
- LLM은 DB write 권한을 갖지 않는다. 사용자 승인 후 application service만 변경한다.
- AI 출력과 tool result는 Pydantic schema 및 결정론적 규칙으로 검증한다.
- 실제 데이터의 `facts`와 AI의 `hypotheses`를 응답과 저장 구조에서 분리한다.
- 요구가 입증되기 전 microservice, event bus, Redis, DuckDB를 추가하지 않는다.

## 기술 스택

Python 3.12, FastAPI, Pydantic v2, SQLAlchemy 2.x, Alembic, PostgreSQL, Streamlit, pytest, Ruff, Docker Compose를 사용한다. LangGraph/LLM provider는 Phase 2, 분석 SQL은 Phase 4에 도입한다. 새 프레임워크는 문제와 대안, 유지비를 문서화한 뒤 추가한다.

## 코딩과 테스트

- public 경계와 주요 함수에 type hint를 사용한다.
- 작은 명시적 schema와 함수를 선호하고, 미래 기능을 위한 추상화를 미리 만들지 않는다.
- 정상, 오류, 경계 조건을 테스트하고 외부 LLM 없는 경로를 유지한다.
- API 변경에는 request/response 및 status code test를 추가한다.
- DB schema 변경에는 Alembic migration과 upgrade 검증을 포함한다.
- 외부 호출에는 timeout, 제한된 retry와 명시적 실패 응답을 둔다.
- SQL 기능은 read-only, AST validation, allowlist, timeout, row limit을 적용한다.
- 변경 후 가능한 범위에서 `pytest`, `ruff check .`, `ruff format --check .`, `docker compose config`를 실행한다.
- 실행하지 못한 검증을 성공으로 기록하지 않는다.

## 데이터와 보안

- 합성 데이터만 사용하고 anomaly truth label을 생성 데이터와 함께 관리한다.
- `.env`, API key, credential, 개인정보를 커밋하거나 로그에 출력하지 않는다.
- 개발용 기본 비밀번호는 운영용이 아니며 배포 환경에서는 교체한다.
- 금액, 날짜, 상태 변경은 결정론적으로 검증한다.
- destructive operation과 자동 최적화/복구에는 명시적 사용자 승인을 요구한다.

## 변경 절차

1. 현재 Phase, product spec, relevant ADR과 dirty working tree를 확인한다.
2. 수용 기준과 실패/경계 case를 먼저 정한다.
3. 가장 작은 계층별 구현과 migration을 작성한다.
4. unit/API/integration test를 추가하고 실제 실행 결과를 확인한다.
5. scope, API, 운영 방식 또는 기술 선택이 바뀌면 README/docs/backlog/decisions를 갱신한다.
6. 완료 보고에 변경 파일, 실행 명령, 실제 검증 결과, 미완료 항목을 구분한다.
