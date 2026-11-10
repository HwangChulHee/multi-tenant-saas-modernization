package com.ordersaas.fulfillment;

import java.time.Duration;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.ordersaas.common.OrderEvent;
import com.ordersaas.common.SqsConfiguration.TenantQueues;
import com.ordersaas.common.TenantDatabase.TenantStores;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.slf4j.MDC;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.client.JdkClientHttpRequestFactory;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;
import org.springframework.web.client.RestClient;
import software.amazon.awssdk.services.sqs.SqsClient;
import software.amazon.awssdk.services.sqs.model.Message;

@Component
class FulfillmentConsumer {
    private static final Logger LOG = LoggerFactory.getLogger(FulfillmentConsumer.class);
    private final TenantStores stores;
    private final TenantQueues queues;
    private final SqsClient sqs;
    private final ObjectMapper json;
    private final RestClient pos;

    FulfillmentConsumer(TenantStores stores, TenantQueues queues, SqsClient sqs, ObjectMapper json,
            @Value("${POS_URL}") String posUrl, @Value("${POS_SHARED_TOKEN}") String posToken,
            @Value("${POS_TIMEOUT_MS:2500}") long timeout) {
        this.stores = stores;
        this.queues = queues;
        this.sqs = sqs;
        this.json = json;
        var client = java.net.http.HttpClient.newBuilder().connectTimeout(Duration.ofMillis(timeout)).build();
        var factory = new JdkClientHttpRequestFactory(client);
        factory.setReadTimeout(Duration.ofMillis(timeout));
        pos = RestClient.builder().baseUrl(posUrl).requestFactory(factory)
                .defaultHeader("X-POS-Token", posToken).build();
    }

    @Scheduled(fixedDelayString = "${WORKER_POLL_MS:250}")
    void poll() {
        queues.urls().forEach((brand, queue) -> {
            try (var tenant = MDC.putCloseable("tenant_id", brand)) {
                try {
                    var messages = sqs.receiveMessage(receive -> receive.queueUrl(queue)
                            .maxNumberOfMessages(1).waitTimeSeconds(1)).messages();
                    for (Message message : messages) {
                        process(brand, queue, message);
                    }
                } catch (RuntimeException | JsonProcessingException error) {
                    LOG.warn("Fulfillment attempt failed ({})", error.getClass().getSimpleName());
                }
            }
        });
    }

    private void process(String brand, String queue, Message message) throws JsonProcessingException {
        OrderEvent event = json.readValue(message.body(), OrderEvent.class);
        if (event == null || !event.hasIdentifiers() || !brand.equals(event.tenantId())) {
            LOG.warn("Rejected event with invalid identifiers or tenant");
            return;
        }
        var store = stores.get(brand);
        try (var request = MDC.putCloseable("request_id", event.requestId().toString())) {
            boolean handled = Boolean.TRUE.equals(store.transactions().execute(transaction -> deliver(store.jdbc(), event)));
            if (handled) {
                sqs.deleteMessage(delete -> delete.queueUrl(queue).receiptHandle(message.receiptHandle()));
            }
        }
    }

    private boolean deliver(JdbcTemplate jdbc, OrderEvent event) {
        var statuses = jdbc.query("""
                SELECT o.status FROM orders o JOIN outbox_events e ON e.order_id = o.id
                WHERE o.id = ? AND e.event_id = ? AND o.request_id = ? FOR UPDATE OF o
                """, (rs, row) -> rs.getString(1), event.orderId(), event.eventId(), event.requestId());
        if (statuses.isEmpty()) {
            LOG.warn("Rejected event without matching order and outbox row");
            return false;
        }
        if (Boolean.TRUE.equals(jdbc.queryForObject("SELECT EXISTS (SELECT FROM processed_events WHERE event_id = ?)",
                Boolean.class, event.eventId()))) {
            LOG.info("Acknowledging an already processed event");
            return true;
        }
        if (!"PENDING".equals(statuses.getFirst())) {
            throw new IllegalStateException("Order status and fulfillment ledger disagree");
        }
        pos.post().uri("/deliveries").body(event).retrieve().toBodilessEntity();
        jdbc.update("INSERT INTO processed_events (event_id, order_id) VALUES (?, ?)", event.eventId(), event.orderId());
        jdbc.update("UPDATE orders SET status = 'FULFILLED' WHERE id = ?", event.orderId());
        LOG.info("Fulfillment recorded");
        return true;
    }
}
