# 애플리케이션

Java 21과 Spring Boot로 로컬 멀티테넌트 Catalog 및 Order API를 실행한다.
각 서비스는 독립 실행 JAR와 컨테이너 이미지로 빌드된다.

## 개발 환경

- 로컬 빌드 및 직접 실행에는 JDK 21이 필요하다. Gradle은 저장소에 포함된 Wrapper를 사용한다.
- 컨테이너 실행에는 Docker Engine과 Docker Compose v2가 필요하다. WSL에서는 사용하는 배포판에서 Docker 엔진에 연결되는지 `docker version`으로 확인한다.
- 처음 빌드할 때 Gradle 배포본, 빌드 의존성, 컨테이너 이미지를 내려받을 수 있어야 한다.

이하 명령은 모두 저장소의 `apps/`에서 실행한다.

## 빌드 및 실행

```bash
./gradlew clean build
SERVER_PORT=8084 ACTIVE_BRANDS=brand_a,brand_b,brand_c ./gradlew :mock-pos:bootRun
```

Catalog, Order, Worker를 직접 실행할 때는 `DB_URL`, `ACTIVE_BRANDS`, 활성 브랜드별
`DB_BRAND_A_PASSWORD` 등의 런타임 비밀번호를 넘긴다. Catalog와 Order에는
`JWT_ISSUER`, `JWT_AUDIENCE`, `LOCAL_JWT_SECRET` 또는 `JWT_JWK_SET_URI`도 필요하다.
DB는 실행하는 프로세스에서 접근할 수 있어야 한다.

개별 이미지는 예를 들어 `docker build --build-arg SERVICE=catalog-api -t catalog-api:local .`로 빌드한다.
이미지는 배포 환경별 설정을 런타임 환경변수로 받으므로 Source와 Target에서 재사용할 수 있다.

```bash
cp -n .env.example .env
# 최초 1회, LOCAL_JWT_SECRET이 비어 있는 경우
sed -i "s/^LOCAL_JWT_SECRET=$/LOCAL_JWT_SECRET=$(openssl rand -hex 32)/" .env
docker compose up --build --wait
docker compose ps
docker compose down
```

`down` 후에도 PostgreSQL 데이터 볼륨은 유지된다. 예제 비밀번호는 로컬 개발용이다.
`DB_URL`의 DB 이름은 `POSTGRES_DB`에 맞추고, `ACTIVE_BRANDS`는 쉼표로 구분한다.
Order와 Worker의 `SQS_ENDPOINT` 및 `AWS_REGION`은 다음 단계의 SQS 연동에 사용할 설정이다.
Compose는 PostgreSQL 준비 후 일회성 `migrate` 서비스에서 SQL을 적용하고 런타임 서비스를 시작한다.
기존 볼륨에서는 기존 PostgreSQL 관리자 자격 증명을 유지하고 누락된 환경변수를 `.env.example`에서 추가한다.
마이그레이션 계정은 스키마를 소유하고, 브랜드별 Catalog·Order·Worker 역할은 필요한 테이블 권한만 받는다.
별도 풀을 브랜드별로 생성하므로 요청 도중 연결의 테넌트 컨텍스트를 바꾸지 않는다.
단일 브랜드 배포에서는 예를 들어 `ACTIVE_BRANDS=brand_a`를 설정한다.
공유 배포에서는 활성 브랜드를 쉼표로 구분한다. 신뢰하는 JWT의 `tenant_id`만 사용하고 `X-Tenant-ID`는 무시한다.
PostgreSQL과 LocalStack은 Compose 네트워크 내부에서 접근한다.

| 서비스 | 기본 로컬 포트 | 포트 변수 |
| --- | ---: | --- |
| Catalog API | 8081 | `CATALOG_PORT` |
| Order API | 8082 | `ORDER_PORT` |
| Fulfillment Worker | 8083 | `WORKER_PORT` |
| Mock POS | 8084 | `MOCK_POS_PORT` |

## 동작 확인

아래 예시는 기본 포트 기준이다. `/health`는 프로세스 생존을 확인한다.
`/ready`는 서비스 준비 상태를 확인하며 Catalog, Order, Worker는 PostgreSQL 연결도 확인한다.
Worker의 HTTP 포트는 상태 확인용이다. 각 서비스는 서비스명이 포함된 JSON 로그를 stdout에 남긴다.

```bash
for port in 8081 8082 8083 8084; do
  curl -fsS "http://localhost:$port/health" && echo
  curl -fsS "http://localhost:$port/ready" && echo
done

docker compose exec -T postgres sh -ec \
  'PGPASSWORD="$POSTGRES_PASSWORD" psql -h 127.0.0.1 -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "SELECT 1;"'
docker compose exec -T localstack awslocal sqs list-queues
```

## 디렉터리 구조

```text
apps/
├── common/                # 공통 Actuator 및 로그 설정
├── catalog-api/           # Catalog API
├── order-api/             # Order API
├── fulfillment-worker/    # Fulfillment Worker
├── mock-pos/              # 모의 POS
├── gradle/wrapper/        # Gradle Wrapper
├── Dockerfile             # 서비스별 이미지 빌드
├── compose.yaml           # 로컬 실행 구성
└── .env.example           # 로컬 환경변수 예시
```

## Phase 1-1 검증 기록

Ubuntu 24.04 WSL, JDK 21, Docker Engine 27.5.1 및 Compose 2.32.4에서 확인했다.

- `./gradlew clean build`로 전체 모듈을 빌드했다.
- 애플리케이션 이미지 4개를 빌드하고 Compose 컨테이너 6개의 `healthy` 상태를 확인했다.
- 네 서비스의 `/health`와 `/ready`가 모두 200을 반환했다. PostgreSQL 중단 중에는 네 서비스의 `/health`가 200을 유지했고, Catalog·Order·Worker의 `/ready`만 503으로 바뀌었다. DB 재시작 후 전체가 복구됐다.
- PostgreSQL에 개발용 자격 증명으로 TCP 연결해 `SELECT 1`을 실행했다.
- LocalStack에서 임시 SQS 큐를 생성해 메시지를 송신·수신·삭제한 뒤 큐를 정리했다.
- 네 서비스의 stdout에서 서비스명을 포함한 JSON 로그를 확인했다. Compose 설정과 Git의 `.env` 제외 규칙도 확인했다.

## Phase 1-2 API 및 검증

- `GET /catalog`은 인증된 브랜드의 메뉴를 반환한다.
- `POST /orders`는 `Idempotency-Key` 헤더와 `{"menuId":"menu-1","quantity":1}`을 받는다.
  최초 생성은 201, 동일 요청 재전송은 200, 다른 내용으로 같은 키를 재사용하면 409를 반환한다.
- `GET /orders/{id}`는 소속 브랜드의 주문을 반환한다. 다른 브랜드 주문 ID도 404로 응답한다.
- 로컬 JWT는 개발용 HS256 키로 서명한다. 실제 서명 검증은 Spring Security가 수행한다.
  배포 시 신뢰하는 발급자의 JWKS, issuer, audience를 환경변수로 설정할 수 있다.

예제 환경과 생성한 로컬 JWT 키를 사용해 Compose를 기동한 뒤, 동일 키를 셸에 내보내고
`python3 tests/test_phase12.py`를 실행한다. 테스트는 예제 DB 계정과 기본 포트를 사용한다.

Ubuntu 24.04 WSL에서 Gradle 전체 빌드와 Compose 통합 테스트 5건을 통과했다.
세 브랜드의 메뉴 및 주문, 교차 브랜드 404, 위조 헤더 무시, DB 권한 거부,
동일 키로 보낸 동시 요청 8건이 주문 1건으로 수렴하는 동작을 확인했다.

## 다음 구현 단계

트랜잭션 Outbox, 브랜드별 SQS 큐, Worker 및 모의 POS를 연결한다.
