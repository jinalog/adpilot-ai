# Architecture

## 시스템 구성

```text
┌──────────────────┐       HTTP/JSON       ┌─────────────────────────────┐
│ Streamlit Client │ ────────────────────> │ FastAPI                     │
└──────────────────┘                       │ API schemas + error mapping │
                                           └──────────────┬──────────────┘
                                                          │
                                           ┌──────────────▼──────────────┐
                                           │ Application Services        │
                                           │ use case / transaction      │
                                           └───────┬──────────┬──────────┘
                                                   │          │ Phase 2+
                                      ┌────────────▼───┐  ┌───▼───────────┐
                                      │ Domain Rules   │  │ Agent Workflow│
                                      │ deterministic  │  │ bounded tools │
                                      └────────┬───────┘  └───┬───────────┘
                                               │              │
                                      ┌────────▼────────┐ ┌───▼───────────┐
                                      │ PostgreSQL      │ │ LLM Provider  │
                                      │ SQLAlchemy      │ │ mock / real   │
                                      └─────────────────┘ └───────────────┘
```

## 모듈 책임

- `frontend`: 화면 표시와 REST 호출만 담당하며 DB/Agent를 직접 호출하지 않는다.
- `app/api`: HTTP 계약, routing, 상태 코드와 오류 변환을 담당한다.
- `app/schemas`: 외부 입력과 출력의 Pydantic 계약이다.
- `app/services`: use case, 승인 확인, transaction boundary를 담당한다.
- `app/domain`: 캠페인 규칙, 상태 전이, KPI 정의처럼 프레임워크와 무관한 정책이다.
- `app/agents`: LLM workflow와 제한된 tool 연결만 담당한다.
- `app/db`, `app/infrastructure`: SQLAlchemy와 외부 provider 구현을 담당한다.
- `evaluations`: 제품 테스트와 분리된 AI 품질 데이터셋 및 runner다.

## 데이터 흐름

### 캠페인 설정 (Phase 2)

자연어 요청 → Agent structured draft → Pydantic validation → domain validation → 사용자 확인 → application service 승인 → transaction → PostgreSQL. Agent는 DB write tool을 갖지 않는다.

### 성과 분석 (Phase 3–4)

질문 → 분석 계획/제한된 SQL 후보 → AST 및 allowlist 검사 → read-only timeout 실행 → 결정론적 KPI → LLM 설명. 응답은 `facts`, `hypotheses`, `recommendations`, `evidence`를 분리한다.

## Agent Workflow 원칙

Workflow state에는 request ID, 단계, 검증 오류, retry 수, tool result reference, latency와 token usage를 둔다. 외부 호출에는 timeout과 제한된 retry를 적용한다. 구조화 출력 실패는 원문을 저장 대상으로 사용하지 않으며, 최종 실패를 명시적으로 반환한다. Mock provider 결과는 실제 provider 결과와 구분한다.

## 데이터 모델 방향

Phase 1의 `campaigns`는 UUID, 이름/목표, 원화 정수 예산, 기간, JSON 채널/타게팅, 상태, 승인·비활성화·생성·수정 시각을 저장한다. DB check constraint와 domain validation을 함께 적용해 우회 저장도 방어한다. Phase 2에는 승인 전 AI `campaign_drafts`와 `agent_runs`, Phase 3에는 `daily_ad_metrics`와 anomaly label/result를 추가한다.

상태 전이는 `DRAFT --approve--> APPROVED --> ACTIVE <--> PAUSED`이며 모든 비활성 상태에서 `INACTIVE`로 이동할 수 있다. `INACTIVE`는 terminal state다. 승인된 설정을 수정하면 승인을 무효화하고 `DRAFT`로 되돌린다. 실제 삭제 대신 상태와 `deactivated_at`을 남기는 soft delete를 사용한다.

## 신뢰 경계와 보안

- 자연어와 LLM 출력은 신뢰하지 않는 입력이다.
- 비밀 값과 사용자 원문은 로그에서 필터링한다.
- DB write는 승인된 application use case만 수행한다.
- analytics DB role은 read-only로 분리할 수 있게 설계한다.
- SQL은 단일 SELECT/CTE, allowlisted table/column, row limit, timeout으로 제한한다.
- 프로젝트 데이터는 합성 데이터만 사용한다.

## 확장 방향

MVP가 측정 가능하게 완료된 뒤 incident agent, creative review, RAG knowledge service를 각각 독립 application module로 추가할 수 있다. 트래픽이나 장애 격리 요구가 실제로 확인되기 전에는 monolith를 유지하며 Kafka와 microservice를 도입하지 않는다.
