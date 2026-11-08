# Phase 0–3 Portfolio Evidence

이 문서는 실제 Docker Compose 환경에서 FastAPI, PostgreSQL, Streamlit을 실행하고 Playwright로 캡처한 포트폴리오 증빙입니다. 캡처 데이터는 `adpilot-portfolio`라는 격리된 Compose 프로젝트의 전용 PostgreSQL 볼륨에 생성한 합성 캠페인 24개입니다. 기존 개발 DB 데이터는 사용하거나 변경하지 않았습니다.

## Phase 0 — Health와 실행 환경

![Dashboard Backend health](assets/screenshots/01-dashboard.png)

- 화면: Dashboard
- 구현 기능: FastAPI Health 연결 상태와 전체·상태별 캠페인 KPI
- 검증 내용: Streamlit이 REST API를 통해 `AdPilot AI v0.1.0` Backend에 연결되고 상태별 `total`을 표시함
- 데이터: 합성 테스트 데이터 24개

## Phase 1 — Campaign API와 Validation

![Swagger Campaign API](assets/screenshots/05-swagger-api.png)

- 화면: FastAPI Swagger Campaign API
- 구현 기능: Campaign CRUD, 승인, 상태 변경, 비활성화 endpoint와 목록 조회 실행
- 검증 내용: `GET /api/v1/campaigns?offset=0&limit=2`가 HTTP 200과 실제 합성 응답을 반환함
- 데이터: 합성 테스트 데이터

![Backend validation error](assets/screenshots/06-validation-error.png)

- 화면: Swagger Validation Error
- 구현 기능: 일예산이 총예산을 초과한 요청의 결정론적 검증
- 검증 내용: `POST /api/v1/campaigns`가 HTTP 422와 `business_rule_violation`을 반환함
- 데이터: 저장되지 않은 합성 오류 요청

## Phase 1.5 — Campaign Administration UI

![Campaign list](assets/screenshots/02-campaign-list.png)

- 화면: Campaign List
- 구현 기능: 상태 필터, 20개 페이지 크기, 24개 결과의 2페이지 탐색, 상세 이동
- 검증 내용: 격리된 PostgreSQL의 상태별 합성 캠페인이 REST API를 통해 표에 렌더링됨
- 데이터: 합성 테스트 데이터 24개

![Campaign create](assets/screenshots/03-campaign-create.png)

- 화면: Campaign Create
- 구현 기능: 필수값, 예산, 기간, 채널, targeting JSON 입력 폼
- 검증 내용: 새 캠페인은 DRAFT로 생성되고 UI 보조 검증 이후 Backend가 최종 검증하는 입력 경계를 표시함
- 데이터: 폼 기본값만 표시하며 새 레코드는 생성하지 않음

![Campaign detail and status](assets/screenshots/04-campaign-detail.png)

- 화면: Campaign Detail / Edit
- 구현 기능: APPROVED 캠페인 조회·수정, 승인 무효화 안내, 활성화와 확인형 비활성화
- 검증 내용: 현재 상태에 허용된 동작만 노출하고 변경은 FastAPI 상태 전이 규칙으로 최종 검증함
- 데이터: 합성 테스트 캠페인

## 재현 환경

```bash
docker compose -p adpilot-portfolio up -d postgres
docker compose -p adpilot-portfolio run --rm backend alembic upgrade head
docker compose -p adpilot-portfolio up -d --build backend frontend
```

- 캡처 해상도: 가로 1440px 기준
- Streamlit: `http://localhost:8501`
- Swagger: `http://localhost:8000/docs`
- API Key, 실제 비밀번호, 개인정보 및 운영 광고 데이터는 포함하지 않음

## Phase 2 — AI Campaign Setup Agent

Phase 2 이미지는 `adpilot-phase2` 격리 Compose 프로젝트의 전용 PostgreSQL 볼륨과 결정론적 Mock Provider로 캡처했습니다. Mock 결과는 실제 LLM 정확도 증빙이 아닙니다.

- 자동 테스트: 53 passed
- PostgreSQL migration 전용 검증: 1 passed (upgrade/downgrade/upgrade)
- Mock golden dataset: 22/22 passed
- 실제 LLM 호출 및 정확도 평가: 미실행

![Natural language campaign input](assets/screenshots/phase-2/01-natural-language-input.png)

- 화면: AI Campaign Setup 자연어 입력
- 구현 기능: 자연어 캠페인 요구 접수와 AI 초안 생성 시작
- 검증 내용: Streamlit이 Agent나 DB를 직접 호출하지 않고 FastAPI REST endpoint만 사용함
- 데이터: 합성 캠페인 요청, Mock Provider

![Missing fields and clarification](assets/screenshots/phase-2/02-needs-clarification.png)

- 화면: 누락 정보와 추가 질문
- 구현 기능: `NEEDS_CLARIFICATION`, 누락 필드, 필드별 보완 질문, Mock mode 표시
- 검증 내용: 월/총예산만으로 일예산·날짜를 추측하지 않고 명시 입력을 요구함
- 데이터: 합성 캠페인 요청, Mock Provider

![Ready editable preview](assets/screenshots/phase-2/03-ready-preview.png)

- 화면: READY 초안과 편집 가능한 미리보기
- 구현 기능: 보완 입력 병합, Pydantic/도메인 검증, 구조화 필드와 편집 폼
- 검증 내용: 기존 값 유지, 명시 필드 보완 후 `READY`; Campaign은 아직 생성되지 않음
- 데이터: 합성 캠페인 요청·타게팅, Mock Provider

![Saved draft campaign detail](assets/screenshots/phase-2/04-draft-saved-detail.png)

- 화면: DRAFT 저장 완료와 Campaign Detail 연결
- 구현 기능: 사용자 확인 후 기존 Campaign Service로 저장하고 상세 화면 이동
- 검증 내용: 저장된 Campaign 상태가 `DRAFT`이며 승인 동작은 별도 API/UI에 유지됨
- 데이터: 합성 캠페인, Mock Provider에서 생성한 초안

![Deterministic validation block](assets/screenshots/phase-2/05-validation-blocked.png)

- 화면: 예산 검증 차단
- 구현 기능: `VALIDATION_FAILED`와 안전한 결정론적 오류 표시
- 검증 내용: 일예산이 총예산을 초과한 완성 초안을 Campaign domain validator가 차단함
- 데이터: 저장되지 않은 합성 오류 요청, Mock Provider

![Provider schema error](assets/screenshots/phase-2/06-provider-error.png)

- 화면: Provider structured output 실패
- 구현 기능: `PROVIDER_ERROR`, 안전한 `provider_schema_mismatch` 오류 코드, 저장 차단
- 검증 내용: 잘못된 JSON을 Campaign으로 저장하거나 tool/DB 작업으로 연결하지 않음
- 데이터: 합성 오류 입력, Mock Provider

## Phase 3 — Synthetic Advertising Analytics

Phase 3 이미지는 기존 개발 DB와 분리한 `adpilot-phase3` Compose 프로젝트, 전용 `adpilot_phase3_demo` PostgreSQL DB와 volume에서 Playwright로 캡처했습니다. dataset은 seed `20261107`, schema `analytics-v1`, 70일, Campaign 6개, 일별 metric 420행과 anomaly truth 4건으로 구성됩니다.

![Performance Dashboard](assets/screenshots/phase-3/01-performance-dashboard.png)

- 화면: Performance Dashboard 요약
- 구현 기능: dataset·기간·Campaign 필터, 원시 합계와 CTR/CVR/CPM/CPC/CPA/ROAS
- 검증 내용: Streamlit이 FastAPI REST만 호출해 격리 PostgreSQL의 합성 KPI를 렌더링하고 합성 데이터임을 명시함
- 데이터: 고정 seed 합성 테스트 데이터

2026-11-08 안정화에서 KPI를 3개 행으로 재배치하고 Spend/Revenue를 원화 정수로 표시해 큰 값의 잘림을 제거했습니다. 비용형 KPI는 소수점 둘째 자리까지 유지하며 0분모는 `N/A (분모 0)`로 구분합니다.

![Daily performance trends](assets/screenshots/phase-3/02-daily-trends.png)

- 화면: 일별 성과 추세
- 구현 기능: impressions/clicks/conversions, spend/revenue, CTR/CVR 시계열
- 검증 내용: 2026-09-01부터 2026-11-09까지 inclusive 일별 집계와 삽입 anomaly 구간이 실제 API 응답으로 표시됨
- 데이터: 고정 seed 합성 테스트 데이터

2026-11-08 안정화에서 추세를 Impressions, Clicks/Conversions, Spend/Revenue, CTR/CVR 네 그래프로 분리하고 제목·단위·범례를 명시했습니다. Detector baseline은 `(dataset_run_id, campaign_id)` 단위로 격리되며 서로 다른 dataset run의 동일 Campaign UUID가 섞이지 않는 회귀 테스트를 추가했습니다.

![Campaign comparison](assets/screenshots/phase-3/03-campaign-comparison.png)

- 화면: Campaign별 성과 비교
- 구현 기능: 6개 Campaign의 raw totals, CTR, CVR, ROAS 비교
- 검증 내용: 합계를 먼저 집계한 뒤 KPI를 계산하며 Campaign 정렬과 필터 경계를 유지함
- 데이터: 고정 seed 합성 테스트 데이터

![Rule based anomaly detections](assets/screenshots/phase-3/04-anomaly-detections.png)

- 화면: 규칙 기반 Anomaly 탐지
- 구현 기능: CTR_DROP, CVR_DROP, SPEND_SPIKE, IMPRESSION_DROP의 observed/baseline/threshold 표시
- 검증 내용: 제품 API가 truth label을 노출하지 않고 raw metric 기반 `rules-v1` detection 4건만 반환함
- 데이터: 고정 seed 합성 테스트 데이터; truth는 평가 전용 별도 저장

![Analytics Swagger API](assets/screenshots/phase-3/05-analytics-api.png)

- 화면: FastAPI Swagger Analytics API
- 구현 기능: datasets, summary, timeseries, campaigns, anomalies의 read-only endpoint
- 검증 내용: 기존 Campaign·AI Setup 계약을 유지하면서 Phase 3 endpoint와 schema가 OpenAPI에 추가됨
- 데이터: API 문서 화면, 비밀정보 없음

### Anomaly 평가

- 실제 실행 결과: TP 4, FP 0, FN 0, precision 1.000000, recall 1.000000, F1 1.000000
- 검증 방식: detector 결과 key와 별도 truth label key 비교
- 제한: 의도적으로 설계한 합성 회귀 결과이며 실제 광고 운영 정확도나 LLM 품질을 의미하지 않음
- 실제 LLM 호출: 없음

## Phase 4 — AI Performance Analyst

Phase 4 이미지는 기존 개발 DB와 분리한 `adpilot-phase4` Compose 프로젝트, 전용 `adpilot_phase4_demo` PostgreSQL DB와 고정 seed 합성 dataset에서 실제 Streamlit·FastAPI를 Playwright로 조작해 캡처했습니다. Planner는 결정론적 Mock이며 실제 LLM 정확도 증빙이 아닙니다.

![Performance Analyst input](assets/screenshots/phase-4/01-analyst-input.png)

- 화면: Performance Analyst 입력
- 구현 기능: dataset·Campaign·기간 범위와 자연어 질문 입력, 대표 질문 선택
- 검증 내용: Streamlit은 REST API만 호출하고 Mock planner, 실제 LLM 미사용, 사용자 SQL 입력/실행 미지원 정책을 화면에 명시함
- 데이터: 고정 seed 합성 테스트 데이터

![Normal Analyst result](assets/screenshots/phase-4/02-normal-result.png)

- 화면: ROAS 상위 Campaign 정상 분석 결과
- 구현 기능: 자연어 질문을 구조화 `AnalysisPlan`으로 제한하고 검증 가능한 facts를 evidence ID와 함께 표시
- 검증 내용: `RANK_CAMPAIGNS`, dataset/date scope, limit 3을 결정론적 SQL로 컴파일해 PostgreSQL read-only transaction에서 실행함
- 데이터: 고정 seed 합성 Campaign 6개와 일별 metric 420행

![Hypotheses and recommendations](assets/screenshots/phase-4/03-hypotheses-recommendations.png)

- 화면: Anomaly 분석 결과
- 구현 기능: facts, 확인이 필요한 hypotheses, 자동 실행되지 않는 recommendations를 분리
- 검증 내용: anomaly truth label을 조회하지 않고 raw metric과 기존 `rules-v1` detector로 사실 4건을 계산함
- 데이터: 고정 seed 합성 테스트 데이터

![Expanded evidence](assets/screenshots/phase-4/04-evidence-expanded.png)

- 화면: Evidence와 조회 범위 확장
- 구현 기능: 실행 plan, dataset/date/campaign scope, query fingerprint, row count, provider mode와 usage 표시
- 검증 내용: 응답의 각 fact가 evidence ID를 참조하며 raw SQL이나 credential은 노출하지 않음
- 데이터: 고정 seed 합성 테스트 데이터, Mock planner

![Clarification response](assets/screenshots/phase-4/05-clarification.png)

- 화면: 질문 명확화 요청
- 구현 기능: 순위 metric이 없는 질문을 `NEEDS_CLARIFICATION`으로 반환
- 검증 내용: 불완전한 요구를 추측해 SQL로 실행하지 않고 필요한 KPI를 사용자에게 요청함
- 데이터: 저장되지 않는 합성 질문

![Safety blocked response](assets/screenshots/phase-4/06-safety-blocked.png)

- 화면: 안전 검증 차단
- 구현 기능: SQL 주입형 자연어 질문의 사전 차단과 안전한 오류 코드 표시
- 검증 내용: `guard_question` 단계에서 `unsafe_question`으로 종료되어 compiler, validator, executor에 진입하지 않음
- 데이터: 저장되지 않는 합성 공격 문자열

![Swagger Analyst API](assets/screenshots/phase-4/07-swagger-analyst-api.png)

- 화면: FastAPI Swagger Performance Analyst API
- 구현 기능: `POST /api/v1/analyst/questions` 요청·응답 schema와 실제 HTTP 200 실행 결과
- 검증 내용: API가 raw SQL 필드 없이 `AnalysisPlan`, facts, hypotheses, recommendations, evidence와 실행 metadata를 반환함
- 데이터: 고정 seed 합성 테스트 데이터, Mock planner

### Phase 4 안전성·평가 결과

- Mock Analyst golden dataset: 22/22 passed
- SQL safety corpus: 40/40 passed
- PostgreSQL 전용 검증: read-only write 거부·rollback, 실제 statement timeout, limit+1 truncation, AST 차단 포함
- 하드 제한: 최대 500행, 2.5초 statement timeout, 최대 366일 범위
- 실제 LLM 호출 및 실제 LLM 품질 평가: 미실행
- 실제 광고 데이터 연결·설정 변경·자동 권고 실행: 없음
