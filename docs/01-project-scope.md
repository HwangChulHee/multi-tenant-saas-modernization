# 01. Project scope and business requirements

**Status:** Proposal — 2026-11-10. Fictional business, independently designed experiment.

## Customer story

A restaurant-ordering SaaS hosts three franchise brands:
- **Brand A:** high promotional bursts and high order volume.
- **Brand B:** steady moderate traffic.
- **Brand C:** small tenant with mostly idle capacity.

The incumbent per-brand ECS API and worker deployments offer straightforward isolation but have duplicated minimum tasks. The customer wants lower operational cost **without weakening availability or exposing other brands' data**.

## Concrete domain workflows

1. A signed-in brand operator manages the brand's catalog.
2. A customer reads a menu and submits an order with an idempotency key.
3. The Order API persists a tenant-owned order and publishes a fulfillment job.
4. A worker delivers the order to a **simulated** brand store/POS endpoint and records the outcome.
5. A brand operator can check order status and operational health.

No actual payment or external POS integration. Store brands and traffic sizes are fictitious.

## Minimum API contract

| Endpoint | Required behavior |
|---|---|
| `GET /catalog` | Return authenticated tenant's menu |
| `POST /orders` | Create order with stable idempotency key |
| `GET /orders/{id}` | Enforce tenant scope, deny other tenants |
| `GET /health`, `GET /ready` | Distinguish liveness and readiness |
| Simulated POS receiver | Deduplicate delivery by event/order ID |

Do not accept a free-form `X-Tenant-ID` request header as authorization. Derive tenant context from validated identity and server-side mapping.

## In scope

- Deploy functionally identical dedicated/shared ECS variants using IaC.
- Tenant authorization and a persistence-layer isolation boundary.
- Controlled load experiments with raw evidence and complete cost assumptions.
- At least one tenant's live migration, validation and rollback decision.
- CloudWatch monitoring, one incident exercise and operational report.

## Out of scope

Real payments, real POS, 21 microservices, cross-account migration, multi-region active-active, complete enterprise security automation. These are optional future directions and must never be described as implemented.

## Quality gates

Define p95 targets, acceptable error rate, load profiles and cost accounting rules **before** publishing comparative conclusions. Record any inability to meet targets transparently.
