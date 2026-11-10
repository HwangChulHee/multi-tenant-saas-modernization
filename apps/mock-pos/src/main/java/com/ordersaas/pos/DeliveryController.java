package com.ordersaas.pos;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.Set;

import com.ordersaas.common.OrderEvent;
import org.slf4j.LoggerFactory;
import org.slf4j.MDC;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.HttpStatus;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

@RestController
class DeliveryController {
    private final JdbcTemplate jdbc;
    private final byte[] token;
    private final int failFirst;
    private final long delay;

    DeliveryController(JdbcTemplate jdbc, @Value("${POS_SHARED_TOKEN}") String token,
            @Value("${POS_FAIL_FIRST:0}") int failFirst, @Value("${POS_DELAY_MS:0}") long delay) {
        if (token.length() < 32 || failFirst < 0 || delay < 0) {
            throw new IllegalArgumentException("Invalid POS token or simulation parameters");
        }
        this.jdbc = jdbc;
        this.token = token.getBytes(StandardCharsets.UTF_8);
        this.failFirst = failFirst;
        this.delay = delay;
    }

    @PostMapping("/deliveries")
    void deliver(@RequestHeader(value = "X-POS-Token", defaultValue = "") String provided,
            @RequestBody OrderEvent event) throws InterruptedException {
        if (!MessageDigest.isEqual(token, provided.getBytes(StandardCharsets.UTF_8))) {
            throw new ResponseStatusException(HttpStatus.UNAUTHORIZED);
        }
        if (!event.hasIdentifiers() || !Set.of("brand_a", "brand_b", "brand_c").contains(event.tenantId())) {
            throw new ResponseStatusException(HttpStatus.BAD_REQUEST);
        }
        try (var request = MDC.putCloseable("request_id", event.requestId().toString());
                var tenant = MDC.putCloseable("tenant_id", event.tenantId())) {
            var deliveries = jdbc.query("""
                    INSERT INTO mock_pos.deliveries AS d (event_id, tenant_id, order_id, request_id, attempts, accepted_at)
                    VALUES (?, ?, ?, ?, 1, CASE WHEN ? = 0 THEN clock_timestamp() END)
                    ON CONFLICT (event_id) DO UPDATE SET attempts = d.attempts + 1,
                        accepted_at = COALESCE(d.accepted_at, CASE WHEN d.attempts + 1 > ? THEN clock_timestamp() END)
                    WHERE d.tenant_id = EXCLUDED.tenant_id AND d.order_id = EXCLUDED.order_id
                        AND d.request_id = EXCLUDED.request_id
                    RETURNING attempts, accepted_at IS NOT NULL
                    """, (rs, row) -> new Delivery(rs.getInt(1), rs.getBoolean(2)),
                    event.eventId(), event.tenantId(), event.orderId(), event.requestId(), failFirst, failFirst);
            if (deliveries.isEmpty()) {
                throw new ResponseStatusException(HttpStatus.CONFLICT);
            }
            Delivery delivery = deliveries.getFirst();
            LoggerFactory.getLogger(DeliveryController.class).atInfo().addKeyValue("attempt", delivery.attempts())
                    .addKeyValue("accepted", delivery.accepted()).log("Mock POS delivery");
            if (delivery.attempts() == 1 && delay > 0) {
                Thread.sleep(delay);
            }
            if (!delivery.accepted()) {
                throw new ResponseStatusException(HttpStatus.SERVICE_UNAVAILABLE);
            }
        }
    }

    private record Delivery(int attempts, boolean accepted) {}
}
