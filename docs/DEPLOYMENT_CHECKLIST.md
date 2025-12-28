# S.S.I. SHADOW - Deployment Checklist

## Pre-Deployment

- [ ] All tests passing (`pytest tests/ -v`)
- [ ] Code linted (`ruff check .`)
- [ ] Environment variables configured
- [ ] Secrets in secret manager
- [ ] Database migrations run
- [ ] Docker image built and tested locally

## Environment Variables

### Required
- [ ] `GCP_PROJECT_ID`
- [ ] `BQ_DATASET`
- [ ] `REDIS_URL`
- [ ] `SECRETS_PROVIDER`

### Optional (for full functionality)
- [ ] `META_ACCESS_TOKEN`
- [ ] `GOOGLE_ADS_DEVELOPER_TOKEN`
- [ ] `GOOGLE_ADS_CLIENT_ID`
- [ ] `GOOGLE_ADS_CLIENT_SECRET`
- [ ] `GOOGLE_ADS_REFRESH_TOKEN`
- [ ] `TIKTOK_ACCESS_TOKEN`
- [ ] `OPENWEATHER_API_KEY`

## Deployment Steps

### 1. Push Docker Image
```bash
docker build -t gcr.io/PROJECT/ssi-shadow-api:VERSION .
docker push gcr.io/PROJECT/ssi-shadow-api:VERSION
```

### 2. Run Migrations
```bash
python -m migrations.migrator migrate
```

### 3. Deploy API
```bash
gcloud run deploy ssi-shadow-api \
  --image gcr.io/PROJECT/ssi-shadow-api:VERSION \
  --region us-central1
```

### 4. Deploy Workers
```bash
cd workers/gateway
npx wrangler publish
```

### 5. Validate
```bash
python scripts/validate_deployment.py
```

## Post-Deployment

- [ ] Health check passing (`/health`)
- [ ] Detailed health check passing (`/health/detailed`)
- [ ] API documentation accessible (`/docs`)
- [ ] Monitoring dashboards working
- [ ] Alerts configured and tested
- [ ] Log aggregation working

## Rollback

If issues occur:

```bash
# Rollback API
gcloud run services update-traffic ssi-shadow-api \
  --to-revisions PREVIOUS_REVISION=100

# Rollback database
python -m migrations.migrator rollback --steps 1
```
