#!/bin/bash
# =============================================================================
# S.S.I. SHADOW — SETUP SCRIPT
# ENTERPRISE EDITION
# =============================================================================

set -e

echo "=============================================="
echo "S.S.I. SHADOW - Setup Script"
echo "=============================================="

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Check requirements
check_command() {
    if ! command -v $1 &> /dev/null; then
        echo -e "${RED}✗ $1 not found${NC}"
        return 1
    else
        echo -e "${GREEN}✓ $1 found${NC}"
        return 0
    fi
}

echo ""
echo "Checking requirements..."
check_command python3
check_command node
check_command npm
check_command gcloud || echo -e "${YELLOW}  (optional for local dev)${NC}"
check_command docker || echo -e "${YELLOW}  (optional for local dev)${NC}"

# Environment
echo ""
echo "Setting up environment..."

if [ ! -f .env ]; then
    cp .env.example .env
    echo -e "${YELLOW}Created .env from template. Please edit with your credentials.${NC}"
else
    echo -e "${GREEN}✓ .env exists${NC}"
fi

# Python dependencies
echo ""
echo "Installing Python dependencies..."
pip install -r requirements.txt --quiet

# Node dependencies (Worker)
echo ""
echo "Installing Node dependencies..."
cd workers/gateway
npm install --silent
cd ../..

# dbt setup
echo ""
echo "Setting up dbt..."
cd dbt
if [ ! -f profiles.yml ]; then
    cat > profiles.yml << 'EOF'
ssi_shadow:
  target: dev
  outputs:
    dev:
      type: bigquery
      method: oauth
      project: "{{ env_var('GCP_PROJECT_ID') }}"
      dataset: ssi_shadow
      threads: 4
      timeout_seconds: 300
    prod:
      type: bigquery
      method: service-account
      project: "{{ env_var('GCP_PROJECT_ID') }}"
      dataset: ssi_shadow
      keyfile: "{{ env_var('GOOGLE_APPLICATION_CREDENTIALS') }}"
      threads: 8
      timeout_seconds: 300
EOF
    echo -e "${GREEN}✓ Created dbt profiles.yml${NC}"
fi
cd ..

# Create directories
echo ""
echo "Creating directories..."
mkdir -p credentials
mkdir -p logs
mkdir -p data

# Permissions
chmod +x docker-entrypoint.sh
chmod +x setup.sh

echo ""
echo "=============================================="
echo -e "${GREEN}Setup complete!${NC}"
echo "=============================================="
echo ""
echo "Next steps:"
echo "1. Edit .env with your credentials"
echo "2. Add GCP service account key to credentials/"
echo "3. Run: make dev (or docker-compose up -d)"
echo ""
echo "Quick commands:"
echo "  make dev        - Start development environment"
echo "  make test       - Run tests"
echo "  make deploy     - Deploy to production"
echo "  make help       - Show all commands"
echo ""
# =============================================================================
# S.S.I. SHADOW — Setup Script
# =============================================================================

set -e

echo "=========================================="
echo "  S.S.I. SHADOW - Setup Automatizado"
echo "=========================================="
echo ""

# Cores
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Funções
success() { echo -e "${GREEN}✓${NC} $1"; }
warning() { echo -e "${YELLOW}⚠${NC} $1"; }
error() { echo -e "${RED}✗${NC} $1"; exit 1; }

# =============================================================================
# VERIFICAR DEPENDÊNCIAS
# =============================================================================

echo "📋 Verificando dependências..."

# Node.js
if command -v node &> /dev/null; then
    NODE_VERSION=$(node -v)
    success "Node.js instalado: $NODE_VERSION"
else
    error "Node.js não encontrado. Instale: https://nodejs.org/"
fi

# npm
if command -v npm &> /dev/null; then
    NPM_VERSION=$(npm -v)
    success "npm instalado: $NPM_VERSION"
else
    error "npm não encontrado."
fi

# Python
if command -v python3 &> /dev/null; then
    PYTHON_VERSION=$(python3 --version)
    success "Python instalado: $PYTHON_VERSION"
else
    warning "Python não encontrado. Oráculo não funcionará."
fi

# Wrangler
if command -v wrangler &> /dev/null; then
    success "Wrangler CLI instalado"
else
    echo "Instalando Wrangler CLI..."
    npm install -g wrangler
    success "Wrangler CLI instalado"
fi

# gcloud (opcional)
if command -v gcloud &> /dev/null; then
    success "gcloud CLI instalado"
else
    warning "gcloud CLI não encontrado. BigQuery requer configuração manual."
fi

echo ""

# =============================================================================
# CONFIGURAR CLOUDFLARE
# =============================================================================

echo "☁️  Configurando Cloudflare..."

# Verificar login
if wrangler whoami &> /dev/null; then
    success "Logado no Cloudflare"
else
    echo "Faça login no Cloudflare..."
    wrangler login
fi

echo ""

# =============================================================================
# CRIAR KV NAMESPACES
# =============================================================================

echo "🗄️  Criando KV Namespaces..."

cd workers/gateway

# Identity KV
echo "Criando IDENTITY_KV..."
IDENTITY_KV_OUTPUT=$(wrangler kv:namespace create "IDENTITY_KV" 2>&1 || true)
if echo "$IDENTITY_KV_OUTPUT" | grep -q "id ="; then
    IDENTITY_KV_ID=$(echo "$IDENTITY_KV_OUTPUT" | grep "id =" | awk -F'"' '{print $2}')
    success "IDENTITY_KV criado: $IDENTITY_KV_ID"
else
    warning "IDENTITY_KV pode já existir"
fi

# Events KV
echo "Criando EVENTS_KV..."
EVENTS_KV_OUTPUT=$(wrangler kv:namespace create "EVENTS_KV" 2>&1 || true)
if echo "$EVENTS_KV_OUTPUT" | grep -q "id ="; then
    EVENTS_KV_ID=$(echo "$EVENTS_KV_OUTPUT" | grep "id =" | awk -F'"' '{print $2}')
    success "EVENTS_KV criado: $EVENTS_KV_ID"
else
    warning "EVENTS_KV pode já existir"
fi

echo ""
echo "⚠️  IMPORTANTE: Atualize o wrangler.toml com os IDs dos namespaces!"
echo ""

# =============================================================================
# INSTALAR DEPENDÊNCIAS NODE
# =============================================================================

echo "📦 Instalando dependências Node..."
npm install
success "Dependências Node instaladas"

cd ../..

# =============================================================================
# INSTALAR DEPENDÊNCIAS PYTHON
# =============================================================================

if command -v python3 &> /dev/null; then
    echo "🐍 Instalando dependências Python..."
    cd shadow
    pip3 install -r requirements.txt --quiet
    success "Dependências Python instaladas"
    cd ..
fi

echo ""

# =============================================================================
# CONFIGURAR SECRETS
# =============================================================================

echo "🔐 Configuração de Secrets"
echo ""
echo "Execute os seguintes comandos para configurar os secrets:"
echo ""
echo "  cd workers/gateway"
echo "  wrangler secret put META_ACCESS_TOKEN"
echo "  wrangler secret put META_PIXEL_ID"
echo "  wrangler secret put GOOGLE_MEASUREMENT_ID"
echo "  wrangler secret put GOOGLE_API_SECRET"
echo "  wrangler secret put BQ_PROJECT_ID"
echo "  wrangler secret put BQ_DATASET_ID"
echo "  wrangler secret put BQ_SERVICE_ACCOUNT_KEY"
echo ""

# =============================================================================
# BIGQUERY SETUP
# =============================================================================

echo "📊 BigQuery Setup"
echo ""
echo "Para configurar o BigQuery:"
echo ""
echo "1. Substitua {PROJECT_ID} em bigquery/schemas/schema.sql"
echo "2. Execute no BigQuery Console ou via CLI:"
echo "   bq query --use_legacy_sql=false < bigquery/schemas/schema.sql"
echo ""

# =============================================================================
# DEPLOY
# =============================================================================

echo "🚀 Deploy"
echo ""
echo "Quando estiver pronto, execute:"
echo ""
echo "  cd workers/gateway"
echo "  wrangler deploy"
echo ""

# =============================================================================
# FINALIZAÇÃO
# =============================================================================

echo "=========================================="
echo "  Setup Concluído!"
echo "=========================================="
echo ""
echo "Próximos passos:"
echo "1. Atualizar IDs dos KV namespaces no wrangler.toml"
echo "2. Configurar secrets (Meta, Google, TikTok, BigQuery)"
echo "3. Configurar BigQuery schemas"
echo "4. Deploy do Worker"
echo "5. Instalar Ghost Script no seu site"
echo ""
echo "Documentação completa: README.md"
echo ""
