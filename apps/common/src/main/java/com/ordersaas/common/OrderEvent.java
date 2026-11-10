package com.ordersaas.common;

import java.util.UUID;

public record OrderEvent(UUID eventId, UUID orderId, String tenantId, UUID requestId) {
    public boolean hasIdentifiers() {
        return eventId != null && orderId != null && tenantId != null && requestId != null;
    }
}
