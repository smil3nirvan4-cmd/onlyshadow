#!/bin/bash
# ============================================================================
# S.S.I. SHADOW - Test Events Script
# ============================================================================
# Execute: chmod +x test-events.sh && ./test-events.sh
# ============================================================================

# Configuração
ENDPOINT="${SSI_ENDPOINT:-https://ssi-shadow.YOUR-SUBDOMAIN.workers.dev}"

echo "============================================"
echo "S.S.I. SHADOW - Test Events"
echo "Endpoint: $ENDPOINT"
echo "============================================"
echo ""

# Cores para output
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Função para testar
test_endpoint() {
  local name=$1
  local method=$2
  local path=$3
  local data=$4
  
  echo -n "Testing $name... "
  
  if [ "$method" = "GET" ]; then
    response=$(curl -s -w "\n%{http_code}" "$ENDPOINT$path")
  else
    response=$(curl -s -w "\n%{http_code}" -X POST "$ENDPOINT$path" \
      -H "Content-Type: application/json" \
      -H "User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36" \
      -H "Accept-Language: pt-BR,pt;q=0.9,en;q=0.8" \
      -d "$data")
  fi
  
  status_code=$(echo "$response" | tail -n1)
  body=$(echo "$response" | sed '$d')
  
  if [ "$status_code" = "200" ] || [ "$status_code" = "204" ]; then
    echo -e "${GREEN}✓ OK${NC} ($status_code)"
    echo "$body" | head -c 200
    echo ""
  else
    echo -e "${RED}✗ FAIL${NC} ($status_code)"
    echo "$body"
  fi
  echo ""
}

# ============================================================================
# Testes
# ============================================================================

echo "1. HEALTH CHECK"
echo "-------------------------------------------"
test_endpoint "Health" "GET" "/api/health" ""

echo "2. CONFIG"
echo "-------------------------------------------"
test_endpoint "Config" "GET" "/api/config" ""

echo "3. PAGEVIEW EVENT"
echo "-------------------------------------------"
test_endpoint "PageView" "POST" "/api/collect" '{
  "event_name": "PageView",
  "url": "https://seusite.com/produto/123",
  "referrer": "https://google.com",
  "title": "Produto Exemplo",
  "scroll_depth": 45,
  "time_on_page": 30000
}'

echo "4. VIEW CONTENT EVENT"
echo "-------------------------------------------"
test_endpoint "ViewContent" "POST" "/api/collect" '{
  "event_name": "ViewContent",
  "url": "https://seusite.com/produto/456",
  "content_ids": ["SKU-456"],
  "content_name": "Camiseta Preta",
  "content_category": "Vestuário",
  "value": 79.90,
  "currency": "BRL"
}'

echo "5. ADD TO CART EVENT"
echo "-------------------------------------------"
test_endpoint "AddToCart" "POST" "/api/collect" '{
  "event_name": "AddToCart",
  "content_ids": ["SKU-456"],
  "content_name": "Camiseta Preta",
  "value": 79.90,
  "currency": "BRL",
  "num_items": 1
}'

echo "6. INITIATE CHECKOUT EVENT"
echo "-------------------------------------------"
test_endpoint "InitiateCheckout" "POST" "/api/collect" '{
  "event_name": "InitiateCheckout",
  "content_ids": ["SKU-456", "SKU-789"],
  "value": 159.80,
  "currency": "BRL",
  "num_items": 2
}'

echo "7. PURCHASE EVENT (with PII)"
echo "-------------------------------------------"
test_endpoint "Purchase" "POST" "/api/collect" '{
  "event_name": "Purchase",
  "email": "teste@email.com",
  "phone": "+5511999999999",
  "first_name": "João",
  "last_name": "Silva",
  "city": "São Paulo",
  "state": "SP",
  "zip": "01310100",
  "country": "BR",
  "content_ids": ["SKU-456", "SKU-789"],
  "value": 159.80,
  "currency": "BRL",
  "order_id": "ORDER-12345",
  "num_items": 2
}'

echo "8. LEAD EVENT"
echo "-------------------------------------------"
test_endpoint "Lead" "POST" "/api/collect" '{
  "event_name": "Lead",
  "email": "lead@email.com",
  "phone": "+5511888888888",
  "first_name": "Maria",
  "last_name": "Santos"
}'

echo "9. SEARCH EVENT"
echo "-------------------------------------------"
test_endpoint "Search" "POST" "/api/collect" '{
  "event_name": "Search",
  "search_string": "camiseta preta masculina"
}'

echo "10. BOT TEST (should be blocked)"
echo "-------------------------------------------"
echo -n "Testing Bot Detection... "
response=$(curl -s -w "\n%{http_code}" -X POST "$ENDPOINT/api/collect" \
  -H "Content-Type: application/json" \
  -H "User-Agent: python-requests/2.28.0" \
  -d '{"event_name":"PageView"}')

status_code=$(echo "$response" | tail -n1)
body=$(echo "$response" | sed '$d')

if echo "$body" | grep -q '"trust_action":"block"'; then
  echo -e "${GREEN}✓ Bot correctly blocked${NC}"
else
  echo -e "${YELLOW}⚠ Bot not blocked (check TRUST_SCORE_THRESHOLD)${NC}"
fi
echo "$body" | head -c 200
echo ""
echo ""

echo "============================================"
echo "Tests completed!"
echo "============================================"
echo ""
echo "Next steps:"
echo "1. Check Meta Events Manager > Test Events"
echo "2. Check TikTok Ads Manager > Events > Test"
echo "3. Check GA4 > Realtime > Events"
echo "4. Check BigQuery > Query results"
echo ""
