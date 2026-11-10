package com.ordersaas.order;

import java.util.UUID;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.ordersaas.common.OrderEvent;
import com.ordersaas.common.SqsConfiguration.TenantQueues;
import com.ordersaas.common.TenantDatabase.TenantStores;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.slf4j.MDC;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;
import software.amazon.awssdk.core.exception.SdkException;
import software.amazon.awssdk.services.sqs.SqsClient;

@Component
class OutboxPublisher {
    private static final Logger LOG = LoggerFactory.getLogger(OutboxPublisher.class);
    private final TenantStores stores;
    private final TenantQueues queues;
    private final SqsClient sqs;
    private final ObjectMapper json;

    OutboxPublisher(TenantStores stores, TenantQueues queues, SqsClient sqs, ObjectMapper json) {
        this.stores = stores;
        this.queues = queues;
        this.sqs = sqs;
        this.json = json;
    }

    @Scheduled(fixedDelayString = "${OUTBOX_POLL_MS:500}")
    void publish() {
        queues.urls().forEach((brand, queue) -> {
            var store = stores.get(brand);
            try (var tenant = MDC.putCloseable("tenant_id", brand)) {
                try {
                    store.transactions().executeWithoutResult(transaction -> publishOne(store.jdbc(), brand, queue));
                } catch (RuntimeException error) {
                    LOG.warn("Outbox transaction failed ({})", error.getClass().getSimpleName());
                }
            }
        });
    }

    private void publishOne(JdbcTemplate jdbc, String brand, String queue) {
        var pending = jdbc.query("""
                SELECT e.event_id, e.order_id, o.request_id
                FROM outbox_events e JOIN orders o ON o.id = e.order_id
                WHERE e.published_at IS NULL AND e.next_attempt_at <= now()
                ORDER BY e.next_attempt_at, e.created_at
                LIMIT 1 FOR UPDATE OF e SKIP LOCKED
                """, (rs, row) -> new OrderEvent(rs.getObject(1, UUID.class), rs.getObject(2, UUID.class),
                        brand, rs.getObject(3, UUID.class)));
        if (pending.isEmpty()) {
            return;
        }
        OrderEvent event = pending.getFirst();
        try (var request = MDC.putCloseable("request_id", event.requestId().toString())) {
            try {
                String body = json.writeValueAsString(event);
                sqs.sendMessage(message -> message.queueUrl(queue).messageBody(body));
            } catch (SdkException | JsonProcessingException error) {
                jdbc.update("""
                        UPDATE outbox_events
                        SET attempts = attempts + 1,
                            next_attempt_at = clock_timestamp() + make_interval(secs => LEAST(attempts + 1, 30))
                        WHERE event_id = ?
                        """, event.eventId());
                LOG.warn("Outbox publish deferred ({})", error.getClass().getSimpleName());
                return;
            }
            jdbc.update("UPDATE outbox_events SET published_at = clock_timestamp() WHERE event_id = ?", event.eventId());
            LOG.info("Outbox event sent");
        }
    }
}
