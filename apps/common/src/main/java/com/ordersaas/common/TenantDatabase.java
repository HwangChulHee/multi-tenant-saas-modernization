package com.ordersaas.common;

import java.util.Arrays;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.Set;

import com.zaxxer.hikari.HikariConfig;
import com.zaxxer.hikari.HikariDataSource;
import org.springframework.boot.actuate.health.Health;
import org.springframework.boot.actuate.health.HealthIndicator;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.env.Environment;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.support.JdbcTransactionManager;
import org.springframework.transaction.support.TransactionTemplate;

@Configuration(proxyBeanMethods = false)
public class TenantDatabase {
    @Bean
    TenantStores tenantStores(Environment env) {
        return new TenantStores(env);
    }

    @Bean
    HealthIndicator dbHealthIndicator(TenantStores stores) {
        return () -> {
            try {
                for (String brand : stores.brands()) {
                    stores.get(brand).jdbc().queryForObject("SELECT 1", Integer.class);
                }
                return Health.up().build();
            } catch (RuntimeException error) {
                return Health.down().build();
            }
        };
    }

    public record Store(JdbcTemplate jdbc, TransactionTemplate transactions) {}

    public static final class TenantStores implements AutoCloseable {
        private static final Set<String> BRANDS = Set.of("brand_a", "brand_b", "brand_c");
        private final Map<String, HikariDataSource> pools = new LinkedHashMap<>();
        private final Map<String, Store> stores = new LinkedHashMap<>();

        private TenantStores(Environment env) {
            var enabled = Arrays.stream(env.getRequiredProperty("app.active-brands").split(",", -1))
                    .map(String::trim).distinct().toList();
            if (!BRANDS.containsAll(enabled)) {
                throw new IllegalArgumentException("ACTIVE_BRANDS must contain known brand identifiers");
            }
            String service = env.getRequiredProperty("app.db-role");
            try {
                for (String brand : enabled) {
                    HikariConfig config = new HikariConfig();
                    config.setJdbcUrl(env.getRequiredProperty("DB_URL"));
                    config.setUsername(brand + "_" + service);
                    config.setPassword(env.getRequiredProperty("DB_" + brand.toUpperCase(java.util.Locale.ROOT) + "_PASSWORD"));
                    config.setSchema(brand);
                    config.setPoolName(service + "-" + brand);
                    config.setMaximumPoolSize(4);
                    config.setMinimumIdle(0);
                    config.setConnectionTimeout(2000);
                    config.setInitializationFailTimeout(-1);
                    HikariDataSource pool = new HikariDataSource(config);
                    pools.put(brand, pool);
                    stores.put(brand, new Store(new JdbcTemplate(pool), new TransactionTemplate(new JdbcTransactionManager(pool))));
                }
            } catch (RuntimeException error) {
                close();
                throw error;
            }
        }

        public Set<String> brands() {
            return java.util.Collections.unmodifiableSet(stores.keySet());
        }

        public Store get(String brand) {
            Store store = stores.get(brand);
            if (store == null) {
                throw new IllegalArgumentException("Inactive brand");
            }
            return store;
        }

        @Override
        public void close() {
            pools.values().forEach(HikariDataSource::close);
        }
    }
}
