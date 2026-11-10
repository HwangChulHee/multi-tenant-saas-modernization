package com.ordersaas.catalog;

import java.util.List;

import com.ordersaas.common.TenantDatabase.TenantStores;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
class CatalogController {
    private final TenantStores stores;

    CatalogController(TenantStores stores) {
        this.stores = stores;
    }

    @GetMapping("/catalog")
    List<MenuItem> catalog(@AuthenticationPrincipal Jwt jwt) {
        return stores.get(jwt.getClaimAsString("tenant_id")).jdbc().query(
                "SELECT id, name, price_cents FROM menus ORDER BY id",
                (rs, row) -> new MenuItem(rs.getString(1), rs.getString(2), rs.getInt(3)));
    }

    record MenuItem(String id, String name, int priceCents) {}
}
