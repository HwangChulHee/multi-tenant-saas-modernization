# Multi-Tenant SaaS Infrastructure Modernization

> **Status: Planning. No AWS deployment, security validation or benchmarks have been completed.**
>
> An independent, scaled-down infrastructure modernization project **inspired by** [Cognizant OrderServ's multi-tenant ECS case](https://aws.amazon.com/blogs/architecture/how-orderserv-achieved-up-to-64-cost-savings-with-multi-tenant-ecs/) (AWS Architecture Blog, 2026-11-05). Not affiliated with Cognizant; no production source code or reported performance results are reproduced.

## Business scenario

A fictional multi-brand restaurant-ordering SaaS hosts **three independent brands**. Its initial design deploys separate ECS API and worker services for each brand to achieve clear operational isolation. As the tenant count grows, duplicated minimum task capacity and operating overhead increase.

We will test a gradual transition to **shared ECS compute** while measuring the trade-offs in **cost, scalability, tenant security, and live migration**. The objective is not to prove shared compute is always superior, but to determine under which constraints it is appropriate.

## Product scope

| Component | Minimal behavior | Infrastructure concern |
|---|---|---|
| Catalog API | Brand-specific menu reads | Read traffic; tenant authorization |
| Order API | Place/read an order with idempotency key | Consistency; tenant data isolation |
| Fulfillment Worker | SQS event to simulated store/POS receiver | Retries; duplication; reliability |
| Tenant routing/config | Select dedicated/shared deployment per brand | Migration waves and rollback |

Excluded: real payments, full POS integrations, 21 microservices, production-grade loyalty services, and cross-account migration (tracked as an independent future learning topic).

## Before / After

| Dimension | Before: dedicated | After: shared |
|---|---|---|
| Compute | Separate ECS services/task sets per brand | Shared ECS API/worker services |
| Capacity | Per-brand minimum tasks | Pooled task capacity |
| Isolation | Deployment and role separation | Verified tenant identity, authorization, database boundary |
| Scaling | Brand-local | Shared pool; noisy-neighbor risk |
| Migration | Existing dedicated endpoint | Brand-by-brand cutover, single authoritative writer |

Separate ECS *clusters* are **not automatically** equivalent to stronger authorization or data separation. An implementation decision on services, task roles, queues, and databases is recorded in [architecture](docs/02-architecture.md).

## Four validation tracks

1. **Cost:** measured resource-hours and transparent monthly estimates under matching availability/SLO assumptions.
2. **Scalability:** per-brand latency and errors during idle, steady, promotional burst, and all-brand workloads; detect noisy-neighbor effects.
3. **Security:** negative cross-tenant API and database tests; trusted tenant identity; least-privilege AWS access.
4. **Live transition:** migrate Brand A under synthetic load, verify order counts and SQS processing, and demonstrate cutover and a bounded rollback procedure.

**Metrics and outcomes are TBD until measured.** Source article results are third-party observations, not results of this project.

## Documentation

- [01 Business scope](docs/01-project-scope.md)
- [02 Architecture / design decisions](docs/02-architecture.md)
- [03 Experiments / cost model](docs/03-experiment-plan.md)
- [04 Tenant security](docs/04-security-plan.md)
- [05 Migration runbook](docs/05-migration-runbook.md)
- [06 November roadmap](docs/06-roadmap.md)
- [07 References](docs/07-references.md)

## Repository layout

```text
apps/            # API / worker / simulated POS
infra/           # Terraform and environment configuration
experiments/     # load tests, scenario definitions, redacted results
docs/            # requirements, ADRs, plans, reports
```

## Guardrails

- No real customer data or payment information.
- Do not commit credentials or actual customer identifiers.
- Configure AWS budgets/alerts and document teardown before provisioning.
- Distinguish hypothetical requirements, tested results and third-party claims.
