# 인프라

Terraform 기반 기존(Source: 브랜드별 독립 ECS 서비스) 및 개선(Target: 공유 ECS 서비스) 환경 구성을 이 디렉터리에 추가할 예정입니다.

AWS 리소스를 배포하기 전에 예산, 접근 권한, Region, 정리 방법을 정의합니다. 아직 인프라 배포는 수행하지 않았습니다.

## 실습·재현 계획

- [학습·실습 커리큘럼](../docs/10-learning-curriculum.md)
- [Source Lab 01: VPC 및 네트워크](../labs/source/01-network/README.md)
- 향후 `modules/`에 재사용 Terraform 모듈, `environments/source/`에 Source 통합 환경을 정의한다. **현재 경로는 계획이며 Terraform은 미작성**이다.
- 리소스 생성 전 비용·보안·검증·정리 방법을 검토하고, 콘솔 생성 리소스를 import하거나 삭제 후 Terraform으로 재생성해 상태 충돌을 방지한다.
- `terraform.tfstate`, 인증정보, Secret, 민감한 tfvars는 커밋하지 않는다. AWS 리소스 삭제 여부는 실제 검증 후 기록한다.
