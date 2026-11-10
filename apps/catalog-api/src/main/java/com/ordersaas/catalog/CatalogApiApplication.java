package com.ordersaas.catalog;

import com.ordersaas.common.TenantDatabase;
import com.ordersaas.common.TenantSecurity;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.jdbc.DataSourceAutoConfiguration;
import org.springframework.context.annotation.Import;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication(exclude = DataSourceAutoConfiguration.class)
@Import({TenantDatabase.class, TenantSecurity.class})
public class CatalogApiApplication {
    public static void main(String[] args) {
        SpringApplication.run(CatalogApiApplication.class, args);
    }
}
