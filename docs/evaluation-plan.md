# AI Evaluation Plan

## 평가 원칙

기능 unit test와 AI 품질 평가는 분리한다. 평가 입력, 기대 결과, 판정 코드와 실행 환경을 version control하며 Mock 결과와 실제 LLM 결과를 별도 집계한다. 수치가 생성되는 경로를 추적하고 실행하지 않은 결과는 보고하지 않는다.

## 지표와 판정 기준

| 기능 | 지표 | 판정 방법 |
|---|---|---|
| Campaign Setup | field exact/normalized match | golden request별 필드 비교 |
| Campaign Setup | 필수값 충족률 | required field non-null 비율이 아닌 요구사항 추출 정답과 비교 |
| Validator | invalid budget/date 차단률 | labeled invalid case 중 reject 비율 |
| Structured output | parse/validation 성공률 | 전체 실행 중 schema 통과 비율 |
| Safe SQL | 잘못된 SQL 차단률 | malicious/DDL/DML/cross-table corpus 차단 비율 |
| Analyst | 질문 정답률 | expected campaign/date/direction/metric과 구조화 결과 비교 |
| Anomaly | precision/recall/F1 | 생성 시 저장한 truth label과 detector 결과 비교 |
| Reliability | 실패율/timeout/retry | 단계별 outcome counter와 failure injection |
| Performance | p50/p95 latency | API/agent/tool 단계별 monotonic timer |
| Cost | token/cost per request | provider usage metadata와 가격 snapshot |

## 데이터셋 설계

- `campaign_setup`: `evaluations/datasets/campaign_setup_golden.json`의 22개 정상, 누락, 모호한 금액·기간, 잘못된 예산·기간, 다중 채널, 한국어 단위, 경계값, prompt injection 입력
- `sql_safety`: SELECT/CTE 정상과 DML, DDL, comment bypass, multi-statement, forbidden table, excessive result
- `analyst_questions`: 캠페인, 기간, metric, 비교 방향이 명시된 기대 결과
- `anomalies`: seed와 주입 구간/유형/severity truth label을 함께 저장

합성 데이터 generator seed, schema version, metric definition version을 기록한다. 실제 개인정보와 광고 계정 데이터는 사용하지 않는다.

## 성능 측정

API latency와 agent 단계별 latency를 분리하고 warm-up 뒤 동일 환경에서 반복 측정한다. DB query timeout과 LLM timeout을 독립 기록한다. p50/p95, error rate, concurrency, 환경/commit을 결과에 포함한다. Phase 5에서 load-test 도구를 선택한다.

## 실패 사례 기록

실패 case는 입력, 기대값, 실제 구조화 결과, 실패 단계, 오류 분류, provider/model/version, retry 수, latency를 저장한다. prompt 원문에 비밀이나 개인정보가 있으면 저장 전에 제거한다. regression dataset 승격 여부와 수정 commit을 연결한다.

## Phase별 실행

Phase 1은 deterministic domain/API test baseline을 만든다. Phase 2는 Mock provider로 campaign golden set을 먼저 통과시키고 실제 provider 평가는 별도 opt-in으로 실행한다. Phase 3은 anomaly truth label로 metric을 계산한다. Phase 4는 SQL safety와 analyst accuracy를 추가하며, Phase 5에서 결과 보고와 CI threshold를 확정한다.

Phase 2 runner는 기대 상태, 일부 기대 필드, 누락 필드, 오류 유형을 자동 비교한다. Mock 결과는 규칙 기반 extractor의 회귀 안정성만 나타내며 실제 LLM field accuracy로 환산하지 않는다. 실제 LLM 평가는 비용·provider/model/version을 기록하는 별도 opt-in 실행으로만 수행하고 기본 test나 CI에는 포함하지 않는다.

Phase 2.1 신뢰성 회귀에는 구조화 수정의 provider 미호출, provider 실패 시 기존 값과 실제 누락 보존, 전용 PostgreSQL의 동시 save 행 잠금, transaction 실패 rollback을 포함한다. Mock golden dataset 22건은 변경 후에도 별도로 실행한다. 실제 LLM 평가는 Phase 2.1에서도 실행하지 않았으며, Mock 및 실패 주입 결과를 실제 provider 품질로 해석하지 않는다.
