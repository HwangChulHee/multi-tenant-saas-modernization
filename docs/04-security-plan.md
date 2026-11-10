# 04. Tenant isolation and security test plan

**Status:** Design and negative-test plan; not a certification.

## Threat model

- Brand A reads or changes Brand B orders or catalog data.
- Forged tenant headers or manipulated tokens switch the request's tenant context.
- Shared workers process messages under the wrong tenant identity.
- An overly privileged ECS task role grants access beyond intended AWS resources.
- Pooled resources lead to availability interference / noisy neighbor.
- Logs or monitoring traces disclose sensitive data.

## Security controls

1. **Identity:** validate token signature, issuer, audience and expiration. Resolve the brand/tenant server-side from trusted claims and membership.
2. **API:** all reads/writes require a trusted tenant context. Define stable 403/404 behavior for unauthorized IDs.
3. **PostgreSQL:** use properly tested tenant isolation such as RLS with non-bypass runtime roles. Set tenant context transaction-locally if connection pooling is used; verify it cannot bleed between requests.
4. **SQS/worker:** validate trusted tenant-to-order associations, use stable idempotency keys, reject invalid jobs and route poison messages to DLQ.
5. **AWS boundary:** private ECS tasks, least-privilege task roles, separate execution roles, Secrets Manager, TLS, CloudTrail, narrowly scoped security groups.
6. **Observability:** record denied operations and policy changes without secrets or actual customer data.

## Negative tests

| Action | Expected result |
|---|---|
| A credential reads B order | Denied |
| A credential edits B catalog | Denied |
| `X-Tenant-ID: B` forged by A | Ignored / denied |
| DB connection reused across tenants | No prior tenant's rows visible |
| Worker message with conflicting tenant/order IDs | Rejected, safely logged |
| Task requests unapproved secret | AWS AccessDenied |
| SQS redelivers an order event | Only one business fulfillment effect |

Retain redacted evidence, HTTP results, PostgreSQL checks and AWS audit event references. Testing uses synthetic accounts/data only.
