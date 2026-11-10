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
ENTRYPOINT ["java", "-jar", "app.jar"]
