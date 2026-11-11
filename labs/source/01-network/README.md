# Source Lab 01 — VPC, Subnet, Routing 및 보안

> **학습 상태:** Practice in progress (기초 VPC/서브넷 콘솔 실습 완료; 전체 Lab 미완료)
> **AWS 리소스 상태:** 마지막 스크린샷 시점 생성 확인 / 현재 실행 및 정리 여부 미검증
> **확인일:** 2026-11-11 · **IaC:** 미작성 · **다음:** IGW/Route Table 이론·설계 → 실습

[전체 학습 커리큘럼](../../../docs/10-learning-curriculum.md) · [상세 설계](../../../docs/09-detailed-design.md)

## 1. Overview

**목표:** Source의 2-AZ 네트워크 골격을 이해하고 안전하게 재현한다. VPC·Subnet·AZ의 관계, Public/Private을 결정하는 라우팅, SG 및 Private 서비스의 AWS API 접근 경로를 설명할 수 있어야 한다.

**성공 조건**
- 같은 VPC의 두 AZ에 Public/App/DB 서브넷 6개를 중복 CIDR 없이 구성
- Public Route Table의 기본 경로가 IGW를 향하고 App/DB에는 IGW 직결 기본 경로가 없음을 확인
- App의 NAT Gateway 또는 VPC Endpoint 경로 선택을 이유·비용과 함께 문서화
- SG 접근 정책과 검증 방법 기록 (실제 EC2/ECS 생성 없이 가능한 검증과 후속 통합 검증 구분)
- Terraform으로 재현·검증, 안전한 Cleanup 완료

## 2. Theory — 배포 전에 익힐 것

1. **VPC:** 리전 수준의 가상 네트워크 주소 공간. `10.20.0.0/16`의 `local` 라우트가 VPC 내부 연결 경로를 제공.
2. **AZ/서브넷:** 서브넷은 단일 AZ에 속함. 2개 AZ는 단일 AZ 장애 대비를 위한 배치 기반이며, 자체로 고가용성을 보장하지 않음.
3. **Public/Private:** 이름이나 '자동 퍼블릭 IP 할당' 체크박스만으로 구분하지 않음. Public은 IGW로의 기본 경로가 존재하고 인터넷과 직접 통신하려면 리소스의 퍼블릭 IP·SG 등 추가 조건이 필요함.
4. **IGW vs NAT:** IGW는 VPC 인터넷 경계; NAT Gateway는 Private 인스턴스의 IPv4 외부 발신 경로로 사용 가능하며 외부에서 직접 연결되는 진입점은 제공하지 않음. NAT Gateway는 유료.
5. **VPC Endpoint:** AWS 서비스에 Private으로 접근할 대안. Endpoint 종류/리전별 필요 항목, DNS, SG, 비용을 비교한 후 채택.
6. **Route Table:** 서브넷 연결과 longest-prefix match. 기본 Route Table을 실수로 Public용으로 바꾸지 않음.
7. **SG/NACL:** SG는 stateful 네트워크 정책, NACL은 subnet 단위 stateless 정책. VPC 기본 NACL 설정을 확인.

**서술형 확인 문제**
- VPC가 리전 단위인데 서브넷은 왜 특정 AZ에 속하는가?
- VPC만 만들고 6개 서브넷을 붙인 지금, 'public'과 'db'가 인터넷 연결에서 왜 아직 같을 수 있는가?
- IGW를 Attach만 하고 `0.0.0.0/0` 라우트가 없으면 어떤 결과가 나오는가?
- Private App Task에서 ECR/SQS/Logs로 나가는 연결은 어떤 방법으로 확보할 수 있는가?

## 3. Design — 목표 주소·라우팅

리전: `ap-northeast-2`, VPC: `ordersaas-source-vpc` / `10.20.0.0/16`.

| Subnet | AZ | CIDR | 역할 |
|---|---|---|---|
| `ordersaas-public-a` | `ap-northeast-2a` | `10.20.0.0/24` | 향후 ALB, 필요 시 NAT |
| `ordersaas-public-b` | `ap-northeast-2b` | `10.20.1.0/24` | 향후 ALB, 필요 시 NAT |
| `ordersaas-app-a` | `ap-northeast-2a` | `10.20.10.0/24` | ECS Fargate |
| `ordersaas-app-b` | `ap-northeast-2b` | `10.20.11.0/24` | ECS Fargate |
| `ordersaas-db-a` | `ap-northeast-2a` | `10.20.20.0/24` | RDS Subnet Group |
| `ordersaas-db-b` | `ap-northeast-2b` | `10.20.21.0/24` | RDS Subnet Group |

```text
Region: ap-northeast-2
  VPC 10.20.0.0/16
    AZ 2a: public-a | app-a | db-a
    AZ 2b: public-b | app-b | db-b

  Internet ←→ IGW ←→ Public Route Table ←→ public-a / public-b
  App Route Table: local + (필요 시 NAT 또는 VPC Endpoint)
  DB Route Table: local (인터넷 직접 경로 없음)
```

**라우팅 표(계획):**

| 서브넷 연결 | 목적지 | 대상 |
|---|---|---|
| Public A/B → Public RT | `10.20.0.0/16` | `local` |
| Public A/B → Public RT | `0.0.0.0/0` | `ordersaas-source-igw` |
| App A/B → App RT | `10.20.0.0/16` | `local` |
| App A/B → App RT | `0.0.0.0/0` | NAT 채택 시에만 해당 NAT |
| DB A/B → DB RT | `10.20.0.0/16` | `local` |

NAT와 VPC Endpoint는 **아직 생성/채택 미확정**. 초반 Network Lab에서는 유료 연결 리소스를 자동 생성하지 않고, 실제 ECS 배포 단계의 ECR/CloudWatch/SQS/Secrets Manager 요구와 비용을 보고 확정할 수 있다.

**보안 설계(후속 서비스 구성 시 검증):** ALB SG는 필요한 HTTPS 인바운드, API SG는 ALB SG에서만, DB SG는 허용한 API/Worker SG에서만 PostgreSQL 포트를 수신. SG를 0.0.0.0/0으로 열어 DB 테스트하지 않음.

## 4. Practice — 진행 기록

### 확인 완료 (사용자 AWS 콘솔 스크린샷 기반, 2026-11-11)

- VPC `ordersaas-source-vpc`, `10.20.0.0/16`, Available.
- DNS resolution 및 DNS hostnames 활성화.
- 2a/2b에 Public/App/DB 서브넷 각 1개씩, 총 6개 생성.
- 당시 6개 서브넷이 기본 Main Route Table을 사용한 리소스 맵 확인.

**스크린샷은 대화에서 확인되었고 저장소 파일로 첨부되지 않았다.** 이는 설정 당시 상태의 증거일 뿐 현재 리소스 현황을 보장하지 않는다.

### 다음 콘솔 실습 (아직 미완료)

1. 현재 계정·리전·VPC와 리소스 상태를 다시 확인.
2. Internet Gateway `ordersaas-source-igw` 생성 후 VPC에 Attach.
3. Public Route Table `ordersaas-source-public-rt` 생성, `0.0.0.0/0 → IGW` 경로 추가.
4. **Public A/B 두 서브넷만** Public RT에 명시적으로 연결. App/DB는 Main RT의 local 라우팅에 남김(후속 시 별도 App/DB RT 생성).
5. 서브넷 연결 및 Effective Route를 콘솔에서 비교·기록.
6. 필요 시 SG 설계 및 테스트 방법 준비. 과금 발생 리소스(NAT, ALB, RDS, EC2)는 이 단계에서 만들지 않음.

## 5. Terraform — 아직 작성 전

실제 모듈 경로는 구현 시 확정. 초기 제안: `infra/modules/network/` 및 이를 호출하는 독립 Lab root. 콘솔 생성 리소스에 대해 import 또는 삭제 후 Terraform 재생성 중 한 가지를 정하고 **중복 생성/소유권 충돌을 방지**한다.

```bash
terraform init
terraform fmt -check
terraform validate
terraform plan
# 계획 승인·비용 검토 후
terraform apply
# 테스트 및 검증 완료 후
terraform destroy
```

**주의:** 위 명령은 목표 실행 흐름이며 아직 수행한 기록이 아니다. State/Secret을 Git에 올리지 않는다. 삭제 전에 기존 수동 생성 리소스가 Terraform 관리 대상인지 확인한다.

## 6. Verification — 계획

- VPC CIDR 및 서브넷 CIDR이 일치하고 중복되지 않음.
- Public A/B에만 IGW 기본 경로가 있음.
- App A/B와 DB A/B에서 Public RT가 연결되지 않았음.
- IGW만 연결하고 기본 라우트가 없는 상태에서는 외부 경로가 생기지 않음을 설명 가능.
- 실제 연결 테스트는 테스트용 리소스 비용과 보안 요건을 검토한 뒤 진행. 라우트 설정 확인만으로 인터넷 통신 성공을 주장하지 않음.
- Terraform 배포 후 생성 리소스가 설계와 일치하는지 비교.

## 7. Troubleshooting

| 증상 | 확인할 항목 |
|---|---|
| 서브넷에서 예상과 다른 경로 | 명시적 Route Table 연결과 Main RT의 관계 |
| IGW가 있는데 인터넷 연결 불가 | 기본 경로, 퍼블릭 IP, SG/NACL, OS 방화벽 및 리소스 상태 |
| Private Task가 AWS 서비스에 접근 불가 | NAT/Endpoint 경로, Endpoint 정책·DNS, Task Role, SG |
| Terraform apply 충돌 | 기존 콘솔 리소스, import 상태, Terraform State 소유권 |

현재까지 확인된 장애·해결 기록은 없음. 문제 발생 시 재현 명령과 관측값을 추가한다.

## 8. Cleanup — 아직 미완료

- 해당 Terraform root에서 생성된 리소스만 `terraform destroy`로 삭제.
- 콘솔 수동 리소스를 Terraform에 import하지 않았다면 별도로 명시적 삭제.
- IGW 분리, 서브넷·라우트 테이블·VPC 삭제 전 의존 리소스 확인.
- AWS 콘솔에서 해당 VPC/IGW/서브넷/RT/SG/네트워크 인터페이스 및 과금 자산의 잔여 여부 확인.
- Destroy와 검증 결과를 기록한 뒤 인프라 상태를 `Destroyed`로 변경한다.
- 과금 경보는 지출의 강제 중단 장치가 아니다.

## 9. Review & Handoff

- **이번까지 확인한 것:** VPC 1개, 2-AZ/6-Subnet, DNS 설정.
- **현재 학습 상태:** Practice in progress. 이론 전체·설계·Terraform·최종 검증·Cleanup은 미완료.
- **다음 세션 시작:** 1) 계정/리전과 실제 리소스 확인 → 2) IGW/Route Table 원리 복습 및 구성 계획 → 3) Public RT 실습 → 4) Terraform 재현 → 5) 정리.
- **완료 증거:** 추후 CLI 출력, 설정표, Terraform Plan, 검증 로그, Cleanup 확인을 링크한다.
