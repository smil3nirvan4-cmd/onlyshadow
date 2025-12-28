"""
S.S.I. SHADOW - Pub/Sub Consumer Cloud Function
================================================

Cloud Function que consome eventos do Pub/Sub e insere no BigQuery em batches.

Arquitetura:
    Worker (Edge) → Pub/Sub (raw-events) → Esta Function → BigQuery

Benefícios:
    - Desacoplamento: Worker retorna em <50ms
    - Resiliência: Pub/Sub garante entrega (retry automático)
    - Eficiência: Batch insert reduz custos do BigQuery
    - Escala: Automatic scaling no Cloud Functions

Deploy:
    gcloud functions deploy pubsub-consumer \
        --runtime python311 \
        --trigger-topic raw-events \
        --entry-point handle_pubsub_message \
        --memory 512MB \
        --timeout 60s \
        --max-instances 100 \
        --set-env-vars GCP_PROJECT_ID=xxx,BQ_DATASET=ssi_shadow,BQ_TABLE=events_raw

Configuração (env vars):
    - GCP_PROJECT_ID: ID do projeto GCP
    - BQ_DATASET: Dataset do BigQuery (default: ssi_shadow)
    - BQ_TABLE: Tabela de eventos (default: events_raw)
    - BATCH_SIZE: Tamanho do batch (default: 100)
    - BATCH_TIMEOUT_MS: Timeout do batch em ms (default: 1000)
    - ENABLE_METRICS: Habilitar métricas Prometheus (default: true)
"""

import os
import json
import base64
import logging
import time
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field
from collections import deque
import threading
import functools

# Google Cloud
from google.cloud import bigquery
from google.cloud import monitoring_v3
import functions_framework

# Prometheus (opcional)
try:
    from prometheus_client import Counter, Histogram, Gauge, push_to_gateway, CollectorRegistry
    PROMETHEUS_AVAILABLE = True
except ImportError:
    PROMETHEUS_AVAILABLE = False

# Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger('pubsub_consumer')

# =============================================================================
# CONFIGURATION
# =============================================================================

@dataclass
class ConsumerConfig:
    """Configuração do consumer."""
    gcp_project_id: str = field(default_factory=lambda: os.getenv('GCP_PROJECT_ID', ''))
    bq_dataset: str = field(default_factory=lambda: os.getenv('BQ_DATASET', 'ssi_shadow'))
    bq_table: str = field(default_factory=lambda: os.getenv('BQ_TABLE', 'events_raw'))
    batch_size: int = field(default_factory=lambda: int(os.getenv('BATCH_SIZE', '100')))
    batch_timeout_ms: int = field(default_factory=lambda: int(os.getenv('BATCH_TIMEOUT_MS', '1000')))
    enable_metrics: bool = field(default_factory=lambda: os.getenv('ENABLE_METRICS', 'true').lower() == 'true')
    pushgateway_url: str = field(default_factory=lambda: os.getenv('PUSHGATEWAY_URL', ''))


# Global config
config = ConsumerConfig()


# =============================================================================
# METRICS
# =============================================================================

class ConsumerMetrics:
    """Métricas do consumer."""
    
    def __init__(self):
        self.events_received = 0
        self.events_inserted = 0
        self.events_failed = 0
        self.batches_processed = 0
        self.total_lag_ms = 0
        self.avg_lag_ms = 0.0
        self.avg_batch_size = 0.0
        self.last_process_time: Optional[str] = None
        self.errors: List[str] = []
        
        # Prometheus metrics (se disponível)
        if PROMETHEUS_AVAILABLE and config.enable_metrics:
            self.registry = CollectorRegistry()
            
            self.prom_events_received = Counter(
                'pubsub_consumer_events_received_total',
                'Total events received from Pub/Sub',
                registry=self.registry
            )
            
            self.prom_events_inserted = Counter(
                'pubsub_consumer_events_inserted_total',
                'Total events inserted into BigQuery',
                registry=self.registry
            )
            
            self.prom_events_failed = Counter(
                'pubsub_consumer_events_failed_total',
                'Total events that failed to insert',
                registry=self.registry
            )
            
            self.prom_lag_seconds = Histogram(
                'pubsub_consumer_lag_seconds',
                'Lag between event reception and BigQuery insert',
                buckets=(0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0, 60.0),
                registry=self.registry
            )
            
            self.prom_batch_size = Histogram(
                'pubsub_consumer_batch_size',
                'Size of batches inserted into BigQuery',
                buckets=(1, 10, 25, 50, 100, 250, 500),
                registry=self.registry
            )
            
            self.prom_insert_duration = Histogram(
                'pubsub_consumer_insert_duration_seconds',
                'Duration of BigQuery insert operations',
                buckets=(0.1, 0.25, 0.5, 1.0, 2.0, 5.0, 10.0),
                registry=self.registry
            )
    
    def record_event_received(self):
        """Registra evento recebido."""
        self.events_received += 1
        if PROMETHEUS_AVAILABLE and config.enable_metrics:
            self.prom_events_received.inc()
    
    def record_batch_inserted(self, batch_size: int, lag_ms: float, duration_s: float):
        """Registra batch inserido com sucesso."""
        self.events_inserted += batch_size
        self.batches_processed += 1
        self.total_lag_ms += lag_ms
        self.avg_lag_ms = self.total_lag_ms / self.events_inserted if self.events_inserted > 0 else 0
        self.avg_batch_size = self.events_inserted / self.batches_processed if self.batches_processed > 0 else 0
        self.last_process_time = datetime.now(timezone.utc).isoformat()
        
        if PROMETHEUS_AVAILABLE and config.enable_metrics:
            self.prom_events_inserted.inc(batch_size)
            self.prom_lag_seconds.observe(lag_ms / 1000.0)
            self.prom_batch_size.observe(batch_size)
            self.prom_insert_duration.observe(duration_s)
    
    def record_failure(self, count: int, error: str):
        """Registra falha de inserção."""
        self.events_failed += count
        self.errors.append(f"{datetime.now().isoformat()}: {error}")
        if len(self.errors) > 100:
            self.errors = self.errors[-100:]  # Keep last 100 errors
        
        if PROMETHEUS_AVAILABLE and config.enable_metrics:
            self.prom_events_failed.inc(count)
    
    def push_to_gateway(self):
        """Envia métricas para Prometheus Pushgateway."""
        if PROMETHEUS_AVAILABLE and config.enable_metrics and config.pushgateway_url:
            try:
                push_to_gateway(
                    config.pushgateway_url,
                    job='pubsub_consumer',
                    registry=self.registry
                )
            except Exception as e:
                logger.warning(f"Failed to push metrics: {e}")
    
    def to_dict(self) -> Dict[str, Any]:
        """Retorna métricas como dicionário."""
        return {
            'events_received': self.events_received,
            'events_inserted': self.events_inserted,
            'events_failed': self.events_failed,
            'batches_processed': self.batches_processed,
            'avg_lag_ms': round(self.avg_lag_ms, 2),
            'avg_batch_size': round(self.avg_batch_size, 2),
            'last_process_time': self.last_process_time,
            'recent_errors': self.errors[-5:] if self.errors else [],
        }


# Global metrics
metrics = ConsumerMetrics()


# =============================================================================
# BIGQUERY CLIENT
# =============================================================================

class BigQueryBatchInserter:
    """
    Insere eventos no BigQuery em batches.
    
    Features:
    - Batch buffering (agrupa eventos)
    - Streaming insert com retry
    - Error handling por row
    """
    
    def __init__(self, project_id: str, dataset_id: str, table_id: str):
        self.project_id = project_id
        self.dataset_id = dataset_id
        self.table_id = table_id
        self.table_ref = f"{project_id}.{dataset_id}.{table_id}"
        self.client = bigquery.Client(project=project_id)
        
        # Batch buffer
        self.buffer: List[Dict[str, Any]] = []
        self.buffer_lock = threading.Lock()
        self.last_flush_time = time.time()
    
    def add_to_buffer(self, row: Dict[str, Any]) -> bool:
        """Adiciona row ao buffer. Retorna True se flush necessário."""
        with self.buffer_lock:
            self.buffer.append(row)
            return len(self.buffer) >= config.batch_size
    
    def should_flush(self) -> bool:
        """Verifica se deve fazer flush (timeout ou size)."""
        with self.buffer_lock:
            if len(self.buffer) == 0:
                return False
            if len(self.buffer) >= config.batch_size:
                return True
            elapsed_ms = (time.time() - self.last_flush_time) * 1000
            return elapsed_ms >= config.batch_timeout_ms
    
    def flush(self) -> Dict[str, Any]:
        """
        Faz flush do buffer para BigQuery.
        
        Returns:
            Dict com resultados: {success, inserted, failed, errors, duration_ms}
        """
        with self.buffer_lock:
            if not self.buffer:
                return {'success': True, 'inserted': 0, 'failed': 0, 'errors': [], 'duration_ms': 0}
            
            rows_to_insert = self.buffer.copy()
            self.buffer = []
            self.last_flush_time = time.time()
        
        start_time = time.time()
        
        try:
            # Streaming insert
            errors = self.client.insert_rows_json(
                self.table_ref,
                rows_to_insert,
                row_ids=[row.get('event_id', None) for row in rows_to_insert]  # Dedup
            )
            
            duration_ms = (time.time() - start_time) * 1000
            
            if errors:
                # Alguns rows falharam
                failed_indices = {e['index'] for e in errors}
                inserted = len(rows_to_insert) - len(failed_indices)
                error_messages = [str(e['errors']) for e in errors[:5]]  # First 5
                
                logger.warning(f"Partial insert: {inserted}/{len(rows_to_insert)} rows, errors: {error_messages}")
                
                return {
                    'success': False,
                    'inserted': inserted,
                    'failed': len(failed_indices),
                    'errors': error_messages,
                    'duration_ms': duration_ms
                }
            else:
                logger.info(f"Inserted {len(rows_to_insert)} rows in {duration_ms:.0f}ms")
                return {
                    'success': True,
                    'inserted': len(rows_to_insert),
                    'failed': 0,
                    'errors': [],
                    'duration_ms': duration_ms
                }
                
        except Exception as e:
            duration_ms = (time.time() - start_time) * 1000
            error_msg = str(e)
            logger.error(f"BigQuery insert failed: {error_msg}")
            
            # Re-add to buffer for retry (optional)
            # with self.buffer_lock:
            #     self.buffer = rows_to_insert + self.buffer
            
            return {
                'success': False,
                'inserted': 0,
                'failed': len(rows_to_insert),
                'errors': [error_msg],
                'duration_ms': duration_ms
            }


# Global inserter (lazy init)
_inserter: Optional[BigQueryBatchInserter] = None

def get_inserter() -> BigQueryBatchInserter:
    """Get or create BigQuery inserter."""
    global _inserter
    if _inserter is None:
        _inserter = BigQueryBatchInserter(
            config.gcp_project_id,
            config.bq_dataset,
            config.bq_table
        )
    return _inserter


# =============================================================================
# MESSAGE PROCESSING
# =============================================================================

def parse_pubsub_message(data: str) -> Optional[Dict[str, Any]]:
    """
    Parse mensagem do Pub/Sub.
    
    Args:
        data: Base64 encoded JSON string
        
    Returns:
        Parsed message dict or None if invalid
    """
    try:
        decoded = base64.b64decode(data).decode('utf-8')
        message = json.loads(decoded)
        return message
    except Exception as e:
        logger.error(f"Failed to parse message: {e}")
        return None


def calculate_lag_ms(received_at: str) -> float:
    """
    Calcula lag entre recebimento no Worker e processamento aqui.
    
    Args:
        received_at: ISO timestamp de quando o Worker recebeu o evento
        
    Returns:
        Lag em milliseconds
    """
    try:
        received_time = datetime.fromisoformat(received_at.replace('Z', '+00:00'))
        now = datetime.now(timezone.utc)
        delta = now - received_time
        return delta.total_seconds() * 1000
    except Exception:
        return 0.0


def process_message(message: Dict[str, Any]) -> Dict[str, Any]:
    """
    Processa uma mensagem do Pub/Sub.
    
    Estrutura esperada:
    {
        "row": { ... BigQuery row ... },
        "metadata": {
            "event_id": "...",
            "event_name": "...",
            "received_at": "...",
            "worker_region": "..."
        }
    }
    """
    row = message.get('row', {})
    metadata = message.get('metadata', {})
    
    # Enriquecer row com metadata do consumer
    row['pubsub_processed_at'] = datetime.now(timezone.utc).isoformat()
    row['pubsub_lag_ms'] = calculate_lag_ms(metadata.get('received_at', ''))
    
    return row


# =============================================================================
# CLOUD FUNCTION ENTRY POINTS
# =============================================================================

@functions_framework.cloud_event
def handle_pubsub_message(cloud_event):
    """
    Entry point para Cloud Function trigger por Pub/Sub.
    
    Esta função é chamada para CADA mensagem (não batch).
    Para batch processing, use Pub/Sub push subscription.
    
    Args:
        cloud_event: CloudEvent com dados do Pub/Sub
    """
    try:
        # Extract message data
        data = cloud_event.data.get('message', {}).get('data', '')
        attributes = cloud_event.data.get('message', {}).get('attributes', {})
        
        if not data:
            logger.warning("Empty message received")
            return 'OK', 200
        
        # Parse message
        message = parse_pubsub_message(data)
        if not message:
            logger.error("Failed to parse message")
            return 'Parse Error', 400
        
        # Record metric
        metrics.record_event_received()
        
        # Process and add to buffer
        row = process_message(message)
        inserter = get_inserter()
        should_flush = inserter.add_to_buffer(row)
        
        # Flush if needed
        if should_flush or inserter.should_flush():
            result = inserter.flush()
            
            if result['inserted'] > 0:
                avg_lag = row.get('pubsub_lag_ms', 0)
                metrics.record_batch_inserted(
                    result['inserted'],
                    avg_lag,
                    result['duration_ms'] / 1000.0
                )
            
            if result['failed'] > 0:
                metrics.record_failure(result['failed'], '; '.join(result['errors'][:3]))
            
            # Push metrics
            metrics.push_to_gateway()
        
        return 'OK', 200
        
    except Exception as e:
        logger.exception(f"Error processing message: {e}")
        metrics.record_failure(1, str(e))
        return f'Error: {e}', 500


@functions_framework.http
def handle_batch_request(request):
    """
    HTTP entry point para batch processing.
    
    Recebe um array de mensagens e processa em batch.
    Útil para Pub/Sub push subscriptions com batching.
    
    Request body:
    {
        "messages": [
            {"data": "base64...", "attributes": {...}},
            ...
        ]
    }
    """
    try:
        body = request.get_json(force=True)
        messages = body.get('messages', [])
        
        if not messages:
            return {'status': 'ok', 'processed': 0}, 200
        
        inserter = get_inserter()
        processed = 0
        total_lag_ms = 0
        
        for msg in messages:
            data = msg.get('data', '')
            if not data:
                continue
            
            message = parse_pubsub_message(data)
            if not message:
                continue
            
            metrics.record_event_received()
            row = process_message(message)
            inserter.add_to_buffer(row)
            processed += 1
            total_lag_ms += row.get('pubsub_lag_ms', 0)
        
        # Flush all
        result = inserter.flush()
        
        if result['inserted'] > 0:
            avg_lag = total_lag_ms / processed if processed > 0 else 0
            metrics.record_batch_inserted(
                result['inserted'],
                avg_lag,
                result['duration_ms'] / 1000.0
            )
        
        if result['failed'] > 0:
            metrics.record_failure(result['failed'], '; '.join(result['errors'][:3]))
        
        # Push metrics
        metrics.push_to_gateway()
        
        return {
            'status': 'ok',
            'processed': processed,
            'inserted': result['inserted'],
            'failed': result['failed'],
            'duration_ms': result['duration_ms'],
        }, 200
        
    except Exception as e:
        logger.exception(f"Error in batch processing: {e}")
        return {'status': 'error', 'error': str(e)}, 500


@functions_framework.http
def health_check(request):
    """Health check endpoint."""
    return {
        'status': 'healthy',
        'timestamp': datetime.now(timezone.utc).isoformat(),
        'config': {
            'project': config.gcp_project_id,
            'dataset': config.bq_dataset,
            'table': config.bq_table,
            'batch_size': config.batch_size,
        },
        'metrics': metrics.to_dict(),
    }, 200


@functions_framework.http
def get_metrics(request):
    """Endpoint para obter métricas."""
    return metrics.to_dict(), 200


# =============================================================================
# CLOUD RUN / STANDALONE MODE
# =============================================================================

def create_flask_app():
    """
    Cria Flask app para rodar como Cloud Run ou standalone.
    
    Útil para:
    - Cloud Run com Pub/Sub push subscription
    - Testing local
    - Container deployment
    """
    from flask import Flask, request as flask_request, jsonify
    
    app = Flask(__name__)
    
    @app.route('/pubsub', methods=['POST'])
    def pubsub_push():
        """Pub/Sub push endpoint."""
        envelope = flask_request.get_json(force=True)
        message = envelope.get('message', {})
        
        data = message.get('data', '')
        if not data:
            return jsonify({'status': 'empty'}), 200
        
        parsed = parse_pubsub_message(data)
        if not parsed:
            return jsonify({'status': 'parse_error'}), 400
        
        metrics.record_event_received()
        row = process_message(parsed)
        
        inserter = get_inserter()
        inserter.add_to_buffer(row)
        
        if inserter.should_flush():
            result = inserter.flush()
            if result['inserted'] > 0:
                metrics.record_batch_inserted(
                    result['inserted'],
                    row.get('pubsub_lag_ms', 0),
                    result['duration_ms'] / 1000.0
                )
        
        return jsonify({'status': 'ok'}), 200
    
    @app.route('/batch', methods=['POST'])
    def batch_endpoint():
        """Batch processing endpoint."""
        return handle_batch_request(flask_request)
    
    @app.route('/health', methods=['GET'])
    def health():
        """Health check."""
        return health_check(flask_request)
    
    @app.route('/metrics', methods=['GET'])
    def metrics_endpoint():
        """Metrics endpoint."""
        return jsonify(metrics.to_dict())
    
    @app.route('/flush', methods=['POST'])
    def force_flush():
        """Force flush buffer."""
        inserter = get_inserter()
        result = inserter.flush()
        return jsonify(result)
    
    return app


# =============================================================================
# CLI / TESTING
# =============================================================================

if __name__ == '__main__':
    import sys
    
    if len(sys.argv) > 1 and sys.argv[1] == 'server':
        # Run as Flask server
        app = create_flask_app()
        port = int(os.getenv('PORT', '8080'))
        app.run(host='0.0.0.0', port=port, debug=True)
    else:
        # Test mode
        print("Pub/Sub Consumer - Test Mode")
        print(f"Config: {config}")
        print(f"Metrics: {metrics.to_dict()}")
        
        # Test message
        test_message = {
            "row": {
                "event_id": "test-123",
                "event_name": "PageView",
                "event_time": datetime.now(timezone.utc).isoformat(),
            },
            "metadata": {
                "event_id": "test-123",
                "event_name": "PageView",
                "received_at": datetime.now(timezone.utc).isoformat(),
            }
        }
        
        encoded = base64.b64encode(json.dumps(test_message).encode()).decode()
        parsed = parse_pubsub_message(encoded)
        print(f"Parsed: {parsed}")
        
        row = process_message(parsed)
        print(f"Processed row: {row}")
