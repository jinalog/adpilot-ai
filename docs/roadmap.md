# Roadmap

## Phase 0 — Project Initialization

완료 조건: Python 3.12 환경 정의, FastAPI health endpoint, Streamlit API 연결 화면, PostgreSQL Compose, Alembic scaffold, 외부 서비스 없는 test, lint 구성, 요구사항/아키텍처/평가 문서가 준비된다.

## Phase 1 — Campaign Backend

**완료.** Campaign entity, repository/service, 최초 migration, CRUD, deterministic budget/date/state rules, approval invalidation, soft deactivate와 API error contract를 구현했다. SQLite 기반 domain/API test와 전용 PostgreSQL migration round trip으로 검증한다.

## Phase 1.5 — Campaign Administration UI

**완료.** 기존 Campaign REST API만 사용하는 Streamlit Dashboard, 목록/필터/페이지네이션, 생성, 상세/수정, 승인·활성화·일시정지·재활성화·확인형 비활성화 화면을 구현했다. 공통 API client가 timeout, 연결 실패, HTTP validation과 비정상 JSON을 구분하며 mock client test와 전체 Docker/PostgreSQL 흐름으로 검증한다.

## Phase 2 — AI Campaign Setup

Phase 1의 검증/저장 use case 위에 provider interface, mock provider, LangGraph workflow, structured draft, missing-field handling, bounded retry, approval과 agent run history를 추가한다. LLM key 없이 전체 workflow test가 재현되는 것이 완료 조건이다.

## Phase 3 — Advertising Analytics

30일 이상 합성 데이터와 anomaly truth label, KPI service/API, dashboard, 규칙 기반 detector를 구현한다. seed 재현성, 0 나눗셈 규칙, known anomaly 탐지 test가 완료 조건이다.

## Phase 4 — AI Performance Analyst

질문 계획, 안전한 read-only SQL, 근거 조회, 사실/가설 분리 응답을 구현한다. malicious/invalid SQL 차단, timeout/row limit, 대표 질문 정답 검증이 완료 조건이다.

## Phase 5 — Evaluation & Reliability

golden dataset, 평가 runner, latency/failure/token/cost 관측, 구조화 logging, failure injection과 부하 테스트를 추가한다. 실행 가능한 평가 보고서와 재현 명령이 완료 조건이다.

## Phase 6 — Advanced Agents

MVP 결과와 취업 포트폴리오 가치로 우선순위를 다시 평가한다. 기본 순서는 incident recovery, creative review, RAG, OpenRTB simulator, Kafka, auto optimization이다. 각 기능은 별도 승인과 설계 결정 후 진행한다.
