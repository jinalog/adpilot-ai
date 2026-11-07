# Product Specification

## 문제와 목표

광고 운영자는 캠페인 설정의 복잡성, 성과 데이터 해석 비용, 이상 상황의 늦은 발견을 겪습니다. AdPilot AI는 자연어 입력을 검증 가능한 초안과 데이터 근거가 있는 분석으로 변환하되, 금액·날짜·상태 변경 같은 핵심 판단은 백엔드가 결정론적으로 통제합니다.

주요 사용자는 합성 광고 환경의 광고 운영자입니다. 취업 포트폴리오 관점에서는 Agent workflow, tool calling, 안전한 SQL, 상태/실패 관리, 평가와 운영 역량을 보여주는 것이 제품 기능 수보다 중요합니다.

## 주요 사용자 시나리오

1. 운영자가 목표, 예산, 기간, 채널을 자연어로 입력한다.
2. Setup Agent가 구조화된 캠페인 초안을 만들고 누락 정보를 표시한다.
3. 백엔드 validator가 예산, 기간, 타게팅 규칙을 검증한다.
4. 운영자가 검증 결과를 확인하고 승인해야 캠페인이 저장된다.
5. 운영자는 합성 성과 지표와 규칙 기반 이상을 조회한다.
6. Analyst 질문에는 실제 계산 지표와 AI 가설이 분리되어 표시된다.

## MVP 범위

- 승인 전 초안과 승인된 캠페인을 분리한 Campaign Management
- Pydantic structured output 기반 AI Campaign Setup
- 30일 이상 합성 성과 및 삽입 anomaly 정답 label
- CTR, CVR, CPM, CPC, CPA, ROAS 등 결정론적 KPI
- CTR/CVR 급락, spend 급증, impression 급감 규칙 탐지
- 제한된 read-only SQL과 근거 데이터 기반 Analyst
- 정확도, 차단률, precision/recall, latency, 실패율, token/cost 평가
- FastAPI, PostgreSQL, Streamlit, Docker 기반 단일 저장소

## 전체 제품 기능

MVP 이후 후보는 creative 생성·심사, OpenRTB simulator, incident detection/recovery, advertising knowledge RAG, Kafka pipeline, 자동 최적화, 인증/RBAC, Prometheus/Grafana, Kubernetes입니다. 이들은 별도 우선순위 결정 없이 구현하지 않습니다.

## 제외 기능

- 실제 광고 송출, 입찰, 광고비 지출
- 실제 광고 계정이나 외부 운영 설정 변경
- 실사용자 개인정보 또는 실제 광고 성과 데이터
- 승인 없는 자동 예산/타게팅 변경 및 복구
- Phase 0의 LLM/LangGraph, 캠페인 CRUD, analytics 구현
- 초기 MVP의 마이크로서비스, Kafka, Kubernetes

## MVP 수용 기준

- 모든 AI 출력이 명시적 Pydantic schema를 통과하거나 안전하게 실패한다.
- 누락된 필수 정보는 임의로 확정하지 않고 사용자에게 표시한다.
- invalid budget/date/state transition이 저장 전에 차단된다.
- 승인 전 초안과 운영 캠페인이 DB와 API에서 구분된다.
- KPI는 정의된 0 나눗셈 정책으로 재현 가능하게 계산된다.
- SQL은 read-only, table allowlist, AST, timeout, row limit 정책을 통과해야 한다.
- anomaly label 데이터셋으로 precision/recall을 재현할 수 있다.
- 외부 LLM 없이 핵심 테스트와 평가의 deterministic subset을 실행할 수 있다.
- 문서에는 실제 실행한 검증과 미실행 항목이 구분되어 있다.
