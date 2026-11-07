# Phase 0–2 Portfolio Evidence

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
