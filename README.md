# AdPilot AI

AdPilot AI는 자연어 캠페인 설정, 광고 성과 분석, 이상 탐지를 안전한 승인 흐름과 결합하는 AI 광고 운영 플랫폼입니다. 실제 광고 송출이나 광고 계정 변경이 아닌 합성 데이터 기반 포트폴리오 프로젝트이며, AI Backend/Agent Platform 설계 역량을 검증하는 것이 목적입니다.

현재 상태는 **Phase 1.5 — Campaign Administration UI 완료**입니다. Campaign CRUD, 결정론적 검증, 승인과 상태 전이, PostgreSQL migration 및 Streamlit 관리자 화면을 제공합니다. Campaign Agent와 Performance Analyst는 아직 구현하지 않았습니다.

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
- LangGraph 및 LLM provider abstraction은 Phase 2에서 도입

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
| Campaign List | `GET /campaigns` | 상태 필터, 페이지네이션, 상세 이동 |
| Campaign Create | `POST /campaigns` | 필수값·예산·기간·채널·타게팅 입력 |
| Campaign Detail / Edit | `GET/PATCH /campaigns/{id}` | 상세 조회와 허용 상태의 설정 수정 |
| Approval / Status | approve/status/delete API | 승인, 활성화, 일시정지, 재활성화, 확인형 비활성화 |

API 오류는 404, 409, 422, 연결 실패, timeout과 예상하지 못한 응답으로 구분합니다. UI 검증은 입력 편의를 위한 보조 수단이며 Backend 검증이 최종 기준입니다. Dashboard의 상태 집계는 목록 응답의 `total`만 사용하도록 각 요청을 `limit=1`로 제한합니다.

Phase 0–1.5의 실제 실행 화면과 검증 설명은 [Portfolio Evidence](docs/portfolio-evidence.md)에서 확인할 수 있습니다.

## 환경 변수

`.env.example`을 `.env`로 복사해 사용합니다. 저장소에 실제 비밀번호나 API key를 커밋하지 않습니다. 예제 계정은 로컬 개발 전용이며 운영 환경에서 사용할 수 없습니다.

| 변수 | 용도 | 기본/예제 |
|---|---|---|
| `APP_ENV` | 실행 환경 표시 | `local` |
| `DATABASE_URL` | SQLAlchemy 연결 URL | PostgreSQL 개발 DB |
| `API_BASE_URL` | Streamlit이 호출할 API | Compose 내부 backend URL |
| `POSTGRES_*` | 로컬 DB 초기화 | 개발 전용 값 |

## 개발 현황

- [x] Phase 0: 프로젝트 구조, 실행 환경, health API, 기본 UI, 테스트, 문서
- [x] Phase 1: Campaign DB 모델, migration, CRUD, 상태 전이 및 API 테스트
- [x] Phase 1.5: Streamlit Campaign Administration UI와 API client 테스트
- [ ] Phase 2: AI Campaign Setup Agent와 승인 흐름
- [ ] Phase 3: 합성 광고 데이터, KPI, dashboard, 이상 탐지
- [ ] Phase 4: 안전한 AI Performance Analyst
- [ ] Phase 5: 평가, 신뢰성, 관측성, 부하 테스트
- [ ] Phase 6: 고급 Agent (MVP 완료 후 선택)

기능 범위와 완료 조건은 [roadmap](docs/roadmap.md)과 [backlog](docs/backlog.md)에 유지합니다.
