FROM golang:1.21-alpine AS builder

WORKDIR /src

COPY go.mod go.sum ./
RUN go mod download

COPY . .
RUN CGO_ENABLED=0 GOOS=linux go build -o /out/poller ./cmd/poller

FROM alpine:3.19

WORKDIR /app
COPY --from=builder /out/poller /usr/local/bin/poller

ENV BACKEND_API_URL=http://localhost:5000 \
    POLLER_API_KEY=change-me \
    DISCOVERY_INTERVAL=15

CMD ["poller"]
