package com.ordersaas.common;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.UUID;
import javax.crypto.spec.SecretKeySpec;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.slf4j.LoggerFactory;
import org.slf4j.MDC;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.env.Environment;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.security.oauth2.core.DelegatingOAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.OAuth2TokenValidatorResult;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.security.oauth2.jwt.JwtIssuerValidator;
import org.springframework.security.oauth2.jwt.JwtTimestampValidator;
import org.springframework.security.oauth2.jwt.NimbusJwtDecoder;
import org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationToken;
import org.springframework.security.oauth2.server.resource.web.authentication.BearerTokenAuthenticationFilter;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.web.filter.OncePerRequestFilter;

@Configuration(proxyBeanMethods = false)
public class TenantSecurity {
    @Bean
    JwtDecoder jwtDecoder(Environment env, TenantDatabase.TenantStores stores) {
        String issuer = env.getRequiredProperty("JWT_ISSUER");
        String audience = env.getRequiredProperty("JWT_AUDIENCE");
        String jwks = env.getProperty("JWT_JWK_SET_URI", "");
        NimbusJwtDecoder decoder;
        if (!jwks.isBlank()) {
            decoder = NimbusJwtDecoder.withJwkSetUri(jwks).build();
        } else {
            byte[] key = env.getRequiredProperty("LOCAL_JWT_SECRET").getBytes(StandardCharsets.UTF_8);
            if (key.length < 32) {
                throw new IllegalArgumentException("LOCAL_JWT_SECRET must contain at least 32 bytes");
            }
            decoder = NimbusJwtDecoder.withSecretKey(new SecretKeySpec(key, "HmacSHA256")).build();
        }
        decoder.setJwtValidator(new DelegatingOAuth2TokenValidator<>(
                new JwtTimestampValidator(Duration.ZERO), new JwtIssuerValidator(issuer), jwt -> {
                    Object tenant = jwt.getClaims().get("tenant_id");
                    if (jwt.getExpiresAt() != null && jwt.getAudience() != null && jwt.getAudience().contains(audience)
                            && tenant instanceof String brand && stores.brands().contains(brand)) {
                        return OAuth2TokenValidatorResult.success();
                    }
                    return OAuth2TokenValidatorResult.failure(new OAuth2Error("invalid_token"));
                }));
        return decoder;
    }

    @Bean
    SecurityFilterChain tenantEndpoints(HttpSecurity http) throws Exception {
        return http.csrf(csrf -> csrf.disable())
                .sessionManagement(sessions -> sessions.sessionCreationPolicy(SessionCreationPolicy.STATELESS))
                .authorizeHttpRequests(rules -> rules.requestMatchers("/health", "/ready", "/error").permitAll()
                        .anyRequest().authenticated())
                .oauth2ResourceServer(oauth -> oauth.jwt(Customizer.withDefaults()))
                .addFilterAfter(new RequestLog(), BearerTokenAuthenticationFilter.class)
                .build();
    }

    private static final class RequestLog extends OncePerRequestFilter {
        @Override
        protected void doFilterInternal(HttpServletRequest request, HttpServletResponse response, FilterChain chain)
                throws ServletException, IOException {
            String id = UUID.randomUUID().toString();
            response.setHeader("X-Request-ID", id);
            MDC.put("request_id", id);
            boolean authenticated = SecurityContextHolder.getContext().getAuthentication() instanceof JwtAuthenticationToken;
            if (SecurityContextHolder.getContext().getAuthentication() instanceof JwtAuthenticationToken auth) {
                MDC.put("tenant_id", auth.getToken().getClaimAsString("tenant_id"));
            }
            long start = System.nanoTime();
            try {
                chain.doFilter(request, response);
            } finally {
                if (authenticated) {
                    LoggerFactory.getLogger(TenantSecurity.class).atInfo()
                            .addKeyValue("duration_ms", (System.nanoTime() - start) / 1_000_000)
                            .addKeyValue("status", response.getStatus()).log("API request");
                }
                MDC.remove("tenant_id");
                MDC.remove("request_id");
            }
        }
    }
}
