# 09. 구현 상세 설계 v1 (2026-11-10)

> 상태: **설계 확정안 / 미배포**. 표의 용량과 임계값은 최초 시험 설정이며 실제 성능과 비용을 보증하지 않는다. 변경 시 실험 근거와 ADR을 남긴다.

## 1. 목표와 범위 고정

- **Source:** 가상 브랜드 A/B/C별 독립 ECS Fargate 컴퓨팅. 3개 브랜드 × Catalog API / Order API / Fulfillment Worker = 9개 ECS Service.
- **Target:** 단일 공유 ECS on EC2 클러스터에서 Catalog API / Order API / Worker = 3개 ECS Service, EC2 Auto Scaling Group과 ECS EC2 Capacity Provider 연동.
- **DB:** 하나의 기존 RDS PostgreSQL 데이터베이스 `ordersaas`, 브랜드별 `brand_a`, `brand_b`, `brand_c` 스키마 유지. **DB 데이터 복사 또는 DB 마이그레이션은 실시하지 않음.**
- **SQS:** 브랜드별 Queue 및 DLQ 유지; 공유 Worker가 인증/검증된 브랜드 메시지를 처리. Queue 통합은 필수 범위에서 제외.
- **필수 초기:** Terraform, 구조화 JSON 로그, 요청 처리 시간, k6 원시 결과, AWS 기본 CloudWatch 메트릭, 비용·확장성·테넌트 보안·전환 실험. **관측 도구 선택/대시보드/Trace 구축은 브랜드 A Cutover 이후 6단계로 연기**하며 최종 비교 전 동일 조건으로 재측정.
- **제외:** 실제 결제/POS, 프론트엔드, EKS, AWS 계정 간 이전, EC2 Warm Pool/Bottlerocket(후속 실험 후보).

## 2. 기술 스택

- Java 21 + Spring Boot: Catalog API, Order API, Fulfillment Worker, 간단한 모의 POS.
- PostgreSQL: JDBC/JPA 등 구현 시 최소 복잡도를 우선하되, 실제 권한 테스트를 필수로 한다.
- k6: 브랜드별 합성 부하, 응답 지연 및 실패 측정.
- Terraform: Source와 Target을 별도 모듈/환경으로 관리하되 **RDS·Queue 등 공통 상태를 전환 과정에서 파괴하지 않도록** 모듈 경계를 분리한다.
- 초기에는 Spring Boot JSON 로그·요청 처리 시간과 k6, CloudWatch 기본 지표만 사용한다. OpenTelemetry/ADOT/X-Ray/Prometheus/Grafana는 **6단계에서 비교 후 선택**하고 비용·지원 경로를 확인한다.

## 3. 비즈니스 요청 흐름과 계약

| 컴포넌트 | 동작 | 관측·안전 장치 |
|---|---|---|
| `GET /catalog` | 인증된 브랜드의 메뉴만 반환 | tenant_id, latency, 4xx/5xx |
| `POST /orders` | 주문과 Outbox 이벤트를 같은 DB 트랜잭션에서 생성 | tenant + idempotency key 유일 제약, Trace |
| `GET /orders/{id}` | 브랜드 소유권을 확인한 후 주문 조회 | 다른 브랜드 요청 거부 |
| Outbox Publisher | 아직 전송되지 않은 이벤트를 SQS로 재시도 발행 | 중복 발행 허용, 충돌 방지 잠금 및 발행 상태 |
| Worker | SQS 메시지 검증, 모의 POS 전달, 주문 처리 결과 기록 | 처리 멱등성, 재시도, DLQ, Trace Context |
| 모의 POS | 이벤트 중복 수신을 무해화하고 성공/지연/실패를 시뮬레이션 | 이벤트 ID 기준 처리 기록 |

초기에는 Outbox Publisher를 Order API 내부 백그라운드 처리로 둔다. 주문 승인 응답과 SQS 발행 간 장애를 안전하게 처리하기 위함이다. SQS Standard의 at-least-once 전송을 고려하여 비즈니스 처리 멱등성을 설계한다.

## 4. 데이터 경계

```text
RDS PostgreSQL
└── database: ordersaas
    ├── schema: brand_a (menus, orders, outbox_events, processed_events)
    ├── schema: brand_b (menus, orders, outbox_events, processed_events)
    └── schema: brand_c (menus, orders, outbox_events, processed_events)
```

- Source: 브랜드별 런타임 DB 사용자에 해당 스키마 사용 권한만 부여.
- Target: 서버가 검증한 브랜드 정체성에 맞는 제한적 DB 자격 증명을 선택; 클라이언트 제공 브랜드 헤더는 권한 근거가 아니다.
- 공통 RDS는 **논리적 격리**만 제공한다. CPU/메모리/스토리지 장애 도메인은 공유된다. 브랜드 A의 DB 자격 증명이 B의 스키마에 접근하지 못하는 부정 테스트를 유지한다.
- DB 운영자/마이그레이션 계정과 애플리케이션 런타임 계정을 분리한다. 풀링 및 권한 변경 시 다른 브랜드로 권한이 누출되지 않는지 점검한다.

## 5. Source: 브랜드별 ECS Fargate

- 클러스터 3개(브랜드별 1개), ECS Service 9개(Catalog/Order/Worker 각각 1개씩).
- API Service 기본 desired 2 Task/브랜드; Worker 기본 desired 1 Task/브랜드. 따라서 최초 기준선은 15 Task.
- 초깃값: Catalog 0.25 vCPU/512 MiB, Order 0.5 vCPU/1 GiB, Worker 0.25 vCPU/512 MiB.
- 각 브랜드: 전용 Task Role, SQS Queue+DLQ, DB 사용자/스키마. API와 Worker를 Private Subnet에서 실행.
- ALB 하나의 브랜드별 호스트 라우팅 및 Target Group을 사용해 공유 네트워크 비용을 통제. 클러스터 분리만으로 IAM·DB 격리 수준이 높아진다는 주장은 금지.

## 6. Target: 공유 ECS on EC2 + ASG

- 공유 ECS 클러스터 1개, 공유 ECS Service 3개(Catalog API, Order API, Worker).
- EC2 ASG 초기 제안: **min 2 / desired 2 / max 6**, 2개 AZ, 온디맨드 ECS 최적화 AMI 사용.
- 인스턴스 초기 후보 `m6i.large`(2 vCPU, 8 GiB), 인스턴스에 실제 Task·ADOT·ECS Agent가 차지하는 CPU/메모리와 ENI 한도를 검증한 뒤 확정한다.
- Task 초깃값은 Source와 동일, Target API Service 각각 desired 2 / min 2 / max 10; Worker desired 2 및 큐 적체 기반 확장.
- API ECS Service Auto Scaling은 CPU Target Tracking 60%를 시작점으로 삼고, Worker는 적체량/Task 및 처리 시간 기반 지표를 사용.
- **ECS Capacity Provider + ASG Managed Scaling**을 사용한다. `target_capacity = 90`(최초 실험값), 인스턴스 warm-up 120초(실측 후 수정). Task 수 증가 → 자원 부족 시 Capacity Provider가 ASG 인스턴스 증설을 유도하는 구조이지 ASG가 HTTP 트래픽에서 직접 Task 수를 판단하지 않는다.
- `awsvpc` Task 네트워크 및 EC2 ENI/Task 배치 한도를 검증. 필요 시 인스턴스 크기 또는 `awsvpcTrunking` 지원 조건을 검토. ASG 용량이 6대에 도달하면 추가 증설은 되지 않으며 부하 테스트로 해당 한계를 드러낸다.
- EC2 종료 시에는 ECS Task 정상 종료, ALB deregistration/connection draining, ASG Managed Draining 적용 여부를 검증한다.
- **IAM:** 인스턴스 Role, Task Execution Role, Task Role은 분리. 공유 Task Role이 모든 브랜드 SQS/Secret에 무제한 접근하도록 설계하지 말고, 접근 대상을 제한한 위임/역할·서버 측 검증과 감사로 보완한다. 브랜드별 AWS 리소스 접근은 구체적인 권한 모델 확정 후 부정 테스트에 포함.

## 7. VPC 및 공통 네트워크

- 단일 VPC, 2개 AZ. Public Subnet 2개(ALB), Private App Subnet 2개(ECS), Private DB Subnet 2개(RDS).
- ECS Task 직접 공개 금지. ALB만 인바운드 HTTPS 허용, API SG는 ALB SG에서만, DB SG는 승인된 API/Worker SG에서만 수신.
- Private Task가 ECR/SQS/CloudWatch/Secrets Manager 등에 연결하는 경로는 NAT 또는 VPC Endpoint의 실제 요구사항과 비용을 비교해 결정. 배포 후 안전한 정리 절차를 문서화한다.
- 개발 편의를 위해 보안 그룹이나 RDS를 인터넷 전체에 개방하지 않는다.

## 8. 관측 — 최소 기능 우선, 고도화는 6단계

- **초기:** Source/Target 공통 JSON 로그(`request_id`, `tenant_id`, 상태·처리 시간), k6 원시 결과, AWS 기본 CloudWatch 지표. 별도 Collector/대시보드/Trace 저장소는 지금 구축하지 않는다.
- **후반:** CloudWatch 단독 또는 OpenTelemetry·X-Ray·Prometheus·Grafana 등을 비교해 선택. API→DB→SQS→Worker→모의 POS의 Trace Context 및 Correlation ID 연계는 고도화 단계 목표다.
- 브랜드 A/B/C별 RPS, p50/p95/p99, 오류율, 주문 처리 지연, DLQ, SQS 메시지 대기, RDS CPU/연결, ECS Task desired/running/pending, EC2 ASG min/desired/in-service, Capacity Provider 이벤트.
- 초기 로그는 `request_id`, `service_name`, `tenant_id`, `deployment_version`을 담고, Trace를 도입한 후 `trace_id`·`span_id`를 추가한다. 원본 인증 토큰과 고객 데이터는 담지 않는다.
- 주문 ID·사용자 ID 등을 메트릭 라벨에 넣지 않는다. 초기 기준선은 k6·CloudWatch 자료를 남기고, 관측 고도화 이후 양쪽 환경을 **동일 조건으로 재측정**해 대시보드·실패/지연 Trace 증거를 확보한다.
- 상세 내용은 [08. 관측 계층](08-observability.md).

## 9. 마이그레이션 (DB 이동 없음)

1. Target 배포, 공통 RDS/Queue의 접근을 안전하게 검증하고 브랜드 A의 읽기 경로를 점검.
2. A의 신규 쓰기를 짧게 차단. **Outbox Publisher 및 A Worker** 동작을 조정해 유일한 발행·소비 경로를 보장.
3. 진행 중 주문과 Queue 메시지 상태를 기록하고, 새 Worker에 A만 허가.
4. ALB 라우팅을 A부터 Target으로 변경하며 B/C는 Source 유지.
5. 신규 API 쓰기와 Worker 소비를 활성화하고 주문 건수·실패율·Trace·Queue 상태를 검증.
6. 실패 시 다시 한 번 쓰기/소비를 정지하고 안전한 단일 주체로 복구. 같은 DB를 사용하더라도 구 버전 코드와 새 버전 코드의 데이터 호환성을 확인해야 하며, 무조건 즉시 DNS 롤백 가능하다고 주장하지 않는다.

## 10. 실험 및 수용 기준

- **비용:** 동등한 SLO·리소스 요구 기준에서 Source Fargate와 Target EC2의 월간 추정비용/실험 실제 청구액을 분리해 계산. ALB, RDS, NAT, 로그, Trace 등 포함.
- **확장성:** A 단독 부하, A/B/C 동시 부하; ECS Task 증설, Capacity Provider/ASG 증설, 서비스 안정화 시간을 시각별로 기록.
- **격리:** A의 과부하 상태에서도 B/C 지연을 측정하고, 브랜드 간 API·스키마·SQS 접근 거부 테스트를 수행.
- **전환:** 브랜드 A 주문 누락 0, 비즈니스 중복 처리 0, Cutover 중단 시간과 롤백 판단 근거 기록.
- **관측:** 정상 및 실패/지연 Trace, 관련 JSON 로그, 확장 이벤트, 대시보드, 알림 발화/복구 기록 확보.
- **과학적 정직성:** Source→Target은 **Fargate→EC2 및 브랜드 통합이 동시에 변경**되므로 전체 절감률을 공유 효과 하나로 해석하지 않는다. 필요하면 임시 공유 Fargate를 대조군으로 측정한다.

## 11. 구현 순서

1. 앱 계약·테스트 데이터·Docker Compose 및 JSON 로그.
2. 네트워크·RDS·SQS 공통 Terraform과 Source 브랜드별 ECS Fargate.
3. **최소 관측만 사용해** Source 기준선 측정(k6·기본 CloudWatch·비용).
4. Target ECS on EC2 / Capacity Provider / ASG + 부정 권한 검증.
5. A 테넌트 단계적 Cutover + Worker 중복 소비 방지.
6. **관측 도구 선택 및 고도화**(동일 조건 비교에 필요한 계측·대시보드·경보·추적).
7. Source/Target 재측정, k6 비용·장애·확장·Noisy Neighbor 실험, 운영 보고서, 리소스 정리.

## 12. 설계에서 아직 검증이 필요한 파라미터

- `m6i.large`에서 `awsvpc` ENI 및 기본 운영 오버헤드를 고려한 실제 최대 Task 배치 수. 관측 도구 도입 시 예약 자원을 재산정할 것.
- NAT Gateway와 VPC Endpoint 비용을 포함한 실제 2-AZ 테스트 예산.
- Worker 다중 SQS 소비 방식과 브랜드별 IAM 권한 위임, DB 자격 증명 캐시 만료 정책.
- Spring Boot 실제 메모리 소비와 지표 기반 확장 임계값.
- 6단계에서 결정할 관측 도구의 배포 위치, Trace 수집 경로·샘플링 및 운영 비용.

**이 항목들은 구현 과정에서 검증 후 ADR로 확정하며, 미검증 가정을 완료된 결과처럼 표기하지 않는다.**

## 공식 참고자료

- [ECS Capacity Provider 동작](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/managed-scaling-behavior.html)
- [ECS EC2의 awsvpc 네트워킹/ENI 제약](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/task-networking-awsvpc.html)
- [ECS IAM Role 모범 사례](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/security-iam-roles.html)
- [ECS ADOT Collector 구성](https://aws-otel.github.io/docs/setup/ecs/)
