package com.ordersaas.order;

import com.ordersaas.common.TenantDatabase;
import com.ordersaas.common.SqsConfiguration;
import com.ordersaas.common.TenantSecurity;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.jdbc.DataSourceAutoConfiguration;
import org.springframework.context.annotation.Import;
import org.springframework.scheduling.annotation.EnableScheduling;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication(exclude = DataSourceAutoConfiguration.class)
@Import({TenantDatabase.class, TenantSecurity.class, SqsConfiguration.class})
@EnableScheduling
public class OrderApiApplication {
    public static void main(String[] args) {
        SpringApplication.run(OrderApiApplication.class, args);
    }
}
