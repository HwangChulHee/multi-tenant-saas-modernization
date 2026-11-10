# 03. Performance, scalability and cost experiment plan

**Status:** Protocol, **no measured results**.

## Workloads

- **Idle:** no requests while capacity is maintained.
- **Steady:** consistent, mixed catalog reads and order writes.
- **Single-tenant burst:** Brand A promotional spike while B/C keep baseline traffic.
- **All-tenant burst:** concurrent demand spike in A/B/C.
- **Failure:** terminate one worker/task or inject a failure into one shared instance.

Use identical application code, data shape, Region and per-test input. Normalize resource ceilings and availability objectives where possible. Warm up runtimes; measure sustained windows; repeat each scenario >=3 times and record environment versions and limitations.

## Primary measurements

Per tenant: request rate, p50/p95/p99 API latency, error %, successful order count, order-to-fulfillment delay, duplicate business effects (target **0**), denied cross-tenant access (target **all**). Infrastructure: ECS tasks/CPU/memory, scaling lag, SQS depth/oldest age, DB utilization, downtime during cutover.

## Hypotheses (to test, not claim)

- H1: pooling reduces duplicated idle compute at low tenant utilization.
- H2: dedicated services better limit some noisy-neighbor effects.
- H3: tenant fairness controls and more warm shared capacity trade cost against burst isolation.
- H4: progressive tenant migration can bound the interruption and protect data integrity.

## Cost comparison

Distinguish **actual AWS spend for experiments** from **modeled 30-day scenario costs**. Include Fargate or EC2 compute, ALB hourly/LCU charges, RDS, SQS, logs, NAT/endpoints, data transfer and any other deployed charge. Evaluate equal tenant count, equivalent redundancy and clear workload distributions. The crossover point is unknown until estimated from evidence.

| Scenario | Architecture | A p95 | B p95 | C p95 | Error % | Task count | Order delay | AWS cost |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| Idle | Dedicated | TBD | TBD | TBD | TBD | TBD | TBD | TBD |
| Idle | Shared | TBD | TBD | TBD | TBD | TBD | TBD | TBD |
| A burst | Dedicated | TBD | TBD | TBD | TBD | TBD | TBD | TBD |
| A burst | Shared | TBD | TBD | TBD | TBD | TBD | TBD | TBD |

## Evidence requirements

Record the k6/test scenarios, raw JSON or CSV output, metric snapshots, Terraform configuration, pricing assumptions and conclusion limitations. Do not borrow OrderServ's reported savings or scale-up improvements as our results.
