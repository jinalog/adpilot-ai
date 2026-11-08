# AdPilot AI

AdPilot AI는 자연어 캠페인 설정, 광고 성과 분석, 이상 탐지를 안전한 승인 흐름과 결합하는 AI 광고 운영 플랫폼입니다. 실제 광고 송출이나 광고 계정 변경이 아닌 합성 데이터 기반 포트폴리오 프로젝트이며, AI Backend/Agent Platform 설계 역량을 검증하는 것이 목적입니다.

현재 상태는 **Phase 4 — AI Performance Analyst 완료**입니다. Phase 3.1의 합성 성과와 KPI 위에 구조화 `AnalysisPlan`, 결정론적 SQL compiler, PostgreSQL AST safety validator, read-only/timeout/row-limit executor와 사실·가설·추천·근거 분리 응답을 추가했습니다. 기본 Provider는 외부 호출이 없는 Mock이며 실제 LLM, 실제 광고 데이터, 사용자 raw SQL과 자동 Campaign 변경은 사용하지 않습니다.

## 목표 기능

- 자연어 요구사항을 검증 가능한 캠페인 초안으로 변환
- 사용자 승인 후에만 운영 캠페인 상태로 전환
- 결정론적으로 광고 KPI를 계산하고 규칙 기반 이상 탐지
- 읽기 전용·허용 목록·AST 검증을 적용한 분석 워크플로
- 실제 데이터 사실과 AI의 원인 가설을 명확히 구분
- Agent 실행 이력, timeout, retry, 평가 및 비용 추적

## 기술 스택

- Python 3.12, FastAPI, Pydantic v2
- SQLAlchemy 2.x, Alembic, PostgreSQL 16
- Streamlit REST client
- pytest, Ruff
- Docker, Docker Compose
- LangGraph, Mock/OpenAI Responses provider adapter
- sqlglot PostgreSQL AST parser

## 아키텍처

```text
Streamlit -> FastAPI API -> Application Service -> Domain Rules
                         -> Agent Orchestration -> LLM Provider (Phase 2+)
                         -> SQLAlchemy -> PostgreSQL
```

Presentation, API, application, domain, infrastructure 계층을 분리합니다. LLM은 DB를 직접 변경하지 않으며, 구조화 출력과 결정론적 검증을 통과한 요청만 application service가 처리합니다. 자세한 내용은 [architecture](docs/architecture.md)를 참고하세요.

## Docker로 실행

필수 조건은 Docker Desktop 또는 호환 Docker Engine입니다.

```bash
cp .env.example .env
docker compose up -d postgres
docker compose run --rm --build backend alembic upgrade head
docker compose up --build
```

- API 문서: <http://localhost:8000/docs>
- Health check: <http://localhost:8000/api/v1/health>
- Streamlit: <http://localhost:8501>
- PostgreSQL: `localhost:5432`

종료:

```bash
docker compose down
```

DB 볼륨까지 삭제하려면 데이터 손실을 확인한 후 명시적으로 `docker compose down -v`를 실행합니다.

## 로컬로 실행

Python 3.12가 필요합니다.

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e ".[dev,frontend]"
cp .env.example .env
uvicorn app.main:app --app-dir backend --reload
```

다른 터미널에서:

```bash
source .venv/bin/activate
API_BASE_URL=http://localhost:8000/api/v1 streamlit run frontend/app.py
```

로컬 API에서 Docker PostgreSQL을 사용할 때 `.env`의 DB host를 `postgres`에서 `localhost`로 변경해야 합니다.

## 테스트 및 품질 검사

```bash
pytest
ruff check .
ruff format --check .
docker compose config
```

Health test는 외부 LLM과 실행 중인 DB를 요구하지 않습니다.

PostgreSQL migration 통합 테스트는 이름이 `_test`로 끝나는 전용 DB만 허용합니다.

```bash
TEST_DATABASE_URL=postgresql+psycopg://adpilot:adpilot@localhost:5432/adpilot_test \
DATABASE_URL=postgresql+psycopg://adpilot:adpilot@localhost:5432/adpilot_test \
pytest -m integration
```

## Campaign API

모든 캠페인은 `DRAFT`로 생성되며 승인 API를 거쳐야 활성화할 수 있습니다. 금액은 원화 최소 단위 정수로 전달합니다.

```bash
curl -X POST http://localhost:8000/api/v1/campaigns \
  -H 'Content-Type: application/json' \
  -d '{
    "name": "신규 쇼핑몰 전환 캠페인",
    "objective": "구매 전환 증대",
    "total_budget_krw": 3000000,
    "daily_budget_krw": 100000,
    "start_date": "2026-11-10",
    "end_date": "2026-12-09",
    "channels": ["mobile", "display"],
    "targeting": {"country": "KR", "device": ["mobile"]}
  }'
```

```bash
# 목록/필터/페이지네이션
curl 'http://localhost:8000/api/v1/campaigns?status=DRAFT&offset=0&limit=20'

# 상세와 수정
curl http://localhost:8000/api/v1/campaigns/{campaign_id}
curl -X PATCH http://localhost:8000/api/v1/campaigns/{campaign_id} \
  -H 'Content-Type: application/json' -d '{"daily_budget_krw":150000}'

# 승인 후 활성화
curl -X POST http://localhost:8000/api/v1/campaigns/{campaign_id}/approve
curl -X PATCH http://localhost:8000/api/v1/campaigns/{campaign_id}/status \
  -H 'Content-Type: application/json' -d '{"status":"ACTIVE"}'

# soft delete: 상태를 INACTIVE로 변경
curl -X DELETE http://localhost:8000/api/v1/campaigns/{campaign_id}
```

상태 전이는 다음과 같습니다.

```text
DRAFT --approve--> APPROVED --> ACTIVE <--> PAUSED
  |                    |          |           |
  └--------------------┴----------┴-----------┴--> INACTIVE
```

승인된 캠페인의 설정을 수정하면 기존 승인이 무효화되어 `DRAFT`로 돌아갑니다. `ACTIVE`, `PAUSED`, `INACTIVE` 캠페인의 설정 수정은 `409 Conflict`로 차단됩니다.

## Streamlit Campaign Admin

`http://localhost:8501`에서 다음 화면을 제공합니다.

| 화면 | 연결 API | 기능 |
|---|---|---|
| Dashboard | `GET /health`, `GET /campaigns` | Backend 상태와 전체·상태별 캠페인 수 |
| Performance Dashboard | `GET /analytics/*` | dataset/기간/Campaign 필터, KPI, 추세, 비교, anomaly |
| Performance Analyst | `POST /analyst/questions` | 자연어 plan, facts/hypotheses/recommendations/evidence |
| Campaign List | `GET /campaigns` | 상태 필터, 페이지네이션, 상세 이동 |
| Campaign Create | `POST /campaigns` | 필수값·예산·기간·채널·타게팅 입력 |
| Campaign Detail / Edit | `GET/PATCH /campaigns/{id}` | 상세 조회와 허용 상태의 설정 수정 |
| Approval / Status | approve/status/delete API | 승인, 활성화, 일시정지, 재활성화, 확인형 비활성화 |

API 오류는 404, 409, 422, 연결 실패, timeout과 예상하지 못한 응답으로 구분합니다. UI 검증은 입력 편의를 위한 보조 수단이며 Backend 검증이 최종 기준입니다. Dashboard의 상태 집계는 목록 응답의 `total`만 사용하도록 각 요청을 `limit=1`로 제한합니다.

Phase 0–4의 실제 실행 화면과 검증 설명은 [Portfolio Evidence](docs/portfolio-evidence.md)에서 확인할 수 있습니다.

## AI Campaign Setup API

기본 `AI_PROVIDER=mock`은 외부 호출이 없는 결정론적 개발용 extractor입니다. Mock 결과는 실제 LLM 정확도가 아닙니다. 생성·보완은 `campaign_drafts`와 `agent_runs`만 기록하며 Campaign은 사용자가 save를 호출할 때만 기존 Campaign Service를 통해 `DRAFT`로 만들어집니다.

```bash
curl -X POST http://localhost:8000/api/v1/ai/campaign-drafts/generate \
  -H 'Content-Type: application/json' \
  -d '{"prompt":"캠페인명: 겨울 설치; 목표: 신규 앱 설치; 총예산: 300만원"}'

curl -X POST http://localhost:8000/api/v1/ai/campaign-drafts/{draft_id}/refine \
  -H 'Content-Type: application/json' \
  -d '{"draft_updates":{"daily_budget_krw":100000,"start_date":"2026-12-01","end_date":"2026-12-31","channels":["mobile"],"targeting":{}}}'

curl http://localhost:8000/api/v1/ai/campaign-drafts/{draft_id}
curl -X POST http://localhost:8000/api/v1/ai/campaign-drafts/{draft_id}/save
```

`READY`가 아닌 초안 저장과 저장 완료 초안의 보완은 `409`로 차단됩니다. 동일 draft save 재시도는 새 Campaign을 만들지 않고 연결된 ID를 반환합니다. 실제 OpenAI adapter는 구현되어 있지만 `AI_PROVIDER=openai`, API key, `AI_REAL_LLM_OPT_IN=true`가 모두 없으면 호출할 수 없습니다.

`refine`에 `draft_updates`만 전달하면 LangGraph가 provider 추출을 명시적으로 건너뛰고 기존 초안과 병합한 뒤 누락·예산·날짜 validation을 그대로 실행합니다. 이 실행은 `not_used` mode, retry 0, token usage 없음으로 기록됩니다. 추가 자연어가 있으면 기존처럼 provider를 호출합니다. Provider 실패 시 이전 초안 값과 실제 누락 필드를 보존하지만 상태는 `PROVIDER_ERROR`로 유지하므로, 실패 전 READY 초안을 자동 저장 가능 상태로 되돌리지는 않습니다.

동일 READY draft의 동시 save는 PostgreSQL `FOR UPDATE`와 단일 transaction으로 직렬화됩니다. 전용 PostgreSQL 통합 테스트에서 두 독립 Session이 동일 Campaign ID를 받고 Campaign 행은 하나만 생성되며, commit 실패 시 고아 Campaign이나 잘못된 draft 연결이 남지 않음을 검증합니다. 이는 AI draft save에 한정된 보장으로 Campaign 전체 optimistic concurrency는 포함하지 않습니다.

Mock golden dataset 실행:

```bash
PYTHONPATH=backend python evaluations/run_campaign_setup_golden.py
```

## Advertising Analytics

기본 generator는 seed `20261107`, schema `analytics-v1`, 2026-09-01부터 70일, Campaign 6개와 일별 성과 420행을 재현합니다. 같은 이름은 기본적으로 `409` 성격의 conflict로 중단하며, 교체하려면 출력된 정확한 dataset ID를 `--replace-dataset-id`로 전달해야 합니다. 이때 generator가 소유한 Campaign·metric·truth만 교체하고 기존 개발 Campaign은 보존합니다.

```bash
PYTHONPATH=backend python scripts/seed/generate_synthetic_analytics.py
PYTHONPATH=backend python evaluations/run_anomaly_evaluation.py \
  --dataset-run-id 4f145f26-ecd7-57ad-bfae-284af05dc3e4
```

분석 API는 dataset ID를 필수로 받고 선택적으로 기간과 Campaign을 필터링합니다.

```bash
curl 'http://localhost:8000/api/v1/analytics/datasets'
curl 'http://localhost:8000/api/v1/analytics/summary?dataset_run_id={dataset_id}'
curl 'http://localhost:8000/api/v1/analytics/timeseries?dataset_run_id={dataset_id}'
curl 'http://localhost:8000/api/v1/analytics/campaigns?dataset_run_id={dataset_id}'
curl 'http://localhost:8000/api/v1/analytics/anomalies?dataset_run_id={dataset_id}'
```

KPI는 원시 합계를 먼저 더한 뒤 `CTR=clicks/impressions`, `CVR=conversions/clicks`, `CPM=spend/impressions×1000`, `CPC=spend/clicks`, `CPA=spend/conversions`, `ROAS=revenue/spend`로 계산합니다. 분모가 0이면 `0`을 만들지 않고 `null`을 반환합니다. 기간은 양 끝 날짜를 포함하며 최대 366일입니다.

`rules-v1`은 `(dataset_run_id, campaign_id)`별로 격리한 정확한 이전 7개 calendar day를 baseline으로 사용합니다. 같은 Campaign UUID가 다른 합성 dataset에 있어도 baseline을 공유하지 않습니다. CTR 60% 이하, CVR 50% 이하, spend 180% 이상, impressions 50% 이하를 각각 탐지하되 최소 노출/클릭과 0 baseline guard를 적용합니다. 기본 합성 truth 4건에 대한 실제 회귀 실행 결과는 TP 4, FP 0, FN 0, precision/recall/F1 1.0입니다. 이는 의도적으로 만든 합성 데이터 회귀 결과이며 실제 광고 운영 정확도를 의미하지 않습니다.

Performance Dashboard는 KPI를 세 행으로 나눠 큰 KRW 합계가 잘리지 않게 표시하고, Spend/Revenue는 원화 정수, CPM/CPC/CPA는 소수점 둘째 자리까지 표시합니다. 일별 추세는 Impressions, Clicks/Conversions, Spend/Revenue, CTR/CVR 네 그래프로 분리해 단위와 스케일을 구분합니다. Frontend는 직접 `pandas`를 사용하지 않고 Streamlit의 chart data contract에 list-of-records를 전달합니다.

## AI Performance Analyst

Analyst API는 자연어 질문과 dataset ID, 선택적 Campaign·기간 context만 받습니다. raw SQL 필드는 Pydantic에서 거부합니다. Mock Provider는 SQL이 아니라 구조화 `AnalysisPlan`만 만들며, Backend compiler가 생성한 named-parameter SQL을 sqlglot AST validator가 다시 검사합니다.

```text
question → AnalysisPlan → deterministic compiler → AST validator
         → PostgreSQL read-only executor → raw totals/KPI
         → facts / hypotheses / recommendations / evidence
```

```bash
curl -X POST http://localhost:8000/api/v1/analyst/questions \
  -H 'Content-Type: application/json' \
  -d '{
    "dataset_run_id":"4f145f26-ecd7-57ad-bfae-284af05dc3e4",
    "question":"ROAS 상위 3개 Campaign을 보여 주세요.",
    "start_date":"2026-09-01",
    "end_date":"2026-11-09"
  }'
```

지원 질문은 전체/특정 Campaign KPI 요약, Campaign 비교, KPI 상·하위 순위, 두 기간 비교, 일별 추세와 detector 기반 anomaly 사실 조회입니다. 모호한 순위 metric이나 비교 기간은 추측하지 않고 `NEEDS_CLARIFICATION`을 반환합니다.

모든 SQL은 `daily_ad_metrics`와 `campaigns`의 허용 column/`SUM`만 사용하며 dataset 범위와 named parameter, row limit을 강제합니다. DML/DDL, multi-statement/comment, wildcard, locking, system catalog, draft/run table, `anomaly_truth_labels`, 파일/network/지연 function은 차단합니다. PostgreSQL transaction은 read-only이며 기본 statement timeout은 2.5초, 결과 기본 limit은 100, 절대 최대는 500입니다. 초과는 `truncated=true`로 표시합니다.

수치 `facts`는 raw totals와 Phase 3 KPI 함수에서만 생성되고 `evidence`의 dataset/Campaign/기간/metric/query fingerprint/근거 값에 연결됩니다. 원인은 “확인 필요”인 `hypotheses`, 조치는 자동 적용되지 않는 `recommendations`로 분리됩니다.

```bash
PYTHONPATH=backend python evaluations/run_analyst_golden.py
PYTHONPATH=backend python evaluations/run_sql_safety_evaluation.py
```

Mock Analyst 결과 22/22와 SQL safety corpus 40/40은 결정론적 회귀 결과입니다. 실제 LLM 정확도, token, 비용과 실제 광고 운영 성능을 의미하지 않습니다.

## 환경 변수

`.env.example`을 `.env`로 복사해 사용합니다. 저장소에 실제 비밀번호나 API key를 커밋하지 않습니다. 예제 계정은 로컬 개발 전용이며 운영 환경에서 사용할 수 없습니다.

| 변수 | 용도 | 기본/예제 |
|---|---|---|
| `APP_ENV` | 실행 환경 표시 | `local` |
| `DATABASE_URL` | SQLAlchemy 연결 URL | PostgreSQL 개발 DB |
| `API_BASE_URL` | Streamlit이 호출할 API | Compose 내부 backend URL |
| `POSTGRES_*` | 로컬 DB 초기화 | 개발 전용 값 |
| `AI_PROVIDER` | extractor 선택 | `mock` |
| `AI_PROVIDER_TIMEOUT_SECONDS` | provider 호출 제한 시간 | `10` |
| `AI_PROVIDER_MAX_RETRIES` | transient 오류 재시도(최대 2) | `2` |
| `AI_REAL_LLM_OPT_IN` | 실제 adapter 호출 명시 동의 | `false` |
| `OPENAI_API_KEY`, `OPENAI_MODEL` | OpenAI adapter 설정 | key 없음 / `gpt-4.1-mini` |
| `ANALYST_PROVIDER` | Analyst planning provider | `mock` |
| `ANALYST_PROVIDER_TIMEOUT_SECONDS` | plan provider 제한 시간 | `10` |
| `ANALYST_PROVIDER_MAX_RETRIES` | plan transient retry(최대 2) | `2` |
| `ANALYST_STATEMENT_TIMEOUT_MS` | PostgreSQL statement timeout | `2500` |
| `ANALYST_ABSOLUTE_MAX_ROWS` | SQL 결과 절대 상한 | `500` |

## 개발 현황

- [x] Phase 0: 프로젝트 구조, 실행 환경, health API, 기본 UI, 테스트, 문서
- [x] Phase 1: Campaign DB 모델, migration, CRUD, 상태 전이 및 API 테스트
- [x] Phase 1.5: Streamlit Campaign Administration UI와 API client 테스트
- [x] Phase 2: AI Campaign Setup Agent, 명시적 DRAFT 저장과 별도 승인 흐름
- [x] Phase 2.1: 구조화 refine provider skip, 실패 초안 보존, PostgreSQL 동시 save 검증
- [x] Phase 3: 합성 광고 데이터, KPI API, Performance Dashboard, 규칙 기반 이상 탐지
- [x] Phase 4: 구조화 plan, 안전한 read-only SQL, 근거 기반 Performance Analyst
- [ ] Phase 5: 평가, 신뢰성, 관측성, 부하 테스트
- [ ] Phase 6: 고급 Agent (MVP 완료 후 선택)

기능 범위와 완료 조건은 [roadmap](docs/roadmap.md)과 [backlog](docs/backlog.md)에 유지합니다.
