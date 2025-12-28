#!/bin/bash
# =============================================================================
# S.S.I. SHADOW — DOCKER ENTRYPOINT
# =============================================================================

set -e

# Configurar credenciais GCP se existir
if [ -f "/app/credentials/sa-key.json" ]; then
    export GOOGLE_APPLICATION_CREDENTIALS="/app/credentials/sa-key.json"
    echo "✓ GCP credentials configured"
fi

# Função para health check server
start_health_server() {
    python3 -c "
import http.server
import socketserver
import threading

class HealthHandler(http.server.SimpleHTTPRequestHandler):
    def do_GET(self):
        if self.path == '/health':
            self.send_response(200)
            self.send_header('Content-type', 'text/plain')
            self.end_headers()
            self.wfile.write(b'OK')
        else:
            self.send_response(404)
            self.end_headers()
    
    def log_message(self, format, *args):
        pass  # Silenciar logs

with socketserver.TCPServer(('', 8080), HealthHandler) as httpd:
    httpd.serve_forever()
" &
    echo "✓ Health server started on :8080"
}

case "$1" in
    shadow)
        echo "Starting SSI Shadow Intelligence Module..."
        start_health_server
        
        # Executar análise contínua
        python3 -c "
import time
import os
import sys
sys.path.insert(0, '/app')

from shadow.engine_v2 import ShadowEngineV2

engine = ShadowEngineV2(
    semrush_key=os.getenv('SEMRUSH_API_KEY'),
    telegram_token=os.getenv('TELEGRAM_BOT_TOKEN'),
    telegram_chat=os.getenv('TELEGRAM_CHAT_ID')
)

# Keywords para monitorar (pode vir de variável de ambiente)
keywords = os.getenv('MONITOR_KEYWORDS', 'suplemento,emagrecimento,termogenico').split(',')

interval_hours = int(os.getenv('ANALYSIS_INTERVAL_HOURS', '6'))

print(f'Monitoring keywords: {keywords}')
print(f'Analysis interval: {interval_hours} hours')

while True:
    try:
        results = engine.analyze_keywords(keywords)
        print(engine.generate_report(results))
    except Exception as e:
        print(f'Error in analysis: {e}')
    
    print(f'Next analysis in {interval_hours} hours...')
    time.sleep(interval_hours * 3600)
"
        ;;
    
    bid-controller)
        echo "Starting Bid Controller..."
        start_health_server
        
        python3 -m automation.bid_controller \
            --project "${GCP_PROJECT_ID}" \
            --schedule "${BID_INTERVAL_MINUTES:-60}" \
            ${DRY_RUN:+--dry-run}
        ;;
    
    analyze)
        echo "Running single analysis..."
        shift
        python3 -m shadow.engine_v2 "$@"
        ;;
    
    train)
        echo "Triggering model training..."
        python3 -c "
import os
import sys
sys.path.insert(0, '/app')

from ml.pipelines.vertex_training import MLPipeline

pipeline = MLPipeline(
    project_id=os.getenv('GCP_PROJECT_ID'),
    region=os.getenv('GCP_REGION', 'us-central1'),
    dataset_id='ssi_shadow'
)

model_type = '${2:-all}'
if model_type == 'ltv':
    pipeline.run_ltv_pipeline()
elif model_type == 'intent':
    pipeline.run_intent_pipeline()
else:
    pipeline.run_all_pipelines()
"
        ;;
    
    shell)
        echo "Starting shell..."
        exec /bin/bash
        ;;
    
    *)
        echo "Usage: $0 {shadow|bid-controller|analyze|train|shell}"
        echo ""
        echo "Modes:"
        echo "  shadow          - Run continuous keyword monitoring"
        echo "  bid-controller  - Run bid optimization loop"
        echo "  analyze         - Run single analysis (pass --keywords)"
        echo "  train           - Trigger ML model training"
        echo "  shell           - Start bash shell"
        exit 1
        ;;
esac
