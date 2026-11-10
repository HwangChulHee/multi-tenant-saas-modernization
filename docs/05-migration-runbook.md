# 05. Progressive tenant migration runbook

**Status:** Proposed; times, interruption and reconciliation behavior require live validation.

## Non-negotiable invariants

- At most **one authoritative write path** per tenant.
- Idempotency keys protect order creation and downstream fulfillment.
- No missing orders, no mixed-tenant records, no silently lost queue work.
- Routing rollback after the target starts accepting writes is **not automatically safe**.

## Proposed wave: Brand A

0. **Prechecks:** record baseline metrics, tenant ownership, deployment versions, DB backups, queue status, SLO/rollback thresholds.
1. **Read-only validation:** deploy shared services; shadow or canary *reads* only; avoid cross-tenant cache collisions.
2. **Seed target data:** copy Brand A records, compare counts/keys/checksums. If continuing source writes, define CDC or a short stopped-writes reconciliation phase.
3. **Quiesce:** temporarily stop Brand A order writes; drain or pause A workers; verify SQS messages and in-flight work.
4. **Reconcile:** verify final tenant data and outstanding fulfillment jobs. Guarantee a single active consumer/writer per tenant.
5. **Cut over:** move Brand A routing to shared API, enable shared writes/worker, watch p95, 5xx, authorized traffic, order counts and SQS delays.
6. **Evaluate:** allow Brand B/C to remain dedicated; record change timeline and go/no-go result.

## Rollback boundaries

- **Before target writes:** revert routing and restart old path after ensuring Source remains authoritative.
- **After target writes:** reverse replication, event replay or explicit lossless reconciliation is required. If unavailable, halt writes and **forward-fix** instead of claiming an instant DNS rollback.
- **Tenant data leak or security failure:** stop affected route, collect audit evidence and follow incident response procedure.

## Migration evidence

Customer change plan, approval/go-no-go checklist, timestamped actions, tenant order inventory, in-flight queue reconciliation, error/latency charts, security negative tests, rollback decision log and post-change verification.
