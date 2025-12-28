# =============================================================================
# S.S.I. SHADOW — MAKEFILE
# ENTERPRISE EDITION
# =============================================================================

.PHONY: help setup dev test lint deploy clean

# Default target
help:
	@echo "S.S.I. SHADOW - Available Commands"
	@echo "=============================================="
	@echo ""
	@echo "Development:"
	@echo "  make setup      - Initial project setup"
	@echo "  make dev        - Start development environment"
	@echo "  make dev-api    - Start API server locally"
	@echo "  make dev-worker - Start Worker locally"
	@echo ""
	@echo "Testing:"
	@echo "  make test       - Run all tests"
	@echo "  make test-cov   - Run tests with coverage"
	@echo "  make lint       - Run linters"
	@echo ""
	@echo "Database:"
	@echo "  make db-migrate - Run BigQuery migrations"
	@echo "  make dbt-run    - Run dbt transformations"
	@echo "  make dbt-test   - Run dbt tests"
	@echo ""
	@echo "Deployment:"
	@echo "  make build      - Build all components"
	@echo "  make deploy     - Deploy to production"
	@echo "  make deploy-staging - Deploy to staging"
	@echo "  make rollback   - Rollback last deployment"
	@echo ""
	@echo "Docker:"
	@echo "  make docker-build - Build Docker image"
	@echo "  make docker-up    - Start Docker containers"
	@echo "  make docker-down  - Stop Docker containers"
	@echo "  make docker-logs  - View container logs"
	@echo ""
	@echo "Utilities:"
	@echo "  make clean      - Clean build artifacts"
	@echo "  make docs       - Generate documentation"
	@echo ""

# =============================================================================
# SETUP
# =============================================================================

setup:
	@./setup.sh

install:
	pip install -r requirements.txt
	cd workers/gateway && npm install

# =============================================================================
# DEVELOPMENT
# =============================================================================

dev: docker-up
	@echo "Development environment started"
	@echo "API: http://localhost:8000"
	@echo "Worker: http://localhost:8787"

dev-api:
	cd api && uvicorn gateway:app --reload --host 0.0.0.0 --port 8000

dev-worker:
	cd workers/gateway && npx wrangler dev

# =============================================================================
# TESTING
# =============================================================================

test:
	pytest tests/ -v

test-cov:
	pytest tests/ -v --cov=shadow --cov=automation --cov=integrations --cov-report=html
	@echo "Coverage report: htmlcov/index.html"

test-worker:
	cd workers/gateway && npm test

lint:
	@echo "Running Python linters..."
	black --check shadow/ automation/ integrations/ functions/ api/ monitoring/ experiments/
	flake8 shadow/ automation/ integrations/ functions/ api/ --max-line-length=120
	@echo "Running TypeScript linter..."
	cd workers/gateway && npm run lint || true
	@echo "Linting complete"

format:
	black shadow/ automation/ integrations/ functions/ api/ monitoring/ experiments/
	isort shadow/ automation/ integrations/ functions/ api/ monitoring/ experiments/

typecheck:
	mypy shadow/ --ignore-missing-imports

# =============================================================================
# DATABASE
# =============================================================================

db-migrate:
	@echo "Running BigQuery migrations..."
	@for file in bigquery/*.sql; do \
		echo "Executing $$file..."; \
		bq query --use_legacy_sql=false < "$$file" || true; \
	done
	@echo "Migrations complete"

dbt-run:
	cd dbt && dbt run

dbt-test:
	cd dbt && dbt test

dbt-docs:
	cd dbt && dbt docs generate && dbt docs serve

# =============================================================================
# BUILD
# =============================================================================

build: build-worker build-docker

build-worker:
	@echo "Building Worker..."
	cd workers/gateway && npm run build

build-docker:
	@echo "Building Docker image..."
	docker build -t ssi-shadow:latest .

# =============================================================================
# DEPLOYMENT
# =============================================================================

deploy: deploy-worker deploy-functions db-migrate dbt-run
	@echo "Deployment complete!"

deploy-staging:
	cd workers/gateway && npx wrangler deploy --env staging
	@echo "Deployed to staging"

deploy-worker:
	cd workers/gateway && npx wrangler deploy --env production
	@echo "Worker deployed to production"

deploy-functions:
	@echo "Deploying Cloud Functions..."
	cd functions && \
	for func in update_identity_graph trigger_model_training sync_platform_costs check_kill_switch cleanup_old_data generate_daily_report update_predictions; do \
		gcloud functions deploy $$func \
			--runtime python311 \
			--trigger-http \
			--allow-unauthenticated \
			--region $(GCP_REGION) \
			--set-env-vars GCP_PROJECT_ID=$(GCP_PROJECT_ID) || true; \
	done

rollback:
	cd workers/gateway && npx wrangler rollback --env production
	@echo "Rolled back to previous version"

# =============================================================================
# DOCKER
# =============================================================================

docker-build:
	docker build -t ssi-shadow:latest .

docker-up:
	docker-compose up -d

docker-down:
	docker-compose down

docker-logs:
	docker-compose logs -f

docker-shell:
	docker-compose exec shadow /bin/bash

# =============================================================================
# UTILITIES
# =============================================================================

clean:
	@echo "Cleaning build artifacts..."
	rm -rf __pycache__ .pytest_cache .coverage htmlcov
	rm -rf shadow/__pycache__ automation/__pycache__ integrations/__pycache__
	rm -rf workers/gateway/dist workers/gateway/node_modules/.cache
	rm -rf dbt/target dbt/dbt_packages
	@echo "Clean complete"

docs:
	@echo "Generating documentation..."
	cd api && python -c "from gateway import app; import json; print(json.dumps(app.openapi(), indent=2))" > ../docs/openapi.json
	@echo "API docs generated: docs/openapi.json"

# Shadow commands
shadow-analyze:
	python -m shadow.engine_v2 --keywords $(KEYWORDS) --project $(GCP_PROJECT_ID)

shadow-train:
	python -m ml.mlops_pipeline --project $(GCP_PROJECT_ID) --action train --force

shadow-report:
	python -m monitoring.observability --project $(GCP_PROJECT_ID) --action report

# A/B Testing
ab-simulate:
	python -m experiments.ab_testing --action simulate --users 10000

# =============================================================================
# VARIABLES
# =============================================================================

GCP_PROJECT_ID ?= $(shell grep GCP_PROJECT_ID .env | cut -d '=' -f2)
GCP_REGION ?= us-central1
KEYWORDS ?= suplemento,emagrecimento

# =============================================================================
# KUBERNETES & HELM
# =============================================================================

K8S_NAMESPACE ?= ssi-shadow
HELM_RELEASE ?= ssi-shadow
HELM_CHART ?= ./k8s/helm/ssi-shadow

# Docker Registry
DOCKER_REGISTRY ?= gcr.io/$(GCP_PROJECT_ID)
DOCKER_IMAGE ?= ssi-shadow
DOCKER_TAG ?= $(shell git rev-parse --short HEAD)

# Build and push Docker images
docker-build-prod:
	docker build \
		-f Dockerfile.production \
		-t $(DOCKER_REGISTRY)/$(DOCKER_IMAGE):$(DOCKER_TAG) \
		-t $(DOCKER_REGISTRY)/$(DOCKER_IMAGE):latest \
		--build-arg BUILD_DATE=$(shell date -u +'%Y-%m-%dT%H:%M:%SZ') \
		--build-arg GIT_COMMIT=$(shell git rev-parse HEAD) \
		--build-arg VERSION=$(DOCKER_TAG) \
		.

docker-push:
	docker push $(DOCKER_REGISTRY)/$(DOCKER_IMAGE):$(DOCKER_TAG)
	docker push $(DOCKER_REGISTRY)/$(DOCKER_IMAGE):latest

docker-build-push: docker-build-prod docker-push

# Multi-arch build
docker-buildx:
	docker buildx build \
		--platform linux/amd64,linux/arm64 \
		-f Dockerfile.production \
		-t $(DOCKER_REGISTRY)/$(DOCKER_IMAGE):$(DOCKER_TAG) \
		-t $(DOCKER_REGISTRY)/$(DOCKER_IMAGE):latest \
		--push \
		.

# Helm commands
helm-deps:
	cd $(HELM_CHART) && helm dependency update

helm-lint:
	helm lint $(HELM_CHART) -f $(HELM_CHART)/values.yaml

helm-template:
	helm template $(HELM_RELEASE) $(HELM_CHART) \
		-f $(HELM_CHART)/values.yaml \
		--namespace $(K8S_NAMESPACE)

helm-template-staging:
	helm template $(HELM_RELEASE) $(HELM_CHART) \
		-f $(HELM_CHART)/values-staging.yaml \
		--namespace $(K8S_NAMESPACE)-staging

helm-template-production:
	helm template $(HELM_RELEASE) $(HELM_CHART) \
		-f $(HELM_CHART)/values-production.yaml \
		--namespace $(K8S_NAMESPACE)

# Kubernetes deployment - Staging
k8s-deploy-staging: helm-deps
	kubectl create namespace $(K8S_NAMESPACE)-staging --dry-run=client -o yaml | kubectl apply -f -
	helm upgrade --install $(HELM_RELEASE) $(HELM_CHART) \
		-f $(HELM_CHART)/values-staging.yaml \
		--namespace $(K8S_NAMESPACE)-staging \
		--set api.image.tag=$(DOCKER_TAG) \
		--wait --timeout 10m

# Kubernetes deployment - Production
k8s-deploy-production: helm-deps
	kubectl create namespace $(K8S_NAMESPACE) --dry-run=client -o yaml | kubectl apply -f -
	helm upgrade --install $(HELM_RELEASE) $(HELM_CHART) \
		-f $(HELM_CHART)/values-production.yaml \
		--namespace $(K8S_NAMESPACE) \
		--set api.image.tag=$(DOCKER_TAG) \
		--wait --timeout 10m

# Kubernetes rollback
k8s-rollback-staging:
	helm rollback $(HELM_RELEASE) --namespace $(K8S_NAMESPACE)-staging

k8s-rollback-production:
	helm rollback $(HELM_RELEASE) --namespace $(K8S_NAMESPACE)

# Kubernetes status
k8s-status:
	@echo "=== Pods ==="
	kubectl get pods -n $(K8S_NAMESPACE) -l app.kubernetes.io/name=ssi-shadow
	@echo ""
	@echo "=== Services ==="
	kubectl get svc -n $(K8S_NAMESPACE) -l app.kubernetes.io/name=ssi-shadow
	@echo ""
	@echo "=== HPA ==="
	kubectl get hpa -n $(K8S_NAMESPACE)
	@echo ""
	@echo "=== Ingress ==="
	kubectl get ingress -n $(K8S_NAMESPACE)

k8s-logs:
	kubectl logs -f -n $(K8S_NAMESPACE) -l app.kubernetes.io/name=ssi-shadow --all-containers

k8s-shell:
	kubectl exec -it -n $(K8S_NAMESPACE) \
		$(shell kubectl get pod -n $(K8S_NAMESPACE) -l app.kubernetes.io/component=api -o jsonpath='{.items[0].metadata.name}') \
		-- /bin/sh

# Delete deployment
k8s-delete-staging:
	helm uninstall $(HELM_RELEASE) --namespace $(K8S_NAMESPACE)-staging || true
	kubectl delete namespace $(K8S_NAMESPACE)-staging || true

k8s-delete-production:
	@echo "⚠️  WARNING: This will delete PRODUCTION deployment!"
	@read -p "Type 'DELETE-PRODUCTION' to confirm: " confirm && [ "$$confirm" = "DELETE-PRODUCTION" ]
	helm uninstall $(HELM_RELEASE) --namespace $(K8S_NAMESPACE) || true

# Local Kubernetes (kind/minikube)
k8s-local-setup:
	kind create cluster --name ssi-shadow --config k8s/kind-config.yaml || true
	kubectl config use-context kind-ssi-shadow

k8s-local-deploy: k8s-local-setup docker-build
	kind load docker-image ssi-shadow:latest --name ssi-shadow
	helm upgrade --install $(HELM_RELEASE) $(HELM_CHART) \
		-f $(HELM_CHART)/values.yaml \
		--namespace $(K8S_NAMESPACE) \
		--create-namespace \
		--set global.imageRegistry="" \
		--set api.image.tag=latest

k8s-local-delete:
	kind delete cluster --name ssi-shadow

# Development environment with Docker Compose
dev-docker:
	docker-compose -f docker-compose.dev.yml up -d
	@echo ""
	@echo "Services started:"
	@echo "  API:        http://localhost:8080"
	@echo "  Dashboard:  http://localhost:3000"
	@echo "  Redis:      localhost:6379"
	@echo ""

dev-docker-down:
	docker-compose -f docker-compose.dev.yml down

dev-docker-logs:
	docker-compose -f docker-compose.dev.yml logs -f

dev-docker-monitoring:
	docker-compose -f docker-compose.dev.yml --profile monitoring up -d
	@echo ""
	@echo "Monitoring services started:"
	@echo "  Prometheus: http://localhost:9091"
	@echo "  Grafana:    http://localhost:3001 (admin/admin)"
	@echo "  Jaeger:     http://localhost:16686"
	@echo ""
