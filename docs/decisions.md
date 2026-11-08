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

## ADR-011: AI 부분 초안과 저장 계약을 분리

선택: Agent 내부 상태와 `campaign_drafts`에는 누락 값을 허용하는 `PartialCampaignDraft`를 사용하고, 저장 직전에만 모든 필드가 필수인 기존 `CampaignCreate`로 변환한다. LangGraph는 누락 확인과 결정론적 검증 결과에 따라 `READY`, `NEEDS_CLARIFICATION`, `VALIDATION_FAILED`, `PROVIDER_ERROR`를 구분한다.

근거: LLM 추출 결과를 완성된 API 계약으로 가장하면 누락과 추측을 구분할 수 없다. 특히 상대 날짜나 월 예산으로부터 날짜·일예산을 임의 계산하지 않는다.

## ADR-012: AI 실행 저장 범위를 최소화

선택: `campaign_drafts`에는 현재 구조화 초안, 누락 필드, 검증 오류, 상태, provider mode, 저장된 Campaign ID와 시각만 저장한다. `agent_runs`에는 request/draft ID, 실행 상태와 실패 단계, provider/model, retry, latency, 제공된 경우의 token usage, 안전한 오류 코드만 저장한다. 자연어 원문, provider 원문 응답, API key는 DB와 애플리케이션 로그에 저장하지 않는다.

근거: Phase 2의 재개·감사에 필요한 최소 메타데이터를 남기면서 프롬프트와 민감정보의 불필요한 보존을 피한다.

## ADR-013: Provider 경계와 실호출 opt-in

선택: workflow는 작은 Provider Protocol에만 의존한다. 기본 provider는 외부 호출이나 tool 권한이 없는 결정론적 Mock이며, 실제 provider adapter는 구조화 출력만 반환한다. 실제 adapter 선택과 실호출은 provider 환경변수, API key, 별도 `AI_REAL_LLM_OPT_IN=true`가 모두 있어야 한다. Mock golden 평가와 실제 LLM 평가는 별도 명령·지표로 관리하며 Mock 통과율을 LLM 정확도로 표현하지 않는다.

근거: API key 없이 개발·테스트·UI가 재현되어야 하고 특정 SDK가 domain 및 graph에 침투하면 안 된다.

## ADR-014: Provider timeout과 제한된 retry

선택: provider 호출에는 환경설정 가능한 timeout을 적용한다. timeout, rate limit, 5xx 등 명시된 transient failure만 최초 호출 후 최대 2회 재시도하며, schema mismatch, 인증, 잘못된 요청 등 재시도 불가능한 오류는 즉시 `PROVIDER_ERROR`로 종료한다. 각 run에는 실제 retry 횟수와 안전한 오류 코드만 기록한다.

근거: 무제한 retry와 숨은 지연을 막고, 동일 입력을 반복해도 복구되지 않는 오류에 비용을 쓰지 않는다.

## ADR-015: 보완 입력은 명시된 값만 병합

선택: refine은 provider가 새 입력에서 추출한 non-null 필드와 사용자가 편집 폼에서 명시한 값만 기존 초안 위에 덮어쓴다. 언급되지 않은 기존 값은 유지한다. 리스트와 객체도 필드 단위로 전체 교체하며 추측 병합이나 자동 날짜·예산 계산은 하지 않는다. 저장된 초안은 더 이상 보완할 수 없다.

근거: 사용자 의도를 추적 가능하게 만들고 오래된 값의 우발적 삭제 및 LLM 추측을 피한다.

## ADR-016: AI 초안 저장에만 좁은 idempotency 적용

선택: `READY` 초안 저장은 해당 draft 행을 잠그고 기존 `CampaignService.create()`의 검증·생성 경로를 같은 transaction에서 재사용한다. draft에 연결된 Campaign ID가 있으면 이를 그대로 반환한다. 저장 완료 후 refine과 추가 저장에 의한 변경은 차단하되, 동일 save 재시도는 성공한 기존 Campaign을 반환한다.

대안: Campaign 전체에 optimistic concurrency/version을 추가하는 방식은 Phase 2 범위를 넘으므로 구현하지 않고 후속 backlog로 유지한다.

## ADR-017: 구조화 보완과 Provider 실패를 workflow에서 분리

선택: refine의 `additional_input`에 공백이 아닌 텍스트가 있을 때만 provider 추출 노드를 실행한다. `draft_updates`만 있으면 LangGraph 시작 conditional edge가 `skip_provider_extraction`으로 분기하고, 기존 초안과 명시적 수정값을 병합한 뒤 동일한 누락 확인과 결정론적 validation을 수행한다. 이 실행은 provider/model을 `not_used`/`structured-updates-only`, retry를 0, token usage를 `null`로 기록한다.

Provider 실패 시 저장된 기존 초안을 보존하고 실제 초안 기준으로 누락 필드를 다시 계산한다. 상태는 `PROVIDER_ERROR`로 유지하며 안전한 오류 코드와 실패 단계만 기록한다. 이전 초안이 `READY`였더라도 실패한 보완 요청을 무시해 자동으로 저장 가능 상태로 되돌리지 않는다. 사용자는 성공한 refine을 다시 수행해야 하며, 이는 실패한 사용자 의도를 조용히 폐기하지 않기 위한 안전 정책이다.

검증: 전용 PostgreSQL에서 두 독립 Session이 동일 READY draft를 겹쳐 저장하는 테스트를 수행했다. 첫 transaction의 `FOR UPDATE` 잠금 중 두 번째 요청이 대기한 뒤 두 응답이 같은 Campaign ID를 반환하고 Campaign 행이 하나임을 확인했다. commit 실패 주입 시 Campaign과 draft 연결이 함께 rollback되는 것도 확인했다. Campaign 전체 optimistic concurrency는 여전히 범위 밖이다.

## ADR-018: 합성 성과 dataset 소유권과 결정론적 분석 계약

선택: `synthetic_dataset_runs`의 UUID가 하나의 생성 실행과 소유 범위를 식별한다. 합성 Campaign은 nullable `synthetic_dataset_run_id` FK로 소유 run을 명시하며 기존 개발 Campaign은 `NULL`로 격리한다. 일별 원시는 `dataset run × campaign × date` 한 행으로 저장하고, 동일 조합은 unique constraint로 차단한다. dataset 이름도 unique이며 같은 이름의 재실행은 기본적으로 거부한다. 교체는 기존 run의 정확한 ID와 명시적 `--replace-dataset-id`가 모두 일치할 때만 허용하고 해당 run이 소유한 metric, truth, Campaign과 run만 transaction 안에서 교체한다. 전체 Campaign 또는 DB reset은 제공하지 않는다.

생성 설정에는 고정 seed, 시작일, 일수, Campaign 수와 schema version을 기록한다. 같은 seed와 같은 정규화 설정은 UUID와 원시 metric/truth까지 동일하게 생성하며 현재 날짜를 참조하지 않는다. schema version은 `analytics-v1`로 시작하고 계약 변경 시 명시적으로 올린다.

KPI는 원시 합계를 먼저 합산한 뒤 `Decimal`로 계산한다. CTR=`clicks/impressions`, CVR=`conversions/clicks`, CPM=`spend×1000/impressions`, CPC=`spend/clicks`, CPA=`spend/conversions`, ROAS=`revenue/spend`다. 분모가 0이면 파생값은 0이나 무한대가 아니라 `null`이다. API 경계에서 rate와 ROAS는 소수점 6자리, 금액형 KPI는 2자리까지 `ROUND_HALF_UP`으로 반올림하고 원시 정수는 반올림하지 않는다.

규칙 탐지는 Campaign별 현재일을 제외한 정확히 7개 선행 calendar day를 baseline으로 사용한다. 관측이 7개 미만이거나 필요한 분모/baseline이 0이면 해당 규칙은 판정 보류한다. 포함 경계는 CTR 60% 이하, CVR 50% 이하, spend 180% 이상, impressions 50% 이하다. CTR은 현재 impressions 100 이상, CVR은 현재 clicks 20 이상일 때만 평가한다.

`anomaly_truth_labels`는 생성 시 주입한 정답만 저장하고 detector는 이를 읽지 않는다. truth가 없는 `(run, campaign, date, type)` 조합은 평가에서 negative다. detector 결과는 threshold나 version 변경 시 stale 상태를 피하기 위해 저장하지 않고 원시 metric에서 요청 시 계산한다. 평가 runner만 truth와 detector key를 비교하며 precision/recall/F1의 분모가 0이면 `null`로 반환한다.

Phase 4가 재사용할 read-only 계약은 `synthetic_dataset_runs`, `campaigns`의 합성 소유 FK, `daily_ad_metrics` 원시 정수와 공개 analytics 조회 응답이다. truth label은 평가 전용이며 제품 anomaly API나 향후 Analyst의 사실 데이터로 노출하지 않는다. PostgreSQL 단일 저장소를 유지하고 microservice, Kafka, Redis, DuckDB는 도입하지 않는다.

## ADR-019: Anomaly baseline 격리와 Dashboard chart data 최소화

선택: `rules-v1` detector의 그룹 키를 `campaign_id` 단독이 아닌 `(dataset_run_id, campaign_id)`로 사용한다. 동일한 Campaign UUID가 여러 합성 dataset에 존재해도 날짜 맵, 7일 baseline과 detection은 run 경계를 넘지 않는다. 임계값, 최소 표본, 정확한 이전 7 calendar day, truth 비참조 정책은 변경하지 않는다.

Performance Dashboard의 KPI는 3개 행으로 나누고 Spend/Revenue는 원화 정수, 비용형 KPI는 소수점 둘째 자리로 표시한다. 추세는 Impressions, Clicks/Conversions, Spend/Revenue, CTR/CVR 네 그래프로 분리한다. Frontend는 직접 `pandas`를 import하지 않고 list-of-records를 Streamlit chart API에 전달한다.

대안: `pandas`를 frontend optional dependency로 명시하는 방법도 가능하지만 현재 변환은 단순 필드 매핑이라 DataFrame 연산이 필요하지 않다. 직접 사용을 제거하면 공개 dependency가 줄고 Streamlit 내부 dependency 버전에 대한 암묵적 결합도 사라진다. 데이터 변환이 복잡해질 때만 명시적 pandas 도입을 다시 검토한다.
