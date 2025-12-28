"""
S.S.I. SHADOW — Vertex AI ML Pipeline
Versão: 1.0.0

Pipeline para treinamento de modelos:
- LTV Prediction
- Intent Score
- Anomaly Detection (Bot Filtering)

Requisitos:
- Google Cloud SDK configurado
- Vertex AI API habilitada
- Service Account com permissões
"""

import os
import json
import logging
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any, Tuple
from dataclasses import dataclass

# Google Cloud
try:
    from google.cloud import bigquery
    from google.cloud import aiplatform
    from google.cloud.aiplatform import TabularDataset, AutoMLTabularTrainingJob
    GOOGLE_CLOUD_AVAILABLE = True
except ImportError:
    GOOGLE_CLOUD_AVAILABLE = False
    print("⚠️ google-cloud-aiplatform não instalado. Execute: pip install google-cloud-aiplatform")

import pandas as pd
import numpy as np

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger('ssi_ml_pipeline')

# =============================================================================
# CONFIGURAÇÃO
# =============================================================================

@dataclass
class PipelineConfig:
    project_id: str
    region: str = 'us-central1'
    dataset_id: str = 'ssi_shadow'
    staging_bucket: str = 'ssi-shadow-ml-staging'
    
    # Treinamento
    training_budget_hours: int = 8
    optimization_objective: str = 'minimize-rmse'  # Para regressão
    
    # Features
    target_column_ltv: str = 'actual_ltv'
    target_column_intent: str = 'converted'
    target_column_anomaly: str = 'is_bot'

# =============================================================================
# FEATURE ENGINEERING
# =============================================================================

class FeatureEngineer:
    """Prepara features para treinamento de modelos"""
    
    def __init__(self, bq_client: bigquery.Client, config: PipelineConfig):
        self.bq = bq_client
        self.config = config
    
    def extract_ltv_features(self, lookback_days: int = 90) -> pd.DataFrame:
        """
        Extrai features para modelo de LTV prediction.
        
        Features:
        - Comportamento de navegação
        - Histórico de compras
        - Atributos de dispositivo/geo
        - Sinais de engajamento
        """
        query = f"""
        WITH user_sessions AS (
            SELECT
                ssi_id,
                COUNT(DISTINCT DATE(event_time)) as session_count,
                COUNT(*) as total_events,
                COUNTIF(event_name = 'PageView') as pageviews,
                COUNTIF(event_name = 'ViewContent') as product_views,
                COUNTIF(event_name = 'AddToCart') as add_to_carts,
                COUNTIF(event_name = 'InitiateCheckout') as checkouts,
                COUNTIF(event_name = 'Purchase') as purchases,
                AVG(trust_score) as avg_trust_score,
                MAX(CASE WHEN fbclid IS NOT NULL THEN 1 ELSE 0 END) as from_meta,
                MAX(CASE WHEN gclid IS NOT NULL THEN 1 ELSE 0 END) as from_google,
                MAX(CASE WHEN ttclid IS NOT NULL THEN 1 ELSE 0 END) as from_tiktok,
                MODE() WITHIN GROUP (ORDER BY device_type) as primary_device,
                MODE() WITHIN GROUP (ORDER BY country) as primary_country,
                MIN(event_time) as first_seen,
                MAX(event_time) as last_seen,
                TIMESTAMP_DIFF(MAX(event_time), MIN(event_time), HOUR) as lifespan_hours
            FROM `{self.config.project_id}.{self.config.dataset_id}.events`
            WHERE event_time >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL {lookback_days} DAY)
                AND ssi_id IS NOT NULL
            GROUP BY ssi_id
        ),
        
        user_purchases AS (
            SELECT
                ssi_id,
                SUM(CAST(JSON_EXTRACT_SCALAR(custom_data, '$.value') AS FLOAT64)) as total_revenue,
                COUNT(*) as purchase_count,
                AVG(CAST(JSON_EXTRACT_SCALAR(custom_data, '$.value') AS FLOAT64)) as avg_order_value,
                MAX(CAST(JSON_EXTRACT_SCALAR(custom_data, '$.value') AS FLOAT64)) as max_order_value
            FROM `{self.config.project_id}.{self.config.dataset_id}.events`
            WHERE event_name = 'Purchase'
                AND event_time >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL {lookback_days} DAY)
                AND ssi_id IS NOT NULL
            GROUP BY ssi_id
        )
        
        SELECT
            s.ssi_id,
            
            -- Features de sessão
            s.session_count,
            s.total_events,
            s.pageviews,
            s.product_views,
            s.add_to_carts,
            s.checkouts,
            s.purchases,
            
            -- Ratios de funil
            SAFE_DIVIDE(s.product_views, s.pageviews) as view_rate,
            SAFE_DIVIDE(s.add_to_carts, s.product_views) as atc_rate,
            SAFE_DIVIDE(s.checkouts, s.add_to_carts) as checkout_rate,
            SAFE_DIVIDE(s.purchases, s.checkouts) as purchase_rate,
            
            -- Qualidade de tráfego
            s.avg_trust_score,
            s.from_meta,
            s.from_google,
            s.from_tiktok,
            
            -- Device e Geo
            CASE s.primary_device WHEN 'mobile' THEN 1 WHEN 'tablet' THEN 2 ELSE 3 END as device_type_encoded,
            CASE s.primary_country 
                WHEN 'BR' THEN 1 
                WHEN 'US' THEN 2 
                WHEN 'PT' THEN 3 
                ELSE 0 
            END as country_encoded,
            
            -- Engajamento
            s.lifespan_hours,
            SAFE_DIVIDE(s.total_events, s.session_count) as events_per_session,
            
            -- Target: LTV real (últimos 90 dias)
            COALESCE(p.total_revenue, 0) as actual_ltv,
            COALESCE(p.purchase_count, 0) as actual_purchases,
            COALESCE(p.avg_order_value, 0) as actual_aov
            
        FROM user_sessions s
        LEFT JOIN user_purchases p ON s.ssi_id = p.ssi_id
        WHERE s.session_count >= 2  -- Pelo menos 2 sessões para ter dados
        """
        
        logger.info("Extraindo features de LTV...")
        df = self.bq.query(query).to_dataframe()
        logger.info(f"Extraídas {len(df)} amostras para LTV")
        
        return df
    
    def extract_intent_features(self, lookback_days: int = 30) -> pd.DataFrame:
        """
        Extrai features para modelo de Intent prediction.
        Prediz se visitante vai converter na sessão atual.
        """
        query = f"""
        WITH sessions AS (
            SELECT
                ssi_id,
                DATE(event_time) as session_date,
                
                -- Primeiro evento da sessão
                MIN(event_time) as session_start,
                
                -- Features da sessão
                COUNTIF(event_name = 'PageView') as pageviews,
                COUNTIF(event_name = 'ViewContent') as product_views,
                COUNTIF(event_name = 'AddToCart') as add_to_carts,
                COUNTIF(event_name = 'InitiateCheckout') as checkouts,
                
                -- Target: converteu nessa sessão?
                MAX(CASE WHEN event_name = 'Purchase' THEN 1 ELSE 0 END) as converted,
                
                -- Contexto
                ANY_VALUE(trust_score) as trust_score,
                ANY_VALUE(device_type) as device_type,
                MAX(CASE WHEN fbclid IS NOT NULL OR gclid IS NOT NULL THEN 1 ELSE 0 END) as from_paid,
                
                -- Tempo na sessão
                TIMESTAMP_DIFF(MAX(event_time), MIN(event_time), MINUTE) as session_duration_min
                
            FROM `{self.config.project_id}.{self.config.dataset_id}.events`
            WHERE event_time >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL {lookback_days} DAY)
                AND ssi_id IS NOT NULL
            GROUP BY ssi_id, DATE(event_time)
        ),
        
        user_history AS (
            SELECT
                ssi_id,
                COUNTIF(event_name = 'Purchase') as historical_purchases
            FROM `{self.config.project_id}.{self.config.dataset_id}.events`
            WHERE event_time < TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL {lookback_days} DAY)
                AND ssi_id IS NOT NULL
            GROUP BY ssi_id
        )
        
        SELECT
            s.ssi_id,
            s.session_date,
            
            -- Features de sessão
            s.pageviews,
            s.product_views,
            s.add_to_carts,
            s.checkouts,
            s.session_duration_min,
            
            -- Indicadores de intent
            CASE WHEN s.add_to_carts > 0 THEN 1 ELSE 0 END as has_cart,
            CASE WHEN s.checkouts > 0 THEN 1 ELSE 0 END as started_checkout,
            
            -- Contexto
            s.trust_score,
            CASE s.device_type WHEN 'mobile' THEN 1 WHEN 'tablet' THEN 2 ELSE 3 END as device_encoded,
            s.from_paid,
            
            -- Histórico
            COALESCE(h.historical_purchases, 0) as historical_purchases,
            CASE WHEN h.historical_purchases > 0 THEN 1 ELSE 0 END as is_returning_buyer,
            
            -- Target
            s.converted
            
        FROM sessions s
        LEFT JOIN user_history h ON s.ssi_id = h.ssi_id
        WHERE s.pageviews >= 1  -- Pelo menos 1 pageview
        """
        
        logger.info("Extraindo features de Intent...")
        df = self.bq.query(query).to_dataframe()
        logger.info(f"Extraídas {len(df)} amostras para Intent")
        
        return df
    
    def extract_anomaly_features(self, lookback_days: int = 7) -> pd.DataFrame:
        """
        Extrai features para detecção de anomalias (bots).
        """
        query = f"""
        SELECT
            ssi_id,
            event_time,
            
            -- Features de request
            trust_score,
            
            -- Padrões de navegação (por sessão)
            COUNT(*) OVER (PARTITION BY ssi_id, DATE(event_time)) as events_per_day,
            
            -- Tempo entre eventos (suspeito se muito rápido)
            TIMESTAMP_DIFF(
                event_time,
                LAG(event_time) OVER (PARTITION BY ssi_id ORDER BY event_time),
                SECOND
            ) as seconds_since_last_event,
            
            -- Device
            device_type,
            
            -- Geo (datacenters são suspeitos)
            country,
            
            -- Funil (bots normalmente não completam funil)
            event_name,
            
            -- Label (baseado em trust_score baixo como proxy)
            CASE WHEN trust_score < 0.3 THEN 1 ELSE 0 END as is_bot
            
        FROM `{self.config.project_id}.{self.config.dataset_id}.events`
        WHERE event_time >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL {lookback_days} DAY)
            AND ssi_id IS NOT NULL
        """
        
        logger.info("Extraindo features de Anomaly...")
        df = self.bq.query(query).to_dataframe()
        
        # Agregar por ssi_id (sessão)
        agg_df = df.groupby('ssi_id').agg({
            'trust_score': 'mean',
            'events_per_day': 'max',
            'seconds_since_last_event': ['mean', 'min'],
            'is_bot': 'max'
        }).reset_index()
        
        agg_df.columns = ['ssi_id', 'avg_trust_score', 'max_events_day', 
                          'avg_time_between_events', 'min_time_between_events', 'is_bot']
        
        logger.info(f"Extraídas {len(agg_df)} amostras para Anomaly")
        
        return agg_df

# =============================================================================
# VERTEX AI TRAINING
# =============================================================================

class VertexTrainer:
    """Gerencia treinamento de modelos no Vertex AI"""
    
    def __init__(self, config: PipelineConfig):
        self.config = config
        
        if GOOGLE_CLOUD_AVAILABLE:
            aiplatform.init(
                project=config.project_id,
                location=config.region,
                staging_bucket=f"gs://{config.staging_bucket}"
            )
    
    def upload_dataset(
        self, 
        df: pd.DataFrame, 
        display_name: str,
        target_column: str
    ) -> TabularDataset:
        """Upload DataFrame para Vertex AI Dataset"""
        
        # Salvar CSV temporário no GCS
        gcs_path = f"gs://{self.config.staging_bucket}/datasets/{display_name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        
        # Upload via BigQuery (mais eficiente para datasets grandes)
        logger.info(f"Uploading dataset: {display_name}")
        
        dataset = TabularDataset.create(
            display_name=display_name,
            gcs_source=gcs_path
        )
        
        logger.info(f"Dataset criado: {dataset.resource_name}")
        return dataset
    
    def train_automl_model(
        self,
        dataset: TabularDataset,
        display_name: str,
        target_column: str,
        optimization_objective: str = 'minimize-rmse',
        budget_hours: int = 8,
        column_specs: Optional[Dict[str, str]] = None
    ) -> Any:
        """
        Treina modelo AutoML Tabular.
        
        optimization_objective options:
        - 'minimize-rmse': Regressão
        - 'minimize-mae': Regressão
        - 'maximize-au-roc': Classificação binária
        - 'minimize-log-loss': Classificação
        """
        
        logger.info(f"Iniciando treinamento: {display_name}")
        logger.info(f"Objetivo: {optimization_objective}")
        logger.info(f"Budget: {budget_hours} horas")
        
        job = AutoMLTabularTrainingJob(
            display_name=display_name,
            optimization_prediction_type='regression' if 'minimize' in optimization_objective else 'classification',
            optimization_objective=optimization_objective,
            column_specs=column_specs
        )
        
        model = job.run(
            dataset=dataset,
            target_column=target_column,
            budget_milli_node_hours=budget_hours * 1000,
            model_display_name=f"{display_name}_model",
            disable_early_stopping=False
        )
        
        logger.info(f"Modelo treinado: {model.resource_name}")
        
        return model
    
    def export_model_onnx(self, model: Any, output_path: str) -> str:
        """
        Exporta modelo para ONNX para inference na edge.
        
        Nota: AutoML models podem não suportar export direto para ONNX.
        Nesse caso, usamos o modelo via endpoint.
        """
        logger.info(f"Exportando modelo para: {output_path}")
        
        try:
            model.export_model(
                export_format_id='tf-saved-model',
                artifact_destination=output_path
            )
            logger.info("Modelo exportado com sucesso")
            return output_path
        except Exception as e:
            logger.warning(f"Export direto não suportado: {e}")
            logger.info("Use o modelo via Vertex AI Endpoint para inference")
            return ""
    
    def deploy_endpoint(self, model: Any, display_name: str) -> Any:
        """Deploy modelo para endpoint de inference"""
        
        logger.info(f"Deploying model to endpoint: {display_name}")
        
        endpoint = model.deploy(
            deployed_model_display_name=display_name,
            machine_type='n1-standard-4',
            min_replica_count=1,
            max_replica_count=3
        )
        
        logger.info(f"Endpoint criado: {endpoint.resource_name}")
        
        return endpoint

# =============================================================================
# PIPELINE ORCHESTRATOR
# =============================================================================

class MLPipeline:
    """Orquestra todo o pipeline de ML"""
    
    def __init__(self, config: PipelineConfig):
        self.config = config
        self.bq_client = bigquery.Client(project=config.project_id) if GOOGLE_CLOUD_AVAILABLE else None
        self.feature_engineer = FeatureEngineer(self.bq_client, config) if self.bq_client else None
        self.trainer = VertexTrainer(config)
    
    def run_ltv_pipeline(self, lookback_days: int = 90) -> Dict[str, Any]:
        """Executa pipeline completo para LTV prediction"""
        
        logger.info("=" * 60)
        logger.info("INICIANDO PIPELINE: LTV Prediction")
        logger.info("=" * 60)
        
        results = {
            'model_type': 'ltv_prediction',
            'started_at': datetime.now().isoformat(),
            'status': 'running'
        }
        
        try:
            # 1. Extrair features
            df = self.feature_engineer.extract_ltv_features(lookback_days)
            results['samples'] = len(df)
            
            if len(df) < 100:
                raise ValueError(f"Amostras insuficientes: {len(df)}. Mínimo: 100")
            
            # 2. Upload dataset
            dataset = self.trainer.upload_dataset(
                df=df,
                display_name='ssi_ltv_features',
                target_column='actual_ltv'
            )
            results['dataset_id'] = dataset.resource_name
            
            # 3. Treinar modelo
            model = self.trainer.train_automl_model(
                dataset=dataset,
                display_name='ssi_ltv_model',
                target_column='actual_ltv',
                optimization_objective='minimize-rmse',
                budget_hours=self.config.training_budget_hours
            )
            results['model_id'] = model.resource_name
            
            # 4. Deploy endpoint
            endpoint = self.trainer.deploy_endpoint(
                model=model,
                display_name='ssi-ltv-endpoint'
            )
            results['endpoint_id'] = endpoint.resource_name
            
            results['status'] = 'success'
            results['completed_at'] = datetime.now().isoformat()
            
        except Exception as e:
            logger.error(f"Pipeline falhou: {e}")
            results['status'] = 'failed'
            results['error'] = str(e)
        
        return results
    
    def run_intent_pipeline(self, lookback_days: int = 30) -> Dict[str, Any]:
        """Executa pipeline para Intent prediction"""
        
        logger.info("=" * 60)
        logger.info("INICIANDO PIPELINE: Intent Prediction")
        logger.info("=" * 60)
        
        results = {
            'model_type': 'intent_prediction',
            'started_at': datetime.now().isoformat(),
            'status': 'running'
        }
        
        try:
            # 1. Extrair features
            df = self.feature_engineer.extract_intent_features(lookback_days)
            results['samples'] = len(df)
            
            if len(df) < 100:
                raise ValueError(f"Amostras insuficientes: {len(df)}. Mínimo: 100")
            
            # 2. Upload dataset
            dataset = self.trainer.upload_dataset(
                df=df,
                display_name='ssi_intent_features',
                target_column='converted'
            )
            results['dataset_id'] = dataset.resource_name
            
            # 3. Treinar modelo (classificação binária)
            model = self.trainer.train_automl_model(
                dataset=dataset,
                display_name='ssi_intent_model',
                target_column='converted',
                optimization_objective='maximize-au-roc',
                budget_hours=self.config.training_budget_hours
            )
            results['model_id'] = model.resource_name
            
            # 4. Deploy endpoint
            endpoint = self.trainer.deploy_endpoint(
                model=model,
                display_name='ssi-intent-endpoint'
            )
            results['endpoint_id'] = endpoint.resource_name
            
            results['status'] = 'success'
            results['completed_at'] = datetime.now().isoformat()
            
        except Exception as e:
            logger.error(f"Pipeline falhou: {e}")
            results['status'] = 'failed'
            results['error'] = str(e)
        
        return results
    
    def run_anomaly_pipeline(self, lookback_days: int = 7) -> Dict[str, Any]:
        """Executa pipeline para Anomaly detection"""
        
        logger.info("=" * 60)
        logger.info("INICIANDO PIPELINE: Anomaly Detection")
        logger.info("=" * 60)
        
        results = {
            'model_type': 'anomaly_detection',
            'started_at': datetime.now().isoformat(),
            'status': 'running'
        }
        
        try:
            # 1. Extrair features
            df = self.feature_engineer.extract_anomaly_features(lookback_days)
            results['samples'] = len(df)
            
            if len(df) < 100:
                raise ValueError(f"Amostras insuficientes: {len(df)}. Mínimo: 100")
            
            # 2. Upload dataset
            dataset = self.trainer.upload_dataset(
                df=df,
                display_name='ssi_anomaly_features',
                target_column='is_bot'
            )
            results['dataset_id'] = dataset.resource_name
            
            # 3. Treinar modelo (classificação binária)
            model = self.trainer.train_automl_model(
                dataset=dataset,
                display_name='ssi_anomaly_model',
                target_column='is_bot',
                optimization_objective='maximize-au-roc',
                budget_hours=self.config.training_budget_hours // 2  # Menos budget para anomaly
            )
            results['model_id'] = model.resource_name
            
            # 4. Deploy endpoint
            endpoint = self.trainer.deploy_endpoint(
                model=model,
                display_name='ssi-anomaly-endpoint'
            )
            results['endpoint_id'] = endpoint.resource_name
            
            results['status'] = 'success'
            results['completed_at'] = datetime.now().isoformat()
            
        except Exception as e:
            logger.error(f"Pipeline falhou: {e}")
            results['status'] = 'failed'
            results['error'] = str(e)
        
        return results
    
    def run_all_pipelines(self) -> Dict[str, Dict[str, Any]]:
        """Executa todos os pipelines"""
        
        results = {
            'ltv': self.run_ltv_pipeline(),
            'intent': self.run_intent_pipeline(),
            'anomaly': self.run_anomaly_pipeline()
        }
        
        # Salvar resultados
        output_path = f"/tmp/ssi_ml_pipeline_results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(output_path, 'w') as f:
            json.dump(results, f, indent=2)
        
        logger.info(f"Resultados salvos em: {output_path}")
        
        return results

# =============================================================================
# CLI
# =============================================================================

def main():
    import argparse
    
    parser = argparse.ArgumentParser(description='S.S.I. Shadow ML Pipeline')
    parser.add_argument('--project', required=True, help='GCP Project ID')
    parser.add_argument('--region', default='us-central1', help='GCP Region')
    parser.add_argument('--pipeline', choices=['ltv', 'intent', 'anomaly', 'all'], default='all')
    parser.add_argument('--budget-hours', type=int, default=8, help='Training budget in hours')
    
    args = parser.parse_args()
    
    config = PipelineConfig(
        project_id=args.project,
        region=args.region,
        training_budget_hours=args.budget_hours
    )
    
    pipeline = MLPipeline(config)
    
    if args.pipeline == 'all':
        results = pipeline.run_all_pipelines()
    elif args.pipeline == 'ltv':
        results = {'ltv': pipeline.run_ltv_pipeline()}
    elif args.pipeline == 'intent':
        results = {'intent': pipeline.run_intent_pipeline()}
    elif args.pipeline == 'anomaly':
        results = {'anomaly': pipeline.run_anomaly_pipeline()}
    
    print(json.dumps(results, indent=2))

if __name__ == '__main__':
    main()
