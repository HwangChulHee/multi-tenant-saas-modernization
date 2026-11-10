FROM eclipse-temurin:21-jdk AS build
WORKDIR /workspace

COPY gradlew settings.gradle build.gradle ./
COPY gradle/ gradle/
RUN ./gradlew --no-daemon --version

COPY common/ common/
COPY catalog-api/ catalog-api/
COPY order-api/ order-api/
COPY fulfillment-worker/ fulfillment-worker/
COPY mock-pos/ mock-pos/
ARG SERVICE
RUN ./gradlew --no-daemon ":${SERVICE}:bootJar" \
    && cp "${SERVICE}/build/libs/app.jar" /app.jar

FROM eclipse-temurin:21-jre-alpine
WORKDIR /app
COPY --from=build /app.jar app.jar
USER 10001:10001
HEALTHCHECK --interval=10s --timeout=4s --start-period=20s --retries=3 \
    CMD wget -q -O /dev/null "http://127.0.0.1:${SERVER_PORT}/ready" || exit 1
ENTRYPOINT ["java", "-jar", "app.jar"]
