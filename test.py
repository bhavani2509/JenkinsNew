GitHub Actions (workflow_dispatch)
        ↓
Checkout source code
        ↓
Install Docker on runner
        ↓
Fetch secrets from Vault
        ↓
Build k6 JS bundle
        ↓
Build custom k6 Docker image (xk6)
        ↓
Run k6 load test in Docker
        ↓
Send data to:
   - Elasticsearch (results)
   - Prometheus (metrics)
        ↓
Pipeline completes (success/failure)


#!/usr/bin/env bash
set -e

#############################################
# Default values
#############################################
BASE_URL=${BASE_URL:-http://test-app:3000}

ELASTIC_USER=${ELASTIC_USER:-elastic}
ELASTIC_PASSWORD=${ELASTIC_PASSWORD:-secret}
ELASTICSEARCH_URL=${ELASTICSEARCH_URL:-http://${ELASTIC_USER}:${ELASTIC_PASSWORD}@elasticsearch:9200}
ELASTICSEARCH_INDEX=${ELASTICSEARCH_INDEX:-k6-index}

#############################################
# Build k6 JS bundle
#############################################
echo "===> Building k6 test bundle..."
npm run build

#############################################
# Build custom k6 Docker image
#############################################
echo "===> Building custom k6 Docker image with Elastic + Prometheus support..."
docker build \
  -t ${K6_IMAGE_NAME}:${K6_IMAGE_TAG} \
  -f Dockerfile.runner .

#############################################
# Run k6 inside Docker
#############################################
echo "===> Running k6 test in Docker..."

docker run --rm \
  --add-host=host.docker.internal:host-gateway \
  -v "$(pwd)/dist:/dist:ro" \
  -e BASE_URL="${BASE_URL}" \
  -e VUS="${VUS}" \
  -e DURATION="${DURATION}" \
  -e ESP_ENV="${ESP_ENV}" \
  -e TARGET_USERNAME="${TARGET_USERNAME}" \
  -e TARGET_PASSWORD="${TARGET_PASSWORD}" \
  -e K6_OUT="output-elasticsearch,xk6-prometheus-rw" \
  -e K6_ELASTICSEARCH_URL="${ELASTICSEARCH_URL}" \
  -e K6_ELASTICSEARCH_INDEX_NAME="${ELASTICSEARCH_INDEX}" \
  -e K6_PROMETHEUS_RW_SERVER_URL="${PROM_REMOTE_WRITE_URL}" \
  ${K6_IMAGE_NAME}:${K6_IMAGE_TAG} \
  run /dist/test.js




  name: k6 End-to-End CI/CD

on:
  workflow_dispatch:
    inputs:
      ESP_ENV:
        description: Environment
        required: true
        type: choice
        options: [non-prod, prod]
        default: non-prod

      VUS:
        description: Virtual users
        required: true
        default: "5"

      DURATION:
        description: Test duration
        required: true
        default: "30s"

permissions:
  contents: read

concurrency:
  group: k6-${{ github.ref }}-${{ github.event.inputs.ESP_ENV }}
  cancel-in-progress: false

jobs:
  k6_ci_cd:
    runs-on: [custom-esp-runner]
    environment: esp_${{ github.event.inputs.ESP_ENV }}

    env:
      # Inputs → test.js (__ENV.*)
      ESP_ENV: ${{ github.event.inputs.ESP_ENV }}
      VUS: ${{ github.event.inputs.VUS }}
      DURATION: ${{ github.event.inputs.DURATION }}

      # Docker
      K6_IMAGE_NAME: k6-custom-runner
      K6_IMAGE_TAG: latest

      # Elasticsearch
      ELASTIC_USER: ${{ vars.ELASTIC_USER }}
      ELASTIC_PASSWORD: ${{ secrets.ELASTIC_PASSWORD }}
      ELASTICSEARCH_URL: ${{ vars.ELASTICSEARCH_URL }}
      ELASTICSEARCH_INDEX: k6-index

      # Prometheus
      PROM_REMOTE_WRITE_URL: ${{ vars.PROM_REMOTE_WRITE_URL }}

    steps:
      # -------------------------
      # Checkout
      # -------------------------
      - name: Checkout
        uses: actions/checkout@v4

      # -------------------------
      # Docker
      # -------------------------
      - name: Install Docker (if missing)
        shell: bash
        run: |
          set -e
          if ! command -v docker >/dev/null 2>&1; then
            curl -fsSL https://get.docker.com | sudo sh
          fi
          docker version

      # -------------------------
      # Vault Secrets (Auth creds for test.js)
      # -------------------------
      - name: Read secrets from Vault
        uses: hashicorp/vault-action@v2.4.1
        with:
          url: https://vault.cluster.us-vault-prod.azure.lnrsg.io/
          method: approle
          roleId: ${{ secrets.ROLE_ID }}
          secretId: ${{ secrets.ROLE_SECRET }}
          namespace: businessservices/esp/esp/${{ env.ESP_ENV }}
          exportToken: true
          secrets: |
            static_secrets/k6_target username | TARGET_USERNAME ;
            static_secrets/k6_target password | TARGET_PASSWORD ;

      # -------------------------
      # CI + CD (delegated to test.sh)
      # -------------------------
      - name: Run k6 CI/CD pipeline
        shell: bash
        env:
          BASE_URL: https://ws.us-esp-${{ env.ESP_ENV }}.azure.lnrsg.io
        run: |
          chmod +x test.sh
          ./test.sh
