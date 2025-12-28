"""
S.S.I. SHADOW — MLOps Pipeline
AUTOMATED RETRAINING & EDGE DEPLOYMENT

Responsabilidades:
1. Retreinar modelos LTV/Intent automaticamente (7-15 dias)
2. Exportar para ONNX
3. Upload para Cloudflare KV (edge inference)
4. Monitorar data drift e model decay
5. Alertas via Telegram

Fluxo:
BigQuery (dados) → Vertex AI (treino) → ONNX (export) → GCS → Cloudflare KV
"""

import os
import json
import logging
import hashlib
import tempfile
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List, Tuple
from dataclasses import dataclass
import base64

import requests

# GCP
try:
    from google.cloud import bigquery
    from google.cloud import storage
    from google.cloud import aiplatform
    from google.cloud.aiplatform import TabularDataset
    VERTEX_AVAILABLE = True
except ImportError:
    VERTEX_AVAILABLE = False
    print("⚠️ google-cloud-aiplatform não instalado")

# ONNX
try:
    import onnx
    import onnxruntime as ort
    ONNX_AVAILABLE = True
except ImportError:
    ONNX_AVAILABLE = False
    print("⚠️ onnxruntime não instalado")

# Sklearn para fallback
try:
    import pandas as pd
    import numpy as np
    from sklearn.ensemble import GradientBoostingRegressor, GradientBoostingClassifier
    from sklearn.model_selection import train_test_split
    from sklearn.metrics import mean_squared_error, roc_auc_score
    import skl2onnx
    from skl2onnx import convert_sklearn
    from skl2onnx.common.data_types import FloatTensorType
    SKLEARN_AVAILABLE = True
except ImportError:
    SKLEARN_AVAILABLE = False
    print("⚠️ scikit-learn não instalado")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger('ssi_mlops')

# =============================================================================
# CONFIGURAÇÃO
# =============================================================================

@dataclass
class MLOpsConfig:
    # GCP
    project_id: str
    region: str = 'us-central1'
    dataset_id: str = 'ssi_shadow'
    
    # Storage
    models_bucket: str = ''  # Auto-set se não fornecido
    
    # Cloudflare
    cf_account_id: str = ''
    cf_api_token: str = ''
    cf_kv_namespace_id: str = ''
    
    # Training
    training_budget_hours: int = 2
    min_samples: int = 1000
    test_size: float = 0.2
    
    # Retraining
    retrain_interval_days: int = 7
    decay_threshold: float = 0.70  # Retreinar se acurácia < 70%
    
    # Alertas
    telegram_bot_token: str = ''
    telegram_chat_id: str = ''

# =============================================================================
# DATA DRIFT DETECTOR
# =============================================================================

class DataDriftDetector:
    """
    Detecta mudanças na distribuição dos dados
    que podem degradar performance do modelo
    """
    
    def __init__(self, bq_client, config: MLOpsConfig):
        self.bq = bq_client
        self.config = config
    
    def calculate_feature_stats(self, days: int = 7) -> Dict[str, Dict]:
        """
        Calcula estatísticas das features na janela recente
        """
        query = f"""
        SELECT
            AVG(trust_score) as avg_trust_score,
            STDDEV(trust_score) as std_trust_score,
            AVG(intent_score) as avg_intent_score,
            STDDEV(intent_score) as std_intent_score,
            AVG(ltv_score) as avg_ltv_score,
            STDDEV(ltv_score) as std_ltv_score,
            COUNT(*) as sample_count,
            COUNTIF(event_name = 'Purchase') / COUNT(*) as conversion_rate
        FROM `{self.config.project_id}.{self.config.dataset_id}.events`
        WHERE event_time >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL {days} DAY)
        """
        
        result = list(self.bq.query(query).result())[0]
        
        return {
            'trust_score': {'mean': result.avg_trust_score, 'std': result.std_trust_score},
            'intent_score': {'mean': result.avg_intent_score, 'std': result.std_intent_score},
            'ltv_score': {'mean': result.avg_ltv_score, 'std': result.std_ltv_score},
            'conversion_rate': result.conversion_rate,
            'sample_count': result.sample_count
        }
    
    def detect_drift(
        self, 
        current_stats: Dict, 
        baseline_stats: Dict,
        threshold: float = 0.3
    ) -> Tuple[bool, List[str]]:
        """
        Detecta drift comparando estatísticas atuais vs baseline
        
        Usa z-score: se |current - baseline| > threshold * std
        """
        drifted_features = []
        
        for feature in ['trust_score', 'intent_score', 'ltv_score']:
            if feature not in current_stats or feature not in baseline_stats:
                continue
            
            current_mean = current_stats[feature]['mean'] or 0
            baseline_mean = baseline_stats[feature]['mean'] or 0
            baseline_std = baseline_stats[feature]['std'] or 1
            
            if baseline_std > 0:
                z_score = abs(current_mean - baseline_mean) / baseline_std
                if z_score > threshold:
                    drifted_features.append(f"{feature} (z={z_score:.2f})")
        
        # Drift em conversion rate
        if abs((current_stats.get('conversion_rate', 0) or 0) - 
               (baseline_stats.get('conversion_rate', 0) or 0)) > 0.05:
            drifted_features.append("conversion_rate")
        
        return len(drifted_features) > 0, drifted_features

# =============================================================================
# MODEL TRAINER (Fallback com Sklearn)
# =============================================================================

class SklearnTrainer:
    """
    Trainer local usando Sklearn
    Usado quando Vertex AI não disponível ou para testes rápidos
    """
    
    def __init__(self, bq_client, config: MLOpsConfig):
        self.bq = bq_client
        self.config = config
    
    def prepare_ltv_data(self, days: int = 90) -> pd.DataFrame:
        """
        Prepara dados para modelo LTV
        """
        query = f"""
        WITH user_features AS (
            SELECT
                ssi_id,
                COUNT(*) as total_events,
                COUNTIF(event_name = 'PageView') as pageviews,
                COUNTIF(event_name = 'ViewContent') as product_views,
                COUNTIF(event_name = 'AddToCart') as add_to_carts,
                COUNTIF(event_name = 'InitiateCheckout') as checkouts,
                COUNTIF(event_name = 'Purchase') as purchases,
                AVG(trust_score) as avg_trust_score,
                AVG(intent_score) as avg_intent_score,
                SUM(CASE WHEN event_name = 'Purchase' 
                    THEN CAST(JSON_EXTRACT_SCALAR(custom_data, '$.value') AS FLOAT64) 
                    ELSE 0 END) as total_value
            FROM `{self.config.project_id}.{self.config.dataset_id}.events`
            WHERE event_time >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL {days} DAY)
            GROUP BY ssi_id
            HAVING total_events >= 3
        )
        SELECT * FROM user_features
        """
        
        return self.bq.query(query).to_dataframe()
    
    def train_ltv_model(self) -> Tuple[Any, Dict[str, float]]:
        """
        Treina modelo de LTV com Gradient Boosting
        """
        logger.info("Preparando dados para LTV...")
        df = self.prepare_ltv_data()
        
        if len(df) < self.config.min_samples:
            raise ValueError(f"Amostras insuficientes: {len(df)} < {self.config.min_samples}")
        
        # Features
        feature_cols = [
            'pageviews', 'product_views', 'add_to_carts', 
            'checkouts', 'purchases', 'avg_trust_score', 'avg_intent_score'
        ]
        
        X = df[feature_cols].fillna(0)
        y = df['total_value'].fillna(0)
        
        X_train, X_test, y_train, y_test = train_test_split(
            X, y, test_size=self.config.test_size, random_state=42
        )
        
        logger.info(f"Training com {len(X_train)} amostras...")
        
        model = GradientBoostingRegressor(
            n_estimators=100,
            max_depth=5,
            learning_rate=0.1,
            random_state=42
        )
        
        model.fit(X_train, y_train)
        
        # Métricas
        y_pred = model.predict(X_test)
        rmse = np.sqrt(mean_squared_error(y_test, y_pred))
        
        # R² como proxy de accuracy
        r2 = model.score(X_test, y_test)
        
        metrics = {
            'rmse': float(rmse),
            'r2': float(r2),
            'samples_train': len(X_train),
            'samples_test': len(X_test),
            'feature_importance': dict(zip(feature_cols, model.feature_importances_.tolist()))
        }
        
        logger.info(f"LTV Model - RMSE: {rmse:.2f}, R²: {r2:.3f}")
        
        return model, metrics
    
    def train_intent_model(self) -> Tuple[Any, Dict[str, float]]:
        """
        Treina modelo de Intent (classificação)
        """
        query = f"""
        SELECT
            ssi_id,
            COUNTIF(event_name = 'PageView') as pageviews,
            COUNTIF(event_name = 'ViewContent') as product_views,
            COUNTIF(event_name = 'AddToCart') as add_to_carts,
            AVG(trust_score) as avg_trust_score,
            MAX(CASE WHEN event_name IN ('InitiateCheckout', 'Purchase') THEN 1 ELSE 0 END) as converted
        FROM `{self.config.project_id}.{self.config.dataset_id}.events`
        WHERE event_time >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 30 DAY)
        GROUP BY ssi_id
        HAVING pageviews >= 1
        """
        
        df = self.bq.query(query).to_dataframe()
        
        if len(df) < self.config.min_samples:
            raise ValueError(f"Amostras insuficientes: {len(df)}")
        
        feature_cols = ['pageviews', 'product_views', 'add_to_carts', 'avg_trust_score']
        
        X = df[feature_cols].fillna(0)
        y = df['converted'].fillna(0)
        
        X_train, X_test, y_train, y_test = train_test_split(
            X, y, test_size=self.config.test_size, random_state=42
        )
        
        model = GradientBoostingClassifier(
            n_estimators=100,
            max_depth=4,
            learning_rate=0.1,
            random_state=42
        )
        
        model.fit(X_train, y_train)
        
        # Métricas
        y_prob = model.predict_proba(X_test)[:, 1]
        auc = roc_auc_score(y_test, y_prob)
        
        metrics = {
            'auc': float(auc),
            'samples_train': len(X_train),
            'samples_test': len(X_test)
        }
        
        logger.info(f"Intent Model - AUC: {auc:.3f}")
        
        return model, metrics

# =============================================================================
# ONNX EXPORTER
# =============================================================================

class ONNXExporter:
    """
    Exporta modelos sklearn para ONNX
    """
    
    @staticmethod
    def export_to_onnx(
        model, 
        feature_names: List[str],
        model_name: str
    ) -> bytes:
        """
        Converte modelo sklearn para ONNX
        """
        if not SKLEARN_AVAILABLE:
            raise RuntimeError("skl2onnx não disponível")
        
        # Definir input type
        initial_type = [('features', FloatTensorType([None, len(feature_names)]))]
        
        # Converter
        onnx_model = convert_sklearn(
            model, 
            initial_types=initial_type,
            target_opset=12
        )
        
        # Adicionar metadata
        onnx_model.doc_string = json.dumps({
            'model_name': model_name,
            'feature_names': feature_names,
            'exported_at': datetime.now().isoformat(),
            'version': '1.0'
        })
        
        # Serializar
        return onnx_model.SerializeToString()
    
    @staticmethod
    def validate_onnx(onnx_bytes: bytes) -> bool:
        """
        Valida modelo ONNX
        """
        try:
            model = onnx.load_from_string(onnx_bytes)
            onnx.checker.check_model(model)
            
            # Testar inferência
            session = ort.InferenceSession(onnx_bytes)
            input_name = session.get_inputs()[0].name
            input_shape = session.get_inputs()[0].shape
            
            # Dummy inference
            dummy_input = np.zeros((1, input_shape[1]), dtype=np.float32)
            session.run(None, {input_name: dummy_input})
            
            return True
        except Exception as e:
            logger.error(f"ONNX validation failed: {e}")
            return False

# =============================================================================
# EDGE DEPLOYER (Cloudflare KV)
# =============================================================================

class EdgeDeployer:
    """
    Deploy de modelos ONNX para Cloudflare KV
    """
    
    def __init__(self, config: MLOpsConfig):
        self.config = config
        self.base_url = f"https://api.cloudflare.com/client/v4/accounts/{config.cf_account_id}"
    
    def _request(self, method: str, endpoint: str, data: Any = None) -> Optional[Dict]:
        """
        Request para Cloudflare API
        """
        headers = {
            'Authorization': f'Bearer {self.config.cf_api_token}',
            'Content-Type': 'application/json'
        }
        
        url = f"{self.base_url}{endpoint}"
        
        try:
            if method == 'PUT':
                # Para KV, o valor vai no body como text/plain
                headers['Content-Type'] = 'text/plain'
                response = requests.put(url, headers=headers, data=data, timeout=60)
            else:
                response = requests.request(method, url, headers=headers, json=data, timeout=30)
            
            if response.status_code in [200, 201]:
                return response.json() if response.text else {'success': True}
            else:
                logger.error(f"Cloudflare API error: {response.status_code} - {response.text}")
                return None
                
        except Exception as e:
            logger.error(f"Cloudflare request failed: {e}")
            return None
    
    def deploy_model(self, model_name: str, onnx_bytes: bytes, metadata: Dict) -> bool:
        """
        Deploy modelo ONNX para KV
        
        Armazena:
        - model:{name}:onnx -> modelo serializado em base64
        - model:{name}:meta -> metadata JSON
        """
        if not self.config.cf_kv_namespace_id:
            logger.warning("Cloudflare KV namespace não configurado")
            return False
        
        namespace_id = self.config.cf_kv_namespace_id
        
        # Upload modelo (base64)
        model_key = f"model:{model_name}:onnx"
        model_b64 = base64.b64encode(onnx_bytes).decode('utf-8')
        
        result = self._request(
            'PUT',
            f"/storage/kv/namespaces/{namespace_id}/values/{model_key}",
            data=model_b64
        )
        
        if not result:
            return False
        
        # Upload metadata
        meta_key = f"model:{model_name}:meta"
        metadata['deployed_at'] = datetime.now().isoformat()
        metadata['size_bytes'] = len(onnx_bytes)
        
        result = self._request(
            'PUT',
            f"/storage/kv/namespaces/{namespace_id}/values/{meta_key}",
            data=json.dumps(metadata)
        )
        
        if result:
            logger.info(f"✓ Model {model_name} deployed to edge ({len(onnx_bytes)} bytes)")
            return True
        
        return False

# =============================================================================
# MLOPS PIPELINE PRINCIPAL
# =============================================================================

class MLOpsPipeline:
    """
    Pipeline completo de MLOps
    """
    
    def __init__(self, config: MLOpsConfig):
        self.config = config
        
        # Clients
        self.bq = bigquery.Client(project=config.project_id) if VERTEX_AVAILABLE else None
        self.storage = storage.Client(project=config.project_id) if VERTEX_AVAILABLE else None
        
        # Components
        self.trainer = SklearnTrainer(self.bq, config) if self.bq else None
        self.drift_detector = DataDriftDetector(self.bq, config) if self.bq else None
        self.edge_deployer = EdgeDeployer(config)
        
        # Estado
        self.baseline_stats: Optional[Dict] = None
    
    def check_should_retrain(self, model_name: str) -> Tuple[bool, str]:
        """
        Verifica se modelo deve ser retreinado
        """
        # 1. Verificar data drift
        if self.drift_detector:
            current_stats = self.drift_detector.calculate_feature_stats(7)
            
            if self.baseline_stats:
                has_drift, drifted = self.drift_detector.detect_drift(
                    current_stats, 
                    self.baseline_stats
                )
                
                if has_drift:
                    return True, f"Data drift detectado: {', '.join(drifted)}"
            
            self.baseline_stats = current_stats
        
        # 2. Verificar tempo desde último treino
        # (implementar checagem via BigQuery ou GCS metadata)
        
        return False, "Sem necessidade de retrain"
    
    def run_training_pipeline(
        self, 
        model_type: str = 'ltv',
        force: bool = False
    ) -> Dict[str, Any]:
        """
        Executa pipeline completo de treinamento
        """
        results = {
            'model_type': model_type,
            'started_at': datetime.now().isoformat(),
            'success': False,
            'metrics': {},
            'deployed': False
        }
        
        try:
            # 1. Verificar necessidade de retrain
            if not force:
                should_retrain, reason = self.check_should_retrain(model_type)
                if not should_retrain:
                    results['skipped'] = True
                    results['reason'] = reason
                    return results
            
            # 2. Treinar modelo
            logger.info(f"Training {model_type} model...")
            
            if model_type == 'ltv':
                model, metrics = self.trainer.train_ltv_model()
                feature_names = ['pageviews', 'product_views', 'add_to_carts', 
                               'checkouts', 'purchases', 'avg_trust_score', 'avg_intent_score']
            elif model_type == 'intent':
                model, metrics = self.trainer.train_intent_model()
                feature_names = ['pageviews', 'product_views', 'add_to_carts', 'avg_trust_score']
            else:
                raise ValueError(f"Unknown model type: {model_type}")
            
            results['metrics'] = metrics
            
            # 3. Exportar para ONNX
            logger.info("Exporting to ONNX...")
            onnx_bytes = ONNXExporter.export_to_onnx(model, feature_names, model_type)
            
            # 4. Validar ONNX
            if not ONNXExporter.validate_onnx(onnx_bytes):
                raise RuntimeError("ONNX validation failed")
            
            results['onnx_size_bytes'] = len(onnx_bytes)
            
            # 5. Upload para GCS
            if self.storage and self.config.models_bucket:
                bucket = self.storage.bucket(self.config.models_bucket)
                blob_name = f"models/{model_type}/{datetime.now().strftime('%Y%m%d_%H%M%S')}.onnx"
                blob = bucket.blob(blob_name)
                blob.upload_from_string(onnx_bytes)
                results['gcs_path'] = f"gs://{self.config.models_bucket}/{blob_name}"
                logger.info(f"Model saved to GCS: {results['gcs_path']}")
            
            # 6. Deploy para Edge (Cloudflare KV)
            if self.config.cf_api_token:
                deployed = self.edge_deployer.deploy_model(
                    model_type, 
                    onnx_bytes,
                    metrics
                )
                results['deployed'] = deployed
            
            results['success'] = True
            results['completed_at'] = datetime.now().isoformat()
            
            # 7. Enviar alerta de sucesso
            self._send_alert(
                f"✅ Modelo {model_type} treinado com sucesso",
                f"Métricas: {json.dumps(metrics, indent=2)}\nDeployed: {results['deployed']}"
            )
            
        except Exception as e:
            logger.error(f"Training pipeline failed: {e}")
            results['error'] = str(e)
            
            self._send_alert(
                f"❌ Falha no treinamento {model_type}",
                str(e)
            )
        
        return results
    
    def run_drift_check(self) -> Dict[str, Any]:
        """
        Executa verificação de data drift
        """
        if not self.drift_detector:
            return {'error': 'Drift detector not available'}
        
        current = self.drift_detector.calculate_feature_stats(7)
        previous = self.drift_detector.calculate_feature_stats(14)
        
        has_drift, drifted_features = self.drift_detector.detect_drift(current, previous)
        
        result = {
            'timestamp': datetime.now().isoformat(),
            'has_drift': has_drift,
            'drifted_features': drifted_features,
            'current_stats': current,
            'action': 'retrain_recommended' if has_drift else 'no_action'
        }
        
        if has_drift:
            self._send_alert(
                "⚠️ Data Drift Detectado",
                f"Features afetadas: {', '.join(drifted_features)}\n\nAção: Retreinamento recomendado"
            )
        
        return result
    
    def _send_alert(self, title: str, message: str):
        """
        Envia alerta via Telegram
        """
        if not self.config.telegram_bot_token or not self.config.telegram_chat_id:
            return
        
        text = f"<b>{title}</b>\n\n{message}"
        
        try:
            requests.post(
                f"https://api.telegram.org/bot{self.config.telegram_bot_token}/sendMessage",
                json={
                    'chat_id': self.config.telegram_chat_id,
                    'text': text,
                    'parse_mode': 'HTML'
                },
                timeout=10
            )
        except Exception as e:
            logger.error(f"Failed to send alert: {e}")

# =============================================================================
# CLI
# =============================================================================

def main():
    import argparse
    
    parser = argparse.ArgumentParser(description='SSI Shadow MLOps Pipeline')
    parser.add_argument('--project', required=True, help='GCP Project ID')
    parser.add_argument('--action', required=True, choices=['train', 'drift-check', 'all'])
    parser.add_argument('--model', choices=['ltv', 'intent', 'all'], default='all')
    parser.add_argument('--force', action='store_true', help='Force retrain')
    parser.add_argument('--cf-account', help='Cloudflare Account ID')
    parser.add_argument('--cf-token', help='Cloudflare API Token')
    parser.add_argument('--cf-kv', help='Cloudflare KV Namespace ID')
    
    args = parser.parse_args()
    
    config = MLOpsConfig(
        project_id=args.project,
        models_bucket=f"{args.project}-ssi-models",
        cf_account_id=args.cf_account or os.getenv('CF_ACCOUNT_ID', ''),
        cf_api_token=args.cf_token or os.getenv('CF_API_TOKEN', ''),
        cf_kv_namespace_id=args.cf_kv or os.getenv('CF_KV_NAMESPACE_ID', ''),
        telegram_bot_token=os.getenv('TELEGRAM_BOT_TOKEN', ''),
        telegram_chat_id=os.getenv('TELEGRAM_CHAT_ID', '')
    )
    
    pipeline = MLOpsPipeline(config)
    
    if args.action in ['train', 'all']:
        if args.model in ['ltv', 'all']:
            result = pipeline.run_training_pipeline('ltv', force=args.force)
            print(json.dumps(result, indent=2))
        
        if args.model in ['intent', 'all']:
            result = pipeline.run_training_pipeline('intent', force=args.force)
            print(json.dumps(result, indent=2))
    
    if args.action in ['drift-check', 'all']:
        result = pipeline.run_drift_check()
        print(json.dumps(result, indent=2))

if __name__ == '__main__':
    main()
