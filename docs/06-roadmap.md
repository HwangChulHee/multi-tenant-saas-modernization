# 06. 2026년 11월 구현 로드맵

> **상태: 계획.** 실제 구현·배포·실험 완료 여부는 증거와 함께 별도 기록한다.
>
> **순서 변경(2026-11-10):** 관측 플랫폼의 선택 및 본격 구축은 마이그레이션 이후로 연기한다. 단, Source 기준선 수집에 필요한 최소 로깅과 기본 측정은 처음부터 유지한다.

실습별 학습 순서·과금 관리·Terraform 재현 및 Cleanup 기준은 [10. 학습·실습 커리큘럼](10-learning-curriculum.md)을 따른다. 이 로드맵의 프로젝트 단계와 각 Lab의 완료 상태는 별도로 관리한다.

## 단계별 진행 순서

| 단계 | 작업 | 구현·검증할 내용 | 통과 기준 |
|---|---|---|---|
| 1 | 최소 애플리케이션 구현 | Java/Spring Boot Catalog·Order·Worker·모의 POS, PostgreSQL 브랜드별 Schema, SQS 연동, Docker Compose | 주문→비동기 처리 통합 테스트 통과, 교차 테넌트 접근 차단 |
| 2 | Source Fargate 인프라 | Terraform, VPC/ALB/RDS/SQS, 3개 브랜드별 ECS Fargate 서비스·권한 | 3개 브랜드의 독립 요청/처리 경로 정상 작동 |
| 3 | Source 기준선 측정 | k6 결과, 기본 CloudWatch ECS/ALB/RDS/SQS 지표, JSON 로그, 예상 비용 | 유휴/정상/A 폭증 시나리오의 입력·성능·비용 가정 저장 |
| 4 | Target 공유 ECS on EC2 | ECS EC2 Capacity Provider·ASG, 공유 API·Worker, DB/Queue 유지, IAM 검증 | Task 및 EC2 증설 동작, 테넌트 접근 거부 통과 |
| 5 | 단계적 마이그레이션 | 브랜드 A Cutover, 쓰기 주체/Outbox/Worker 중복 방지, 롤백 의사결정 | 주문 누락·중복 처리 검사, 변경 타임라인 확보 |
| 6 | 관측 계층 고도화 | CloudWatch 단독 또는 Prometheus/Grafana/OTel/X-Ray 등 도구 선택, 브랜드별 대시보드·경보·추적 | Source와 Target에 동일한 계측 조건을 적용할 수 있음 |
| 7 | 최종 비교·장애 실험 | 두 환경을 같은 관측 조건으로 재측정, 비용·확장성·Noisy Neighbor·보안·장애 원인 분석 | 원시 결과, 그래프, 분석 보고서, Runbook, 리소스 정리 기록 |

**날짜는 실행 속도에 따라 조정**한다. 11월 말 지원을 고려하되, 관측 도구 결정을 위해 앱·인프라 구현을 멈추지 않는다.

## 지금 구현하는 최소 관측

- 애플리케이션은 stdout에 구조화 **JSON 로그**를 남긴다. 가능하면 `timestamp`, `service_name`, `request_id`, `tenant_id`, `duration_ms`, `status`를 포함한다.
- 민감 정보·인증 토큰은 로그에 남기지 않으며 `tenant_id`는 인증 후 확정한 값만 기록한다.
- 각 API는 처리 시간을 기록한다. **k6의 요청 처리량·p95·오류율은 원시 결과로 저장**한다.
- AWS 기본 CloudWatch 메트릭(사용 가능한 ECS/ALB/RDS/SQS/EC2 지표)을 보관한다. EC2 메모리 등 기본 제공되지 않는 지표는 따로 계측할 때 명시한다.
- 자동 확장 및 Cutover 시각은 운영 로그에 수동·자동으로 기록한다.
- 이 단계에서는 OpenTelemetry Collector, Prometheus, Grafana, Trace 저장소, 고급 경보를 설치할 필요가 없다.

## 관측 고도화의 시점과 범위

- **6단계에서 도구 선택:** 우선 CloudWatch 중심으로 충분한지 평가하고, 부족한 분석 요구가 확인되면 Prometheus/Grafana 또는 OpenTelemetry/Trace 백엔드 추가를 검토한다.
- Source와 Target 비교의 정합성을 위해 **최종 실험은 두 환경 모두 같은 계측 설정으로 재실행**한다.
- 상세 추적(HTTP→DB→SQS→Worker)은 목표 기능으로 남겨두되, 수집 백엔드·Collector 배포 방식을 지금 확정하지 않는다.
- 관측 자체의 CPU·메모리·비용 오버헤드를 실측해 보고서에 포함한다.

## 우선순위

- **P0 / 지금:** 로컬 앱 기능, Source Fargate, 최소 JSON 로그·k6·기본 메트릭, Target EC2/ASG, 브랜드 A Cutover 안전성.
- **P1 / 후반:** 관측 계층 도구 선택·고도화, 동일 조건의 재측정, 브랜드별 대시보드, 경보, 장애 원인 분석 및 최종 보고서.
- **P2 / 확장:** EC2 Warm Pool/Bottlerocket, 복잡한 LGTM 스택, 고급 샘플링·장기 저장, 전체 브랜드 전환 및 확장된 CI/CD.

관측은 **삭제한 것이 아니라 순서를 뒤로 옮겼다.** 일정 부족으로 P1을 생략한다면 관측 기반 장애 분석까지 완료했다고 주장하지 않는다.

## 최종 완료 기준

1. 애플리케이션이 로컬 및 두 AWS 컴퓨팅 환경에서 재현 가능하다.
2. 공유 ECS에서도 API·DB·Queue의 브랜드별 권한 격리를 검증한다.
3. 브랜드 A Cutover와 주문 정합성 검증 기록이 있다.
4. 기본 Source 기준선과 **동일 관측 조건의 최종 Source/Target 비교**가 구분되어 있다.
5. 비용·성능·확장성·장애 근거, 관측 비용 및 변경 보고서·Runbook을 남긴다.
6. AWS 예산 경보 및 Terraform 리소스 정리 절차를 명시한다.
