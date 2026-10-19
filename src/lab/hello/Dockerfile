FROM alpine:3.21
WORKDIR /app
COPY greet.sh /app/greet.sh
RUN chmod +x /app/greet.sh
ARG APP_VERSION=1.0
RUN printf '%s\n' "$APP_VERSION" > /app/version.txt
ENV GREETING=Hello
ENTRYPOINT ["/app/greet.sh"]
CMD ["student"]