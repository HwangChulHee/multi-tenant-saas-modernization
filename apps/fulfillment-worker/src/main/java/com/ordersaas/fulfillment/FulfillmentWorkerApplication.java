package com.ordersaas.fulfillment;

import com.ordersaas.common.TenantDatabase;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.jdbc.DataSourceAutoConfiguration;
import org.springframework.context.annotation.Import;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication(exclude = DataSourceAutoConfiguration.class)
@Import(TenantDatabase.class)
public class FulfillmentWorkerApplication {
    public static void main(String[] args) {
        SpringApplication.run(FulfillmentWorkerApplication.class, args);
    }
}
