INSERT INTO outbox_events (event_id, order_id)
SELECT gen_random_uuid(), id FROM orders WHERE status = 'PENDING'
ON CONFLICT (order_id) DO NOTHING;

CREATE INDEX outbox_pending_idx ON outbox_events (next_attempt_at, created_at)
WHERE published_at IS NULL;
