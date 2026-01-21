#!/bin/bash
set -e

########################################
# Default values
########################################
BASE_URL="http://test-app:3000"

# Toggle ELK integration (off by default)
ENABLE_ELK=${ENABLE_ELK:-false}

ELASTIC_USER="elastic"
ELASTIC_PASSWORD="secret"
ELASTICSEARCH_URL="http://${ELASTIC_USER}:${ELASTIC_PASSWORD}@elasticsearch:9200"
ELASTICSEARCH_INDEX="k6-index"

########################################
# Build custom k6 Docker image
########################################
echo "==> Building custom k6 Docker image..."
docker build -t k6-custom-runner:latest -f Dockerfile.runner .

########################################
# Decide k6 output mode
########################################
if [ "$ENABLE_ELK" = "true" ]; then
  echo "==> Running k6 with ELK outputs ENABLED"
  K6_OUT="output-elasticsearch,xk6-prometheus-rw"
else
  echo "==> Running k6 with ELK outputs DISABLED (stdout only)"
  K6_OUT="stdout"
fi

########################################
# Windows-safe path resolution (FIX)
########################################
HOST_PWD="$(cygpath -u "$(pwd)")"
HOST_DIST_PATH="$HOST_PWD/dist"

########################################
# Run k6 test (single-line execution)
########################################
echo "==> Running k6 test in Docker..."

docker run --rm --add-host=host.docker.internal:host-gateway \
-v "$HOST_DIST_PATH:/dist:ro" \
-e BASE_URL="$BASE_URL" \
-e K6_OUT="$K6_OUT" \
k6-custom-runner:latest run /dist/test.js



# -------- Builder stage --------
FROM golang:1.25-alpine AS builder

RUN apk --no-cache add git ca-certificates

# Install xk6
RUN CGO_ENABLED=0 go install go.k6.io/xk6/cmd/xk6@latest

# Build custom k6 with Elasticsearch + Prometheus outputs
RUN CGO_ENABLED=0 xk6 build \
  --with github.com/elastic/xk6-output-elasticsearch \
  --with github.com/grafana/xk6-output-prometheus-remote \
  --output /tmp/k6

# -------- Runtime stage --------
FROM alpine:3.21

RUN apk add --no-cache ca-certificates && \
    adduser -D -u 12345 -g 12345 k6

COPY --from=builder /tmp/k6 /usr/bin/k6

USER 12345
WORKDIR /home/k6

ENTRYPOINT ["k6"]

import http from 'k6/http';
import { check, sleep } from 'k6';

export const options = {
  vus: 5,
  duration: '30s',
};

export default function () {
  const res = http.get('https://test.k6.io');

  check(res, {
    'status is 200': (r) => r.status === 200,
  });

  sleep(1);
}

