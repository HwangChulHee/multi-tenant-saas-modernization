# 10. 학습·실습 커리큘럼

> 상태: **학습 운영 규칙 확정 / AWS 실습 진행 중** (2026-11-11).
> 이 문서는 학습 순서와 실습 완료 기준이다. 실제 제품 구현 단계와 수용 기준은 [06. 구현 로드맵](06-roadmap.md), [09. 상세 설계](09-detailed-design.md)를 따른다.
> **문서의 계획은 실제 AWS 구축·검증 완료를 의미하지 않는다.**

## 1. 목적과 기본 원칙

목표는 실제 AWS에서 Source(브랜드별 ECS Fargate) → Target(공유 ECS on EC2 + ASG/Capacity Provider) → Cutover → 성능·비용·격리 비교를 수행하면서, 각 단계의 개념·설계 근거·관측 결과를 스스로 설명하고 환경을 반복 재현하는 것이다.

- **먼저 학습, 나중에 과금:** Theory와 Design을 끝내기 전에는 실습을 위한 과금 리소스를 만들지 않는다.
- **독립된 학습 단계, 재현 가능한 실습:** 각 Lab은 이론·검증·증거·정리 단위로 완결한다. 의존 인프라는 Terraform 모듈을 조합해 재생성한다.
- **수동 경험 이후 IaC:** 처음 접하는 핵심 리소스는 콘솔/CLI에서 직접 구성해 보고 Terraform으로 옮긴다. 콘솔 리소스를 import하거나 삭제 후 Terraform으로 재생성하되 같은 리소스를 중복 소유하지 않는다.
- **완료와 가동 상태 분리:** Lab은 완료했더라도 AWS 인프라는 삭제된 상태일 수 있다. '실습 완료'를 '현재 배포 중'과 혼동하지 않는다.
- **실측과 예상 구분:** 설정값·가정·예상 비용과 실제 AWS 측정 결과를 명확히 구분한다.
- **불필요한 재구축 회피:** 서로 의존하는 Lab 04~07 등은 하나의 배포 세션에서 묶어 실습할 수 있지만, 학습·검증 기록은 Lab별로 남긴다.

## 2. 공통 Lab 생명주기

| 단계 | 수행 내용 | 다음 단계로 이동하는 조건 |
|---|---|---|
| 1. Theory | 개념, 내부 동작, 왜 필요한가, 실패 사례, 대안; 서술형 인출 문제 | 핵심 흐름을 말/그림으로 설명 가능 |
| 2. Design | 아키텍처, CIDR/권한/라우팅, 리소스 목록, 의존성, 비용 위험, 검증·삭제 계획 | 설계 및 성공 조건 확정 |
| 3. Practice | 콘솔/CLI로 직접 구축; 기대 동작과 오류 상황 관찰 | 실습 증거 확보 |
| 4. IaC | Terraform으로 코드화; 재사용 모듈, 입력·출력, 초기화 스크립트 | fmt/validate/plan 통과, 배포·검증 재현 확인 |
| 5. Verification | 통신, 기능, 부정 접근, 장애·재시도, 결과 기록 | 정상/비정상 수용 기준과 증거 충족 |
| 6. Cleanup | 과금 리소스 삭제, 잔여 리소스·비용 확인, 상태 기록 | 다음 세션에서 다시 시작 가능 |

예외: 실제 배포 없이 개념을 검증하는 학습은 Practice/IaC를 '해당 없음'으로 표기하고 근거를 남긴다. AWS 구축을 요구하는 Lab은 문서·계획만으로 완료 처리하지 않는다.

### Lab 상태(학습 상태와 인프라 상태는 별도)

- **학습 상태:** Not started → Theory done → Design done → Practice in progress → Verified → Complete.
- **AWS 인프라 상태:** Not deployed / Running / Destroyed / Cleanup pending.
- Verified는 실습 검증 완료를 뜻하고, Complete는 재현 자료와 Cleanup 검증까지 끝난 상태를 뜻한다.
- README 머리말에 상태, 마지막 검증 일자, 완료 증거, 다음 작업, 재개 명령을 기록한다. 증거 없는 완료 표기는 피한다.

### 각 Lab README 템플릿

1. Overview (목표, 선행 Lab, 성공 조건)
2. Theory (개념, 패킷/요청 흐름, 설계 선택 이유, 서술형 문제)
3. Design (구성도, 설정표, 비용·보안·의존성)
4. Practice (콘솔·CLI 단계, 예상 결과)
5. Terraform (코드 경로, init/plan/apply, import 또는 재생성 방식)
6. Verification (정상·장애·권한 부정 테스트, 수집할 증거)
7. Troubleshooting (증상, 원인, 확인 절차, 해결)
8. Cleanup (destroy, 수동 잔여 자원 확인)
9. Review & Handoff (배운 점, 결과 링크, 다음 세션 시작점)

## 3. Source Track — Phase 2~3

실습 단위는 네트워크·DB·메시징부터 독립성을 확보하고, 앱 배포 이후에는 공통 Source 스택을 재사용한다.

| Lab | 학습 범위 | 최종 산출물 / 완료 기준 |
|---|---|---|
| [01 — Network](../labs/source/01-network/README.md) | VPC, AZ, CIDR, 6 Subnet, IGW, Public/Private Route Table, SG, NAT vs Endpoint | 네트워크 Terraform, 라우팅 검증, 정리 |
| 02 — Database | RDS PostgreSQL, DB Subnet Group, SG, Schema, 브랜드별 DB Role, 데이터 초기화 | 접속·권한 부정 테스트, 재생성 SQL, 정리 |
| 03 — Messaging | SQS Standard, DLQ, Visibility Timeout, Redrive, IAM | 브랜드별 큐, 실패·복구 실험, 정리 |
| 04 — ECS Fargate | ECR, Task Definition, Service, IAM Roles, ALB, HTTPS, Mock POS 배치 | 브랜드 A API/Worker 배포와 정상 통신 |
| 05 — End-to-end | Catalog → Order → Outbox → SQS → Worker → POS → DB | A 주문 201→FULFILLED 및 재시도/멱등성 증거 |
| 06 — Multi-tenant | 브랜드 B/C 서비스 확장, Host/Path Routing, DB·SQS·IAM 격리 | 총 9 Service 구조 및 교차 접근 거부 |
| 07 — Baseline | JSON/CloudWatch, k6 유휴/정상/A 집중 부하, ECS Auto Scaling, 비용 | 원시 결과, 한계·가정·청구액 구분, 정리 |

주의: Lab 04의 Mock POS는 Source↔Target 비교에서 공통 실험 설비다. 배치 및 비용 포함 여부를 고정해 기록한다. Source 초기안은 9개 Service, 15개 Task이며 실제 배포 후 확정한다. Cluster 3개와 Cluster 1개/9 Service 중 선택은 ADR로 결정하고 보안 경계로 과장하지 않는다.

## 4. 후속 Track (초기 계획)

| Track | 학습 단위 | 확인할 것 |
|---|---|---|
| Target | ECS on EC2, ASG, Capacity Provider, Task 배치/ENI, IAM | Task 증설과 호스트 증설 분리, 자원 경쟁·운영 비용 |
| Migration | A의 단일 쓰기/Publisher/Worker 소유권, ALB 경로 전환, rollback | B/C는 Source 유지, 누락·중복 비즈니스 효과 0 |
| Operations | 관측 고도화, 양쪽 동일 조건 재측정, 장애·Noisy Neighbor, Runbook | 성능·비용·격리 트레이드오프를 측정 근거로 설명 |

후속 Track 세부 Lab은 Source 실험 결과를 확인한 후 문서화한다. Source→Target은 Fargate→EC2와 테넌트 공유라는 **두 변수**가 함께 바뀌므로 절감 원인을 단일 요인으로 단정하지 않는다.

## 5. Terraform 및 실습 운영 규칙

예상 구조(코드가 아직 생성되지 않은 경로는 계획임):

```text
labs/source/01-network/README.md       # 학습·실습·검증 로그
infra/modules/network/                  # 재사용 인프라
infra/modules/database/
infra/modules/messaging/
infra/modules/ecs-fargate/
infra/modules/alb/
infra/environments/source/              # Source 전체 스택 진입점
```

- 각 Lab별 독립 배포가 필요하면 작은 root module을 추가하고 공통 모듈을 재사용한다. 모든 Lab에 Terraform 코드를 복사하지 않는다.
- 기존 콘솔 생성 리소스는 **import로 관리 전환**하거나 안전하게 삭제한 후 Terraform에서 재생성한다. Terraform state와 실제 AWS 리소스 간 소유권을 확인한다.
- 재현 명령의 기본 흐름은 `terraform init` → `terraform fmt -check` → `terraform validate` → `terraform plan` → `terraform apply` → 검증 → `terraform destroy`이다.
- DB Schema, Role, 테스트 데이터는 SQL/스크립트로 재현하며 재생성 시 데이터가 초기화될 수 있음을 명시한다.
- `*.tfstate*`, `.terraform/`, `*.tfvars` 내 민감 정보, 자격 증명, 개인 데이터, JWT 키, Secret을 Git에 올리지 않는다. `.gitignore`와 State 저장·보호 방식을 구현 전에 검증한다.
- Backend와 State 잠금 전략은 실제 Terraform 도입 때 결정한다. State를 수동으로 지우지 않는다.

### 비용·보안 체크리스트

- [ ] 리전·계정 및 AWS 예산/경보 확인 (경보는 강제 비용 상한이 아님)
- [ ] 과금 위험 목록 작성: NAT Gateway, RDS, ALB, Fargate/EC2, Public IPv4, Endpoint, CloudWatch, 스냅샷 등
- [ ] 보안 그룹 최소 권한, DB 비공개, Secret 외부 노출 없음
- [ ] 실습 종료 시 destroy 결과와 잔여 리소스 수동 점검
- [ ] EIP/Public IPv4, NAT, EBS, RDS 스냅샷, CloudWatch 로그/저장소 등 별도 요금 자산 확인
- [ ] 다음 Lab 재현에 필요한 출력값·초기화 스크립트·문서 저장

## 6. 다른 학습 프로젝트에도 적용

- **클라우드 Lab:** Theory → Design → Practice → Terraform → Verification → Cleanup.
- **네트워킹 Lab(Packet Tracer):** Theory → Topology Design → Packet/CLI Practice → `.pkt` 및 장비 설정 저장 → 통신/패킷 검증 → 상태 저장. 비용 없는 환경에 Terraform이나 강제 삭제를 요구하지 않는다.
- 기존 실습의 진도를 소급해서 임의로 '완료' 처리하지 않고, 증거가 확보된 범위만 기록한다.

## 7. 현재 체크포인트 (2026-11-11)

- **Source Lab 01:** VPC `ordersaas-source-vpc`(`10.20.0.0/16`), 서울 2a/2b의 Public/App/DB 6개 서브넷 콘솔 생성 화면 확인. DNS resolution/hostnames 활성화 확인.
- **아직 미확인:** IGW 생성·연결, Route Table 분리, SG, Terraform 재현, 검증, Cleanup. 현재 환경 삭제 여부는 검증하지 않음.
- **다음:** [Source Lab 01](../labs/source/01-network/README.md)에서 남은 네트워크 이론·설계 정리 → 콘솔 실습 → Terraform 관리 전환 → 검증/정리.
