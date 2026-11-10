# 로컬 부하 실험

Phase 1-5에서 Docker Compose 애플리케이션의 HTTP 및 비동기 처리 경로를 측정한다.
AWS Source/Target 실험은 [실험 계획](../docs/03-experiment-plan.md)에 따라 별도로 수행한다.

## 실행

저장소 루트에서 Python 3과 Docker Compose v2가 있는 Linux 또는 Ubuntu WSL에서 실행한다.
부하 실행기는 PostgreSQL과 LocalStack을 별도 Compose 프로젝트에 띄우고 임시 키를 생성한다.
Catalog, Order, POS에는 로컬 포트 18181, 18182, 18184를 사용하고 Worker 포트는 컨테이너 내부에서만 연다.
정상 종료 및 오류 시 실행기가 생성한 컨테이너와 PostgreSQL 볼륨을 정리한다.

```bash
# 네 가지 기본 시나리오 및 Worker 비교 세 가지
python3 experiments/k6/run.py --suite

# 단독 실행
DURATION_SECONDS=20 RATE_A=12 ORDER_PERCENT_A=50 \
  python3 experiments/k6/run.py --scenario single-spike --workers 2 --pos-delay-ms 400

# 로컬 이미지 및 동일 이미지의 Source 런타임 계약 검증
python3 experiments/k6/verify_images.py experiments/k6/runs/ecs-local.json
```

기본 출력은 Git에서 제외하는 `experiments/k6/runs/`에 저장한다. `--output`에는
새 디렉터리를 지정한다. 리뷰 후 공유할 결과만 `experiments/results/`에 보관한다.

| 시나리오 | A/B/C 기본 목표 req/s | 부하 |
| --- | ---: | --- |
| `idle` | 0 / 0 / 0 | k6 대기 VU 1개가 시간 창을 유지한다. HTTP 비즈니스 요청은 0건이다. |
| `normal` | 2 / 2 / 2 | 메뉴 조회와 주문 생성 혼합 |
| `single-spike` | 10 / 2 / 2 | A만 증량하고 B/C의 기본 요청률 유지 |
| `all-spike` | 6 / 6 / 6 | 세 브랜드 동시 증량 |

- `DURATION_SECONDS` 기본 12초, `RATE_A/B/C`는 브랜드별 요청률, `ORDER_PERCENT_A/B/C`는
  브랜드별 주문 목표 비중으로 기본 35%다. 일정한 반복 패턴을 사용하며 실제 비중은 원시 결과에서 확인한다.
- `VUS_PER_BRAND` 기본 4는 활성 브랜드별 고정 사전 할당 상한이다. k6는 열린 부하 모델로
  요청을 스케줄한다. VU는 실행 슬롯이므로 실제 동시 HTTP 요청 수와 다르다. VU가 부족하면
  `dropped_iterations`가 발생한다. [k6 실행기 설명](https://grafana.com/docs/k6/latest/using-k6/scenarios/executors/constant-arrival-rate/)
- `SAMPLE_SECONDS` 기본 4초, `DRAIN_SECONDS` 기본 100초다. 각 실행 전 브랜드별 Catalog 및
  Order 읽기를 한 차례 워밍업하고, 실행 후 주문·Outbox·처리 원장·POS 수락 수와 큐 잔여를 대조한다.
- Worker 비교는 같은 A 집중 부하에서 POS 지연 0/400ms와 Worker 1/2개를 교차한다.
  POS 지연은 최초 전달에 적용한다. 기본 시나리오와 같은 데이터·인증·요청 혼합을 사용한다.

## 결과 파일과 해석

| 파일 | 내용 |
| --- | --- |
| `environment.json`, `conditions.json` | 로컬 환경, 실행 설정, 부하 및 관측 시각 |
| `k6.json.gz`, `summary.json` | k6 원시 포인트, 브랜드·작업별 요청 건수/RPS/p50/p95/p99/실패율, 주문 성공률과 비동기 요약 |
| `samples.jsonl` | 서비스별 Docker CPU·메모리, PostgreSQL 세션·Outbox, SQS visible/in-flight·DLQ 스냅샷 |
| `orders.json`, `sqs-age.jsonl` | 개별 주문의 DB 처리 시각과 지연, SQS 발행→수신 나이 및 수신→ACK 시각 차이 |

HTTP RPS는 수집된 요청 수를 설정 부하 시간으로 나눈다. p50/p95/p99는 원시 포인트의
nearest rank이며, 정상 응답은 Catalog 200과 주문 최초 생성 201로 정의한다.
Worker의 부하 구간 처리량은 k6 컨테이너 호출 전후 벽시계 창에서 처리 원장에 기록된 건수를 초로 나눈다.
컨테이너 기동 및 결과 압축 시간이 그 창에 포함될 수 있다. 주문 지연은 DB의
`created_at`부터 처리 트랜잭션 안에서 찍은 `processed_at`까지이며 커밋 및 HTTP 조회 시각과 차이가 있다.
SQS age는 브로커의 `SentTimestamp`와 Worker 수신 시각의 차이다. ACK가 성공해 로그가 남은
표본만 집계한다. 재전달 시 최초 발행부터의 시간이 누적될 수 있다.

Docker·PostgreSQL·SQS 조회는 각각 시작 시각과 소요 시간을 남긴다. 기본 4초 간격은 목표이며
소요 시간과 프로세스 스케줄링에 따라 달라진다. 같은 행의 관측치를 정밀 동기화한 것으로 해석하지 않는다.
SQS 깊이는 근사치이며, DB 세션 표본은 Hikari 대기열이나 순간 잠금의 전수 기록을 대신할 수 없다.
유휴 창에도 Compose 헬스체크, Publisher/Worker 폴링, 수집 도구는 실행된다.

공유 결과는 [Phase 1-5 로컬 결과](results/local-phase-1-5/README.md)에 기록한다.
