package com.ordersaas.common;

import java.net.URI;
import java.time.Duration;
import java.util.LinkedHashMap;
import java.util.Locale;
import java.util.Map;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.env.Environment;
import software.amazon.awssdk.http.urlconnection.UrlConnectionHttpClient;
import software.amazon.awssdk.regions.Region;
import software.amazon.awssdk.services.sqs.SqsClient;

@Configuration(proxyBeanMethods = false)
public class SqsConfiguration {
    @Bean
    SqsClient sqsClient(Environment env) {
        var client = SqsClient.builder()
                .region(Region.of(env.getRequiredProperty("AWS_REGION")))
                .httpClientBuilder(UrlConnectionHttpClient.builder())
                .overrideConfiguration(config -> config.apiCallTimeout(Duration.ofSeconds(5))
                        .apiCallAttemptTimeout(Duration.ofSeconds(3)));
        String endpoint = env.getProperty("SQS_ENDPOINT", "");
        if (!endpoint.isBlank()) {
            client.endpointOverride(URI.create(endpoint));
        }
        return client.build();
    }

    @Bean
    TenantQueues tenantQueues(TenantDatabase.TenantStores stores, Environment env) {
        Map<String, String> urls = new LinkedHashMap<>();
        for (String brand : stores.brands()) {
            String url = env.getRequiredProperty("SQS_" + brand.toUpperCase(Locale.ROOT) + "_QUEUE_URL");
            if (url.isBlank() || urls.containsValue(url)) {
                throw new IllegalArgumentException("Each active brand must have its own SQS queue URL");
            }
            urls.put(brand, url);
        }
        return new TenantQueues(Map.copyOf(urls));
    }

    public record TenantQueues(Map<String, String> urls) {}
}
