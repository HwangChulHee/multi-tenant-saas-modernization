# 06. November 2026 implementation roadmap

**Status:** Planned milestones; not evidence of completion.

| Dates (KST) | Milestone | Exit criteria |
|---|---|---|
| Nov 10–13 | Minimal order domain and dedicated baseline | Working Catalog/Order/Worker, tenant fixtures, deploy instructions |
| Nov 14–17 | Pooled ECS + tenant security | Shared deployment, authentication, persistence isolation, denied-access tests |
| Nov 18–21 | Scaling and cost experiments | Repeated comparable tests, raw per-tenant metrics, assumptions |
| Nov 22–24 | Brand A live cutover and failure drill | One verified migration wave, bounded rollback, runbook |
| Nov 25–27 | MSP-style report and job application | Architecture ADRs, final benchmark/security/cutover report |

## Priority and scope freeze

**P0:** dedicated and pooled deployments, functional parity, tenant boundaries, repeatable benchmark.

**P1:** Brand A cutover, a negative security test suite, one operational incident, rollback or safe forward-fix analysis.

**P2:** FireLens, X-Ray, Bottlerocket, EC2 warm pools, dedicated AWS roles per tenant, rich CI/CD, all-brand migration. Do not put optional services on the finished architecture diagram unless deployed and verified.

## Definition of done

- Another engineer can follow prerequisites and reproduce both environments.
- Security denied tests pass at API and data layer.
- Results include measured numbers, raw data and cost assumptions.
- One brand migration has timestamps and evidence of order integrity.
- A customer-oriented change report and cleanup instructions exist.
- AWS budget alerts and explicit `terraform destroy` / teardown are documented.
