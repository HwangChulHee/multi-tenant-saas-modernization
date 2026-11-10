# 멀티테넌트 SaaS 인프라 현대화

> **진행 상태: 로컬 애플리케이션 및 Phase 1-5 검증 완료. AWS 배포와 기준선 측정은 후속 단계입니다.**
>
> 이 프로젝트는 [Cognizant OrderServ의 멀티테넌트 ECS 현대화 사례](https://aws.amazon.com/blogs/architecture/how-orderserv-achieved-up-to-64-cost-savings-with-multi-tenant-ecs/) (AWS Architecture Blog, 2026-11-05)에서 영감을 받은 **독립적인 축소 실험**입니다. Cognizant와 무관하며, 실제 서비스 코드나 공식 사례의 성과를 재현했다고 주장하지 않습니다.

## 프로젝트 배경

가상의 외식 주문 SaaS가 프랜차이즈 브랜드 **3개**를 운영합니다. 기존에는 브랜드별로 ECS API 및 Worker 서비스를 독립 배포해 운영상 격리를 확보했습니다. 그러나 브랜드가 증가하면서 최소 Task 수에 따른 유휴 자원과 운영 관리 비용이 늘어납니다.

이 프로젝트는 브랜드별 독립 구조를 **공유 ECS on EC2 구조로 단계적으로 전환**하면서 **비용, 확장성, 테넌트 보안 격리, 운영 중 마이그레이션**의 상충 관계를 측정합니다. 공유 구조가 항상 우수하다는 결론을 미리 정하지 않습니다.

## 서비스 범위

| 구성 요소 | 최소 기능 | 인프라 관점 |
|---|---|---|
| Catalog API | 브랜드별 메뉴 조회 | 읽기 부하, 테넌트 인가 |
| Order API | 주문 등록·조회, 멱등성 키 사용 | 정합성, 데이터 격리 |
| Fulfillment Worker | SQS 이벤트를 모의 매장/POS로 전달 | 재시도, 중복 처리, 신뢰성 |
| 테넌트 라우팅·설정 | 브랜드별 독립/공유 환경 선택 | 단계적 전환과 롤백 |

실제 결제, 외부 POS 연동, 21개 마이크로서비스, 상용 멤버십 기능, **AWS 계정 간 마이그레이션**은 범위에서 제외합니다. 계정 간 이전은 별도 학습 과제입니다.

## 아키텍처 비교

| 항목 | 기존: 브랜드별 독립 구조 | 개선안: 공유 구조 |
|---|---|---|
| 컴퓨팅 | 브랜드별 ECS Fargate 서비스·Task | 공유 ECS on EC2(API·Worker) + EC2 ASG |
| 용량 | 브랜드마다 최소 Fargate Task 유지 | 공유 EC2 인스턴스에 Task 배치, ASG로 호스트 용량 확장 |
| 격리 | 배포·Role 분리 | 검증된 테넌트 인증·인가·DB 격리 |
| 확장 | 브랜드별 Fargate Task 확장 | ECS Service Auto Scaling → EC2 Capacity Provider → ASG 증설(자동·조건부), Noisy Neighbor 위험 |
| 전환 | 브랜드별 기존 엔드포인트 | 브랜드별 Cutover, 단일 쓰기 주체 보장 |

**ECS 클러스터를 분리했다고 해서 접근 권한이나 데이터 격리가 자동으로 보장되는 것은 아닙니다.** 서비스, Task Role, Queue, DB에 관한 구체적 결정은 [아키텍처 설계](docs/02-architecture.md)에 정리합니다.

**목표 컴퓨팅 결정:** 기존은 브랜드별 ECS Fargate, 전환 후는 **공유 ECS on EC2 + Auto Scaling Group(ASG)**. 트래픽 증가 시 ECS Task 수를 늘리고 EC2 배치 용량이 모자라면 Capacity Provider가 ASG 증설을 유도하도록 설계한다. ASG가 트래픽을 직접 해석해 Task를 늘리는 것은 아니다. EC2 Warm Pool·Bottlerocket은 별도 고도화 과제로 남긴다.

## 관측 계층 — 후반 구축 (도구 미확정)

**관측 기능은 프로젝트 범위에 유지하지만 도구 선택·본격 구축은 마이그레이션 이후(6단계)로 연기합니다.** 초기에는 Spring Boot JSON 로그(`request_id`, 인증된 `tenant_id`, 처리 시간), k6 원시 결과, AWS 기본 CloudWatch 메트릭만 수집합니다. 최종 비교 실험 전에는 Source/Target을 동일한 관측 조건으로 재측정합니다. OpenTelemetry·X-Ray·Prometheus·Grafana 등은 지금 확정하지 않습니다. [단계별 로드맵](docs/06-roadmap.md) · [관측 요구사항](docs/08-observability.md)

## 4대 검증 영역

1. **비용:** 동일한 가용성 및 SLO 조건에서 리소스 사용량과 월간 예상 비용 비교.
2. **확장성:** 초기에는 k6·기본 CloudWatch 지표로 유휴·정상·프로모션 폭증 부하의 지연·오류를 측정하고, 관측 고도화 후 동일 조건으로 재측정하여 Noisy Neighbor의 원인을 분석.
3. **보안:** 브랜드 간 API/DB 접근 차단, 신뢰 가능한 테넌트 식별, 최소 권한 검증.
4. **운영 중 전환:** 브랜드 A를 운영 부하 상태에서 전환하며 주문 수·SQS 처리 결과를 검증하고 제한 조건이 명확한 롤백 절차 실험.

로컬 Compose의 보안·복구 검증과 부하 측정은 별도로 기록합니다. AWS 환경의 성능·비용 비교는 실제 배포 후 측정합니다. [로컬 부하 실험](experiments/README.md)

## 문서

- [01. 프로젝트 범위 및 요구사항](docs/01-project-scope.md)
- [02. 아키텍처 및 설계 의사결정](docs/02-architecture.md)
- [03. 성능·확장성·비용 실험 계획](docs/03-experiment-plan.md)
- [04. 테넌트 보안 설계](docs/04-security-plan.md)
- [05. 단계별 마이그레이션 Runbook](docs/05-migration-runbook.md)
- [06. 11월 로드맵](docs/06-roadmap.md)
- [07. 참고 자료](docs/07-references.md)
- [08. 필수 관측 계층 설계](docs/08-observability.md)
- [09. 구현 상세 설계 v1](docs/09-detailed-design.md)

## 디렉터리

```text
apps/            # API, Worker, 모의 POS
infra/           # Terraform 및 환경별 설정
experiments/     # 부하 시나리오와 민감 정보를 제거한 실험 결과
docs/            # 요구사항, ADR, 계획서, 결과 보고서
```

## 기본 원칙

- 실제 고객 정보나 결제 정보 사용 금지.
- 자격 증명과 개인 식별 정보 Git 커밋 금지.
- AWS 생성 전에 예산 경보와 리소스 정리 절차 마련.
- 가상 요구사항, 실제 측정 결과, 외부 사례의 주장을 명확히 구분.
