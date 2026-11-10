package com.ordersaas.order;

import java.net.URI;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.util.UUID;

import com.ordersaas.common.TenantDatabase.TenantStores;
import org.slf4j.MDC;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.server.ResponseStatusException;

@RestController
class OrderController {
    private static final String FIELDS = "id, menu_id, quantity, status";
    private final TenantStores stores;

    OrderController(TenantStores stores) {
        this.stores = stores;
    }

    @PostMapping("/orders")
    ResponseEntity<Order> create(@AuthenticationPrincipal Jwt jwt, @RequestHeader("Idempotency-Key") String key,
            @RequestBody OrderRequest request) {
        if (!key.matches("[!-~]{1,128}") || request.menuId() == null || request.menuId().isBlank()
                || request.menuId().length() > 128 || request.quantity() < 1 || request.quantity() > 100) {
            throw new ResponseStatusException(HttpStatus.BAD_REQUEST, "Invalid order or idempotency key");
        }
        var store = stores.get(jwt.getClaimAsString("tenant_id"));
        return store.transactions().execute(transaction -> create(store.jdbc(), key, request));
    }

    private ResponseEntity<Order> create(JdbcTemplate jdbc, String key, OrderRequest request) {
        Order existing = byKey(jdbc, key);
        if (existing != null) {
            return replay(existing, request);
        }
        if (!Boolean.TRUE.equals(jdbc.queryForObject("SELECT EXISTS (SELECT FROM menus WHERE id = ?)",
                Boolean.class, request.menuId()))) {
            throw new ResponseStatusException(HttpStatus.BAD_REQUEST, "Unknown menu item");
        }
        var inserted = jdbc.query("""
                INSERT INTO orders (id, idempotency_key, menu_id, quantity, request_id)
                VALUES (?, ?, ?, ?, ?) ON CONFLICT (idempotency_key) DO NOTHING
                RETURNING id, menu_id, quantity, status
                """, OrderController::map, UUID.randomUUID(), key, request.menuId(), request.quantity(),
                UUID.fromString(MDC.get("request_id")));
        if (inserted.isEmpty()) {
            return replay(byKey(jdbc, key), request);
        }
        Order order = inserted.getFirst();
        return ResponseEntity.created(URI.create("/orders/" + order.id())).body(order);
    }

    @GetMapping("/orders/{id}")
    Order get(@AuthenticationPrincipal Jwt jwt, @PathVariable UUID id) {
        return stores.get(jwt.getClaimAsString("tenant_id")).jdbc()
                .query("SELECT " + FIELDS + " FROM orders WHERE id = ?", OrderController::map, id)
                .stream().findFirst().orElseThrow(() -> new ResponseStatusException(HttpStatus.NOT_FOUND));
    }

    private static Order byKey(JdbcTemplate jdbc, String key) {
        return jdbc.query("SELECT " + FIELDS + " FROM orders WHERE idempotency_key = ?", OrderController::map, key)
                .stream().findFirst().orElse(null);
    }

    private static ResponseEntity<Order> replay(Order order, OrderRequest request) {
        if (!order.menuId().equals(request.menuId()) || order.quantity() != request.quantity()) {
            throw new ResponseStatusException(HttpStatus.CONFLICT, "Idempotency key already used for another order");
        }
        return ResponseEntity.ok(order);
    }

    private static Order map(ResultSet rs, int row) throws SQLException {
        return new Order(rs.getObject("id", UUID.class), rs.getString("menu_id"), rs.getInt("quantity"),
                rs.getString("status"));
    }

    record OrderRequest(String menuId, int quantity) {}
    record Order(UUID id, String menuId, int quantity, String status) {}
}
