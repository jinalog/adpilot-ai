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

### Campaign Administration UI (Phase 1.5)

Streamlit sidebar 화면 → 공통 `AdPilotApiClient` → FastAPI Campaign API → application service → domain rules → PostgreSQL 순서로만 호출한다. UI는 DB, repository, service를 import하지 않는다. Client는 timeout과 HTTP/JSON 오류를 표준화하고, 화면은 404/409/422/연결 실패를 구분해 표시한다. 변경 성공 후 Streamlit state를 갱신해 최신 상세나 목록을 다시 조회한다.

Dashboard는 전체와 상태별 목록 API를 `limit=1`로 호출하고 응답의 `total`만 사용한다. 별도 집계 endpoint를 추가하지 않아 Backend contract를 유지하면서 전체 캠페인 payload의 반복 다운로드를 피한다.

### 캠페인 설정 (Phase 2)

자연어 요청 → AI 부분 초안 → 누락 확인/보완 → Pydantic 및 Campaign domain 검증 → 사용자 편집·확인 → Campaign Service로 `DRAFT` 저장 → 별도 승인 API 순서다. 생성·보완 단계는 `campaign_drafts`와 `agent_runs`만 기록하며 Campaign 행을 만들지 않는다. Agent와 provider는 DB write/tool 권한이 없고 save application use case만 Campaign을 생성한다.

LangGraph는 입력 텍스트 유무를 판단하는 시작 conditional edge, `extract_requirements`/`skip_provider_extraction`, `merge_context`, `check_missing_fields`, `validate_draft`, preview/clarification/provider-error 노드를 사용한다. `additional_input`이 유효한 텍스트일 때만 provider 추출을 실행하고, 구조화 `draft_updates`만 있는 refine은 provider를 호출하지 않은 채 기존 초안과 병합한 뒤 동일한 누락·결정론적 검증을 거친다. 완료 상태는 `READY`, `NEEDS_CLARIFICATION`, `VALIDATION_FAILED`, `PROVIDER_ERROR`로 분기한다. 동일 draft save는 PostgreSQL 행 잠금과 단일 transaction으로 연결된 Campaign을 재사용한다.

### 성과 분석 (Phase 3)

고정 seed generator → dataset run과 소유 Campaign → 일별 raw metric → FastAPI application service → 결정론적 KPI/규칙 detector → Streamlit REST client 순서다. KPI는 Campaign·기간의 raw 합계를 먼저 집계한 뒤 계산하며 0 분모는 `null`이다. 조회 기간은 inclusive, 최대 366일이고 Campaign 필터는 선택한 dataset 소유 여부를 검사한다.

`rules-v1` detector는 현재일을 제외한 정확한 이전 7 calendar day를 `(dataset_run_id, campaign_id)`별 baseline으로 사용한다. Campaign UUID가 우연히 같아도 서로 다른 dataset run의 metric은 같은 날짜 맵이나 baseline에 들어가지 않는다. `anomaly_truth_labels`는 generator와 평가 runner만 읽으며, 제품의 `/analytics/anomalies`는 raw metric으로 매 요청 계산한 detection만 반환한다. 따라서 정답을 결과로 노출하거나 detector가 정답을 참조하지 않는다.

Performance Dashboard는 FastAPI 응답을 list-of-records chart data로 변환해 Streamlit에 전달한다. Frontend 코드가 `pandas`를 직접 import하지 않아 Streamlit의 transitive dependency를 프로젝트 API처럼 취급하지 않는다. KPI는 3개 행, 추세는 4개 단위별 그래프로 나누며 계산식은 계속 Backend domain에만 둔다.

### AI Performance Analyst (Phase 4, 미구현)

향후 질문 → 분석 계획/제한된 SQL 후보 → AST 및 allowlist 검사 → read-only timeout 실행 → 결정론적 KPI → LLM 설명 흐름을 추가한다. Phase 3의 raw metric과 KPI API를 재사용하며 응답은 `facts`, `hypotheses`, `recommendations`, `evidence`를 분리한다. 현재 자연어 SQL과 LLM 설명은 구현하지 않았다.

## Agent Workflow 원칙

Workflow state에는 request ID, 단계, 검증 오류, retry 수, tool result reference, latency와 token usage를 둔다. 외부 호출에는 timeout과 제한된 retry를 적용한다. provider 미사용 실행은 `not_used`/`structured-updates-only`, retry 0, token usage `null`로 실제 provider 실행과 구분한다. 구조화 출력 실패는 원문을 저장 대상으로 사용하지 않으며, 최종 실패를 명시적으로 반환한다. Provider 실패 시 기존 초안을 보존하고 그 값을 기준으로 실제 누락 필드만 다시 계산한다. Mock provider 결과도 실제 provider 결과와 구분한다.

## 데이터 모델 방향

Phase 1의 `campaigns`는 UUID, 이름/목표, 원화 정수 예산, 기간, JSON 채널/타게팅, 상태, 승인·비활성화·생성·수정 시각을 저장한다. DB check constraint와 domain validation을 함께 적용해 우회 저장도 방어한다. Phase 2의 `campaign_drafts`는 현재 구조화 값과 판정만, `agent_runs`는 provider/model/retry/latency/usage/error metadata만 저장한다. 자연어와 provider 원문은 저장하지 않는다.

Phase 3의 `synthetic_dataset_runs`는 seed, schema version, 기간과 generation config를 기록한다. `campaigns.synthetic_dataset_run_id`는 generator 소유권을 명시하며 기존 Campaign은 `NULL`로 유지한다. `daily_ad_metrics`는 dataset×Campaign×date 단위의 impressions/clicks/conversions/spend/revenue 원시값을, `anomaly_truth_labels`는 평가용 주입 유형과 metadata를 저장한다. detection 결과는 저장하지 않는다. 동일 dataset 이름은 기본 거부하며 정확한 ID를 명시한 교체만 해당 run 소유 데이터를 transaction 안에서 삭제·재생성한다.

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
