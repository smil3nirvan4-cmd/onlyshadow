# 🔐 S.S.I. SHADOW - CI/CD Secrets & Configuration

## Required GitHub Secrets

Configure these secrets in your repository settings:
**Settings → Secrets and variables → Actions → New repository secret**

---

## 🔑 Cloudflare Secrets

| Secret Name | Description | How to Get |
|-------------|-------------|------------|
| `CLOUDFLARE_API_TOKEN` | API token with Workers permissions | [Cloudflare Dashboard](https://dash.cloudflare.com/profile/api-tokens) |
| `CLOUDFLARE_ACCOUNT_ID` | Your Cloudflare account ID | Dashboard → Overview → Account ID |

### Cloudflare API Token Permissions
Create a token with these permissions:
- Account > Workers Scripts > Edit
- Account > Workers KV Storage > Edit
- Account > Workers Routes > Edit
- Zone > Workers Routes > Edit

---

## 📊 Meta (Facebook) Secrets

| Secret Name | Description | How to Get |
|-------------|-------------|------------|
| `META_PIXEL_ID` | Production Pixel ID | [Events Manager](https://business.facebook.com/events_manager) |
| `META_ACCESS_TOKEN` | System User access token | Business Settings → System Users |
| `META_PIXEL_ID_STAGING` | Staging/Test Pixel ID | Create test pixel in Events Manager |
| `META_ACCESS_TOKEN_STAGING` | Staging access token | Same as above |
| `META_TEST_EVENT_CODE` | Test event code | Events Manager → Test Events |

### Meta Access Token Permissions
- `ads_management`
- `ads_read`
- `pages_read_engagement`

---

## 🎵 TikTok Secrets

| Secret Name | Description | How to Get |
|-------------|-------------|------------|
| `TIKTOK_PIXEL_ID` | Production Pixel ID | [TikTok Events Manager](https://ads.tiktok.com/marketing_api/docs) |
| `TIKTOK_ACCESS_TOKEN` | API access token | TikTok for Business |
| `TIKTOK_PIXEL_ID_STAGING` | Staging Pixel ID | Same as above |
| `TIKTOK_ACCESS_TOKEN_STAGING` | Staging token | Same as above |

---

## 📈 Google Analytics Secrets

| Secret Name | Description | How to Get |
|-------------|-------------|------------|
| `GA4_MEASUREMENT_ID` | GA4 Measurement ID (G-XXXXX) | Google Analytics → Admin → Data Streams |
| `GA4_API_SECRET` | Measurement Protocol secret | Data Stream → Measurement Protocol API secrets |
| `GA4_MEASUREMENT_ID_STAGING` | Staging Measurement ID | Create staging property |
| `GA4_API_SECRET_STAGING` | Staging API secret | Same as above |

---

## ☁️ Google Cloud Platform Secrets

| Secret Name | Description | How to Get |
|-------------|-------------|------------|
| `GCP_PROJECT_ID` | GCP Project ID | GCP Console → Project Settings |
| `GCP_SERVICE_ACCOUNT_JSON` | Service account key (JSON) | IAM → Service Accounts → Create Key |

### GCP Service Account Permissions
- BigQuery Data Editor
- BigQuery Job User
- Cloud Functions Developer
- Storage Object Admin

### Creating Service Account Key
```bash
# Create service account
gcloud iam service-accounts create ssi-shadow-ci \
  --display-name="SSI Shadow CI/CD"

# Grant permissions
gcloud projects add-iam-policy-binding PROJECT_ID \
  --member="serviceAccount:ssi-shadow-ci@PROJECT_ID.iam.gserviceaccount.com" \
  --role="roles/bigquery.dataEditor"

gcloud projects add-iam-policy-binding PROJECT_ID \
  --member="serviceAccount:ssi-shadow-ci@PROJECT_ID.iam.gserviceaccount.com" \
  --role="roles/bigquery.jobUser"

# Create key
gcloud iam service-accounts keys create key.json \
  --iam-account=ssi-shadow-ci@PROJECT_ID.iam.gserviceaccount.com

# Copy JSON content to secret
cat key.json
```

---

## 📣 Notification Secrets

| Secret Name | Description | How to Get |
|-------------|-------------|------------|
| `SLACK_WEBHOOK_URL` | Slack incoming webhook | [Slack Apps](https://api.slack.com/apps) → Incoming Webhooks |
| `TELEGRAM_BOT_TOKEN` | Telegram bot token | [@BotFather](https://t.me/botfather) → /newbot |
| `TELEGRAM_CHAT_ID` | Chat/Group ID | Send message to bot, check updates API |

### Creating Slack Webhook
1. Go to [Slack Apps](https://api.slack.com/apps)
2. Create New App → From scratch
3. Incoming Webhooks → Activate
4. Add New Webhook to Workspace
5. Copy Webhook URL

### Getting Telegram Chat ID
```bash
# After creating bot and sending it a message:
curl https://api.telegram.org/bot<TOKEN>/getUpdates
# Find chat.id in response
```

---

## 🔒 Security Scanning Secrets

| Secret Name | Description | How to Get |
|-------------|-------------|------------|
| `SNYK_TOKEN` | Snyk API token | [Snyk Account](https://app.snyk.io/account) |
| `CODECOV_TOKEN` | Codecov upload token | [Codecov](https://codecov.io/) → Repository Settings |

---

## 🌳 Branch Protection Rules

Configure these in **Settings → Branches → Add rule**

### Main Branch (`main`)

```yaml
Branch name pattern: main

✅ Require a pull request before merging
  ✅ Require approvals: 1
  ✅ Dismiss stale pull request approvals when new commits are pushed
  ✅ Require review from Code Owners

✅ Require status checks to pass before merging
  ✅ Require branches to be up to date before merging
  Required status checks:
    - lint-typescript
    - lint-python
    - test-unit-typescript
    - test-unit-python
    - build
    - quality-gate

✅ Require conversation resolution before merging

✅ Require signed commits (optional)

✅ Require linear history

❌ Allow force pushes: Never

❌ Allow deletions: Never

✅ Lock branch (optional for releases)
```

### Develop Branch (`develop`)

```yaml
Branch name pattern: develop

✅ Require a pull request before merging
  ✅ Require approvals: 1

✅ Require status checks to pass before merging
  Required status checks:
    - lint-typescript
    - lint-python
    - test-unit-typescript
    - test-unit-python
    - build

❌ Allow force pushes: Never

❌ Allow deletions: Never
```

---

## 📂 Environment Configuration

### Environments Setup

Go to **Settings → Environments** and create:

#### `testing`
- No protection rules
- Used for integration tests

#### `staging`
- **Wait timer:** 0 minutes
- **Required reviewers:** None
- **Deployment branches:** `develop` only

#### `production-canary`
- **Wait timer:** 0 minutes
- **Required reviewers:** 1
- **Deployment branches:** `main` only

#### `production-canary-50`
- **Wait timer:** 2 minutes (auto-proceed after validation)
- **Required reviewers:** None
- **Deployment branches:** `main` only

#### `production`
- **Wait timer:** 0 minutes
- **Required reviewers:** 1 (for manual deployments)
- **Deployment branches:** `main` only
- **Environment secrets:** All production secrets

---

## 🔧 Repository Settings

### Actions Settings

**Settings → Actions → General**

```yaml
Actions permissions: Allow all actions and reusable workflows

Artifact and log retention: 30 days

Fork pull request workflows:
  ✅ Require approval for first-time contributors
  ✅ Require approval for all outside collaborators
```

### Dependabot Settings

Create `.github/dependabot.yml`:

```yaml
version: 2
updates:
  - package-ecosystem: "npm"
    directory: "/workers/gateway"
    schedule:
      interval: "weekly"
    open-pull-requests-limit: 10
    labels:
      - "dependencies"
      - "npm"

  - package-ecosystem: "npm"
    directory: "/dashboard"
    schedule:
      interval: "weekly"

  - package-ecosystem: "pip"
    directory: "/"
    schedule:
      interval: "weekly"
    labels:
      - "dependencies"
      - "python"

  - package-ecosystem: "github-actions"
    directory: "/"
    schedule:
      interval: "weekly"
    labels:
      - "dependencies"
      - "github-actions"
```

---

## ✅ Setup Checklist

- [ ] Configure all Cloudflare secrets
- [ ] Configure all Meta secrets
- [ ] Configure all TikTok secrets
- [ ] Configure all Google secrets
- [ ] Configure all GCP secrets
- [ ] Configure Slack webhook
- [ ] Configure Telegram bot
- [ ] Configure Snyk token
- [ ] Configure Codecov token
- [ ] Set up branch protection for `main`
- [ ] Set up branch protection for `develop`
- [ ] Create `testing` environment
- [ ] Create `staging` environment
- [ ] Create `production-canary` environment
- [ ] Create `production` environment
- [ ] Add Dependabot configuration
- [ ] Test CI workflow on a feature branch
- [ ] Test staging deployment
- [ ] Test production deployment (with canary)

---

## 🚨 Troubleshooting

### CI Fails on Lint
```bash
# Fix TypeScript lint issues
cd workers/gateway && npm run lint -- --fix

# Fix Python lint issues
black ads_engine/ automation/ ml/
isort ads_engine/ automation/ ml/
```

### Deployment Fails
1. Check Cloudflare API token permissions
2. Verify account ID is correct
3. Check wrangler.toml environment configuration

### Secret Scan Fails
1. Check for accidentally committed secrets
2. Add to `.gitignore` if needed
3. Use `git filter-branch` to remove from history

### Tests Timeout
1. Increase timeout in vitest.config.ts
2. Check for async operations not awaited
3. Reduce parallel workers if memory issues
