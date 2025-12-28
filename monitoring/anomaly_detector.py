"""
S.S.I. SHADOW - Anomaly Detection with Prophet
===============================================

Detecção de anomalias em tempo real usando Facebook Prophet.
Detecta quedas bruscas (site fora) e picos anormais (ataque bot).

Arquitetura:
    BigQuery (histórico) → Prophet (modelo) → Previsão → Z-Score → Alerta

Uso:
    # Como serviço standalone
    python -m monitoring.anomaly_detector

    # Integrado ao sistema
    from monitoring.anomaly_detector import AnomalyDetector
    detector = AnomalyDetector()
    await detector.run_check()

Schedule recomendado:
    - Produção: A cada 10 minutos
    - Staging: A cada 30 minutos

Configuração (env vars):
    - GCP_PROJECT_ID: Projeto do BigQuery
    - BQ_DATASET: Dataset (default: ssi_shadow)
    - ANOMALY_CHECK_INTERVAL_MINUTES: Intervalo (default: 10)
    - ANOMALY_ZSCORE_THRESHOLD: Threshold Z-Score (default: 3.0)
    - DEFENSE_MODE_API_URL: URL para ativar defense mode no Worker
    - SLACK_WEBHOOK_URL: Webhook do Slack para alertas
"""

import os
import json
import logging
import asyncio
from datetime import datetime, timedelta, timezone
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass, field
from enum import Enum
import numpy as np
import pandas as pd

# Google Cloud
try:
    from google.cloud import bigquery
    BIGQUERY_AVAILABLE = True
except ImportError:
    BIGQUERY_AVAILABLE = False
    bigquery = None

# Prophet
try:
    from prophet import Prophet
    PROPHET_AVAILABLE = True
except ImportError:
    try:
        from fbprophet import Prophet
        PROPHET_AVAILABLE = True
    except ImportError:
        PROPHET_AVAILABLE = False
        Prophet = None

# HTTP client
import httpx

# Local imports
from webhooks.services.alert_service import get_alert_service, AlertSeverity
from monitoring.metrics import metrics

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('anomaly_detector')


# =============================================================================
# CONFIGURATION
# =============================================================================

@dataclass
class AnomalyConfig:
    """Configuração do detector de anomalias."""
    
    # BigQuery
    gcp_project_id: str = field(default_factory=lambda: os.getenv('GCP_PROJECT_ID', ''))
    bq_dataset: str = field(default_factory=lambda: os.getenv('BQ_DATASET', 'ssi_shadow'))
    bq_events_table: str = field(default_factory=lambda: os.getenv('BQ_EVENTS_TABLE', 'events_raw'))
    
    # Detection
    check_interval_minutes: int = field(default_factory=lambda: int(os.getenv('ANOMALY_CHECK_INTERVAL_MINUTES', '10')))
    training_days: int = field(default_factory=lambda: int(os.getenv('ANOMALY_TRAINING_DAYS', '30')))
    zscore_threshold: float = field(default_factory=lambda: float(os.getenv('ANOMALY_ZSCORE_THRESHOLD', '3.0')))
    
    # Granularity
    aggregation_minutes: int = field(default_factory=lambda: int(os.getenv('ANOMALY_AGGREGATION_MINUTES', '10')))
    
    # Defense Mode
    defense_mode_api_url: str = field(default_factory=lambda: os.getenv('DEFENSE_MODE_API_URL', ''))
    defense_mode_api_key: str = field(default_factory=lambda: os.getenv('DEFENSE_MODE_API_KEY', ''))
    
    # Notifications
    slack_webhook_url: str = field(default_factory=lambda: os.getenv('SLACK_WEBHOOK_URL', ''))
    pagerduty_routing_key: str = field(default_factory=lambda: os.getenv('PAGERDUTY_ROUTING_KEY', ''))
    
    # Thresholds for different severities
    warning_zscore: float = field(default_factory=lambda: float(os.getenv('ANOMALY_WARNING_ZSCORE', '2.0')))
    critical_zscore: float = field(default_factory=lambda: float(os.getenv('ANOMALY_CRITICAL_ZSCORE', '3.0')))
    
    # Auto-defense
    auto_defense_on_spike: bool = field(default_factory=lambda: os.getenv('AUTO_DEFENSE_ON_SPIKE', 'true').lower() == 'true')
    
    def validate(self) -> List[str]:
        """Validate configuration."""
        errors = []
        if not self.gcp_project_id:
            errors.append("GCP_PROJECT_ID is required")
        if not PROPHET_AVAILABLE:
            errors.append("Prophet library not installed (pip install prophet)")
        if not BIGQUERY_AVAILABLE:
            errors.append("BigQuery library not installed (pip install google-cloud-bigquery)")
        return errors


# Global config
config = AnomalyConfig()


# =============================================================================
# ANOMALY TYPES
# =============================================================================

class AnomalyType(str, Enum):
    """Tipos de anomalia."""
    SPIKE = "spike"           # Pico anormal (possível ataque bot)
    DROP = "drop"             # Queda brusca (possível site fora)
    DRIFT = "drift"           # Desvio gradual
    NORMAL = "normal"         # Dentro do esperado


@dataclass
class AnomalyResult:
    """Resultado da detecção de anomalia."""
    timestamp: datetime
    metric: str
    actual_value: float
    predicted_value: float
    lower_bound: float
    upper_bound: float
    zscore: float
    anomaly_type: AnomalyType
    severity: str  # info, warning, critical
    message: str
    details: Dict[str, Any] = field(default_factory=dict)
    
    @property
    def is_anomaly(self) -> bool:
        return self.anomaly_type != AnomalyType.NORMAL
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'timestamp': self.timestamp.isoformat(),
            'metric': self.metric,
            'actual_value': self.actual_value,
            'predicted_value': round(self.predicted_value, 2),
            'lower_bound': round(self.lower_bound, 2),
            'upper_bound': round(self.upper_bound, 2),
            'zscore': round(self.zscore, 2),
            'anomaly_type': self.anomaly_type.value,
            'severity': self.severity,
            'message': self.message,
            'details': self.details,
        }


# =============================================================================
# BIGQUERY DATA FETCHER
# =============================================================================

class EventDataFetcher:
    """Busca dados de eventos do BigQuery."""
    
    def __init__(self, project_id: str, dataset: str, table: str):
        self.project_id = project_id
        self.dataset = dataset
        self.table = table
        self.client = bigquery.Client(project=project_id) if BIGQUERY_AVAILABLE else None
    
    def fetch_event_counts(
        self,
        start_time: datetime,
        end_time: datetime,
        aggregation_minutes: int = 10
    ) -> pd.DataFrame:
        """
        Busca contagem de eventos agregados por intervalo.
        
        Returns:
            DataFrame com colunas: ds (datetime), y (count)
        """
        if not self.client:
            raise RuntimeError("BigQuery client not available")
        
        query = f"""
        SELECT
            TIMESTAMP_TRUNC(event_time, MINUTE) AS minute_ts,
            COUNT(*) as event_count
        FROM `{self.project_id}.{self.dataset}.{self.table}`
        WHERE event_time >= @start_time
          AND event_time < @end_time
        GROUP BY minute_ts
        ORDER BY minute_ts
        """
        
        job_config = bigquery.QueryJobConfig(
            query_parameters=[
                bigquery.ScalarQueryParameter("start_time", "TIMESTAMP", start_time),
                bigquery.ScalarQueryParameter("end_time", "TIMESTAMP", end_time),
            ]
        )
        
        df = self.client.query(query, job_config=job_config).to_dataframe()
        
        if df.empty:
            return pd.DataFrame(columns=['ds', 'y'])
        
        # Resample para o intervalo desejado
        df['minute_ts'] = pd.to_datetime(df['minute_ts'])
        df = df.set_index('minute_ts')
        df = df.resample(f'{aggregation_minutes}T').sum()
        df = df.reset_index()
        df.columns = ['ds', 'y']
        
        return df
    
    def fetch_current_count(self, window_minutes: int = 10) -> Tuple[int, datetime]:
        """
        Busca contagem de eventos nos últimos N minutos.
        
        Returns:
            Tuple of (count, timestamp)
        """
        if not self.client:
            raise RuntimeError("BigQuery client not available")
        
        end_time = datetime.now(timezone.utc)
        start_time = end_time - timedelta(minutes=window_minutes)
        
        query = f"""
        SELECT COUNT(*) as cnt
        FROM `{self.project_id}.{self.dataset}.{self.table}`
        WHERE event_time >= @start_time
          AND event_time < @end_time
        """
        
        job_config = bigquery.QueryJobConfig(
            query_parameters=[
                bigquery.ScalarQueryParameter("start_time", "TIMESTAMP", start_time),
                bigquery.ScalarQueryParameter("end_time", "TIMESTAMP", end_time),
            ]
        )
        
        result = self.client.query(query, job_config=job_config).result()
        row = list(result)[0]
        
        return row.cnt, end_time
    
    def fetch_event_counts_by_type(
        self,
        start_time: datetime,
        end_time: datetime,
        event_names: List[str] = None
    ) -> pd.DataFrame:
        """
        Busca contagem de eventos por tipo.
        """
        if not self.client:
            raise RuntimeError("BigQuery client not available")
        
        event_filter = ""
        if event_names:
            names_str = ", ".join([f"'{n}'" for n in event_names])
            event_filter = f"AND event_name IN ({names_str})"
        
        query = f"""
        SELECT
            event_name,
            TIMESTAMP_TRUNC(event_time, MINUTE) AS minute_ts,
            COUNT(*) as event_count
        FROM `{self.project_id}.{self.dataset}.{self.table}`
        WHERE event_time >= @start_time
          AND event_time < @end_time
          {event_filter}
        GROUP BY event_name, minute_ts
        ORDER BY event_name, minute_ts
        """
        
        job_config = bigquery.QueryJobConfig(
            query_parameters=[
                bigquery.ScalarQueryParameter("start_time", "TIMESTAMP", start_time),
                bigquery.ScalarQueryParameter("end_time", "TIMESTAMP", end_time),
            ]
        )
        
        return self.client.query(query, job_config=job_config).to_dataframe()


# =============================================================================
# PROPHET MODEL WRAPPER
# =============================================================================

class ProphetAnomalyModel:
    """
    Wrapper para Prophet focado em detecção de anomalias.
    
    Features:
    - Sazonalidade diária e semanal
    - Holidays (opcional)
    - Confidence interval para anomalias
    """
    
    def __init__(
        self,
        interval_width: float = 0.95,
        seasonality_mode: str = 'multiplicative',
        daily_seasonality: bool = True,
        weekly_seasonality: bool = True,
        yearly_seasonality: bool = False
    ):
        if not PROPHET_AVAILABLE:
            raise RuntimeError("Prophet library not installed")
        
        self.interval_width = interval_width
        self.seasonality_mode = seasonality_mode
        self.daily_seasonality = daily_seasonality
        self.weekly_seasonality = weekly_seasonality
        self.yearly_seasonality = yearly_seasonality
        
        self.model: Optional[Prophet] = None
        self.last_train_time: Optional[datetime] = None
        self.training_data: Optional[pd.DataFrame] = None
    
    def train(self, df: pd.DataFrame) -> None:
        """
        Treina o modelo Prophet.
        
        Args:
            df: DataFrame com colunas 'ds' (datetime) e 'y' (valores)
        """
        if df.empty or len(df) < 10:
            raise ValueError("Insufficient data for training (need at least 10 points)")
        
        # Suppress Prophet logging
        logging.getLogger('prophet').setLevel(logging.WARNING)
        logging.getLogger('cmdstanpy').setLevel(logging.WARNING)
        
        self.model = Prophet(
            interval_width=self.interval_width,
            seasonality_mode=self.seasonality_mode,
            daily_seasonality=self.daily_seasonality,
            weekly_seasonality=self.weekly_seasonality,
            yearly_seasonality=self.yearly_seasonality,
            uncertainty_samples=1000,
        )
        
        # Add custom seasonality for hour of day
        self.model.add_seasonality(
            name='hourly',
            period=1/24,  # 1 hour in days
            fourier_order=5
        )
        
        self.model.fit(df)
        self.last_train_time = datetime.now(timezone.utc)
        self.training_data = df.copy()
        
        logger.info(f"Prophet model trained on {len(df)} data points")
    
    def predict(self, periods: int = 1, freq: str = '10T') -> pd.DataFrame:
        """
        Faz previsão para os próximos períodos.
        
        Returns:
            DataFrame com previsão e intervalos de confiança
        """
        if self.model is None:
            raise RuntimeError("Model not trained")
        
        future = self.model.make_future_dataframe(
            periods=periods,
            freq=freq,
            include_history=False
        )
        
        forecast = self.model.predict(future)
        
        return forecast[['ds', 'yhat', 'yhat_lower', 'yhat_upper']]
    
    def get_expected_value(self, timestamp: datetime) -> Tuple[float, float, float]:
        """
        Retorna valor esperado para um timestamp específico.
        
        Returns:
            Tuple of (predicted, lower_bound, upper_bound)
        """
        if self.model is None:
            raise RuntimeError("Model not trained")
        
        future = pd.DataFrame({'ds': [timestamp]})
        forecast = self.model.predict(future)
        
        row = forecast.iloc[0]
        return row['yhat'], row['yhat_lower'], row['yhat_upper']
    
    def calculate_zscore(
        self,
        actual: float,
        predicted: float,
        lower: float,
        upper: float
    ) -> float:
        """
        Calcula Z-Score normalizado.
        
        O Z-Score é calculado como a distância do valor real
        em relação ao intervalo de confiança.
        """
        # Estimar desvio padrão a partir do intervalo de confiança
        # Para 95% CI, o intervalo é aproximadamente 2 * 1.96 * std
        std_estimate = (upper - lower) / (2 * 1.96)
        
        if std_estimate == 0:
            return 0.0
        
        zscore = (actual - predicted) / std_estimate
        return zscore
    
    def detect_anomaly(
        self,
        actual: float,
        timestamp: datetime,
        zscore_threshold: float = 3.0
    ) -> AnomalyResult:
        """
        Detecta se um valor é anômalo.
        
        Returns:
            AnomalyResult com detalhes da análise
        """
        predicted, lower, upper = self.get_expected_value(timestamp)
        zscore = self.calculate_zscore(actual, predicted, lower, upper)
        
        # Determinar tipo de anomalia
        if abs(zscore) < config.warning_zscore:
            anomaly_type = AnomalyType.NORMAL
            severity = "info"
            message = "Event volume within expected range"
        elif zscore > config.critical_zscore:
            anomaly_type = AnomalyType.SPIKE
            severity = "critical"
            message = f"🚨 SPIKE DETECTED: Event volume {actual:.0f} is {zscore:.1f}σ above expected ({predicted:.0f})"
        elif zscore < -config.critical_zscore:
            anomaly_type = AnomalyType.DROP
            severity = "critical"
            message = f"🔴 DROP DETECTED: Event volume {actual:.0f} is {abs(zscore):.1f}σ below expected ({predicted:.0f})"
        elif zscore > config.warning_zscore:
            anomaly_type = AnomalyType.SPIKE
            severity = "warning"
            message = f"⚠️ Elevated event volume: {actual:.0f} (expected ~{predicted:.0f})"
        else:  # zscore < -warning
            anomaly_type = AnomalyType.DROP
            severity = "warning"
            message = f"⚠️ Reduced event volume: {actual:.0f} (expected ~{predicted:.0f})"
        
        return AnomalyResult(
            timestamp=timestamp,
            metric="event_count",
            actual_value=actual,
            predicted_value=predicted,
            lower_bound=lower,
            upper_bound=upper,
            zscore=zscore,
            anomaly_type=anomaly_type,
            severity=severity,
            message=message,
            details={
                'training_data_points': len(self.training_data) if self.training_data is not None else 0,
                'last_train_time': self.last_train_time.isoformat() if self.last_train_time else None,
            }
        )


# =============================================================================
# DEFENSE MODE CONTROLLER
# =============================================================================

class DefenseModeController:
    """
    Controla o modo de defesa do Worker.
    
    Quando ativado, o Worker aumenta o threshold de Trust Score
    para bloquear mais tráfego suspeito.
    """
    
    def __init__(self, api_url: str, api_key: str = ""):
        self.api_url = api_url
        self.api_key = api_key
        self.is_active = False
        self.activated_at: Optional[datetime] = None
        self.http_client = httpx.AsyncClient(timeout=10.0)
    
    async def activate(self, reason: str, duration_minutes: int = 30) -> bool:
        """
        Ativa o modo de defesa.
        
        Args:
            reason: Motivo da ativação
            duration_minutes: Duração em minutos (auto-desativa depois)
            
        Returns:
            True se ativou com sucesso
        """
        if not self.api_url:
            logger.warning("Defense mode API URL not configured")
            return False
        
        try:
            response = await self.http_client.post(
                f"{self.api_url}/api/defense-mode",
                json={
                    'enabled': True,
                    'reason': reason,
                    'duration_minutes': duration_minutes,
                    'trust_score_multiplier': 1.5,  # Aumenta threshold em 50%
                },
                headers={
                    'Authorization': f'Bearer {self.api_key}',
                    'Content-Type': 'application/json',
                }
            )
            
            if response.status_code == 200:
                self.is_active = True
                self.activated_at = datetime.now(timezone.utc)
                logger.info(f"Defense mode ACTIVATED: {reason}")
                return True
            else:
                logger.error(f"Failed to activate defense mode: {response.status_code}")
                return False
                
        except Exception as e:
            logger.error(f"Error activating defense mode: {e}")
            return False
    
    async def deactivate(self) -> bool:
        """Desativa o modo de defesa."""
        if not self.api_url:
            return False
        
        try:
            response = await self.http_client.post(
                f"{self.api_url}/api/defense-mode",
                json={
                    'enabled': False,
                },
                headers={
                    'Authorization': f'Bearer {self.api_key}',
                    'Content-Type': 'application/json',
                }
            )
            
            if response.status_code == 200:
                self.is_active = False
                self.activated_at = None
                logger.info("Defense mode DEACTIVATED")
                return True
            return False
            
        except Exception as e:
            logger.error(f"Error deactivating defense mode: {e}")
            return False
    
    async def close(self):
        await self.http_client.aclose()


# =============================================================================
# MAIN ANOMALY DETECTOR
# =============================================================================

class AnomalyDetector:
    """
    Detector principal de anomalias.
    
    Integra:
    - BigQuery para dados históricos
    - Prophet para previsão
    - AlertService para notificações
    - DefenseMode para proteção automática
    """
    
    def __init__(self, config: AnomalyConfig = None):
        self.config = config or AnomalyConfig()
        
        # Validate config
        errors = self.config.validate()
        if errors:
            for error in errors:
                logger.error(f"Config error: {error}")
        
        # Initialize components
        self.data_fetcher = EventDataFetcher(
            self.config.gcp_project_id,
            self.config.bq_dataset,
            self.config.bq_events_table
        )
        
        self.model = ProphetAnomalyModel() if PROPHET_AVAILABLE else None
        
        self.defense_controller = DefenseModeController(
            self.config.defense_mode_api_url,
            self.config.defense_mode_api_key
        )
        
        self.alert_service = get_alert_service()
        
        # State
        self.last_check_time: Optional[datetime] = None
        self.last_anomaly: Optional[AnomalyResult] = None
        self.check_count = 0
        self.anomaly_count = 0
        self._running = False
    
    async def train_model(self) -> bool:
        """
        Treina o modelo Prophet com dados históricos.
        
        Returns:
            True se treinou com sucesso
        """
        if not self.model:
            logger.error("Prophet not available")
            return False
        
        try:
            end_time = datetime.now(timezone.utc)
            start_time = end_time - timedelta(days=self.config.training_days)
            
            logger.info(f"Fetching training data from {start_time} to {end_time}")
            
            df = self.data_fetcher.fetch_event_counts(
                start_time,
                end_time,
                self.config.aggregation_minutes
            )
            
            if df.empty:
                logger.error("No training data available")
                return False
            
            logger.info(f"Training model with {len(df)} data points")
            self.model.train(df)
            
            # Record metric
            metrics.ml_predictions.labels(model='prophet_anomaly', prediction_type='train').inc()
            
            return True
            
        except Exception as e:
            logger.exception(f"Error training model: {e}")
            return False
    
    async def run_check(self) -> Optional[AnomalyResult]:
        """
        Executa uma verificação de anomalia.
        
        Returns:
            AnomalyResult se detectou anomalia, None se normal
        """
        self.check_count += 1
        self.last_check_time = datetime.now(timezone.utc)
        
        try:
            # Ensure model is trained
            if self.model is None or self.model.model is None:
                logger.info("Training model for the first time...")
                if not await self.train_model():
                    return None
            
            # Get current event count
            current_count, timestamp = self.data_fetcher.fetch_current_count(
                self.config.aggregation_minutes
            )
            
            # Detect anomaly
            result = self.model.detect_anomaly(
                actual=current_count,
                timestamp=timestamp,
                zscore_threshold=self.config.zscore_threshold
            )
            
            self.last_anomaly = result
            
            # Record metrics
            metrics.ml_predictions.labels(
                model='prophet_anomaly',
                prediction_type='inference'
            ).inc()
            
            # Handle anomaly
            if result.is_anomaly:
                self.anomaly_count += 1
                await self._handle_anomaly(result)
            
            return result if result.is_anomaly else None
            
        except Exception as e:
            logger.exception(f"Error in anomaly check: {e}")
            return None
    
    async def _handle_anomaly(self, result: AnomalyResult) -> None:
        """Handle detected anomaly."""
        logger.warning(f"ANOMALY DETECTED: {result.message}")
        
        # Send alert via AlertService
        await self._send_alert(result)
        
        # Activate defense mode if spike
        if result.anomaly_type == AnomalyType.SPIKE and self.config.auto_defense_on_spike:
            await self.defense_controller.activate(
                reason=f"Auto-activated due to traffic spike: {result.message}",
                duration_minutes=30
            )
        
        # Send to Slack
        if self.config.slack_webhook_url:
            await self._send_slack_alert(result)
        
        # Send to PagerDuty (critical only)
        if result.severity == 'critical' and self.config.pagerduty_routing_key:
            await self._send_pagerduty_alert(result)
    
    async def _send_alert(self, result: AnomalyResult) -> None:
        """Send alert via AlertService."""
        try:
            from webhooks.channels.notifications import get_notification_service
            
            notification_service = get_notification_service()
            
            severity_map = {
                'info': AlertSeverity.INFO,
                'warning': AlertSeverity.WARNING,
                'critical': AlertSeverity.CRITICAL,
            }
            
            await notification_service.send(
                channels=['slack', 'telegram'],
                title=f"🔮 Anomaly Detected: {result.anomaly_type.value.upper()}",
                message=result.message,
                data={
                    'Current Value': f"{result.actual_value:.0f}",
                    'Expected Value': f"{result.predicted_value:.0f}",
                    'Z-Score': f"{result.zscore:.2f}σ",
                    'Time': result.timestamp.strftime('%Y-%m-%d %H:%M UTC'),
                    'Type': result.anomaly_type.value,
                },
                severity=severity_map.get(result.severity, AlertSeverity.WARNING)
            )
        except Exception as e:
            logger.error(f"Error sending alert: {e}")
    
    async def _send_slack_alert(self, result: AnomalyResult) -> None:
        """Send alert to Slack."""
        if not self.config.slack_webhook_url:
            return
        
        color = {
            'info': '#36a64f',
            'warning': '#ffcc00',
            'critical': '#ff0000',
        }.get(result.severity, '#808080')
        
        emoji = {
            AnomalyType.SPIKE: '📈',
            AnomalyType.DROP: '📉',
            AnomalyType.DRIFT: '↗️',
        }.get(result.anomaly_type, '⚠️')
        
        payload = {
            'attachments': [{
                'color': color,
                'title': f"{emoji} SSI Shadow: {result.anomaly_type.value.upper()} Detected",
                'text': result.message,
                'fields': [
                    {'title': 'Current', 'value': f"{result.actual_value:.0f}", 'short': True},
                    {'title': 'Expected', 'value': f"{result.predicted_value:.0f}", 'short': True},
                    {'title': 'Z-Score', 'value': f"{result.zscore:.2f}σ", 'short': True},
                    {'title': 'Severity', 'value': result.severity.upper(), 'short': True},
                ],
                'footer': 'SSI Shadow Anomaly Detection',
                'ts': int(result.timestamp.timestamp()),
            }]
        }
        
        try:
            async with httpx.AsyncClient() as client:
                await client.post(self.config.slack_webhook_url, json=payload)
        except Exception as e:
            logger.error(f"Error sending Slack alert: {e}")
    
    async def _send_pagerduty_alert(self, result: AnomalyResult) -> None:
        """Send critical alert to PagerDuty."""
        if not self.config.pagerduty_routing_key:
            return
        
        payload = {
            'routing_key': self.config.pagerduty_routing_key,
            'event_action': 'trigger',
            'dedup_key': f"ssi-anomaly-{result.anomaly_type.value}-{result.timestamp.strftime('%Y%m%d%H')}",
            'payload': {
                'summary': result.message,
                'severity': 'critical',
                'source': 'ssi-shadow-anomaly-detector',
                'timestamp': result.timestamp.isoformat(),
                'custom_details': result.to_dict(),
            }
        }
        
        try:
            async with httpx.AsyncClient() as client:
                await client.post(
                    'https://events.pagerduty.com/v2/enqueue',
                    json=payload
                )
        except Exception as e:
            logger.error(f"Error sending PagerDuty alert: {e}")
    
    async def start(self) -> None:
        """Start continuous monitoring loop."""
        self._running = True
        logger.info(f"Starting anomaly detector (interval: {self.config.check_interval_minutes}min)")
        
        # Initial training
        await self.train_model()
        
        while self._running:
            try:
                result = await self.run_check()
                
                if result:
                    logger.info(f"Check complete - ANOMALY: {result.anomaly_type.value}")
                else:
                    logger.info("Check complete - Normal")
                
                # Retrain model daily
                if self.model and self.model.last_train_time:
                    hours_since_train = (datetime.now(timezone.utc) - self.model.last_train_time).total_seconds() / 3600
                    if hours_since_train > 24:
                        logger.info("Retraining model (daily)")
                        await self.train_model()
                
            except Exception as e:
                logger.exception(f"Error in monitoring loop: {e}")
            
            await asyncio.sleep(self.config.check_interval_minutes * 60)
    
    async def stop(self) -> None:
        """Stop monitoring."""
        self._running = False
        await self.defense_controller.close()
        logger.info("Anomaly detector stopped")
    
    def get_status(self) -> Dict[str, Any]:
        """Get current status."""
        return {
            'running': self._running,
            'check_count': self.check_count,
            'anomaly_count': self.anomaly_count,
            'last_check_time': self.last_check_time.isoformat() if self.last_check_time else None,
            'last_anomaly': self.last_anomaly.to_dict() if self.last_anomaly else None,
            'model_trained': self.model is not None and self.model.model is not None,
            'defense_mode_active': self.defense_controller.is_active,
            'config': {
                'check_interval_minutes': self.config.check_interval_minutes,
                'zscore_threshold': self.config.zscore_threshold,
                'training_days': self.config.training_days,
            }
        }


# =============================================================================
# FASTAPI ROUTES
# =============================================================================

try:
    from fastapi import APIRouter, HTTPException, BackgroundTasks
    from pydantic import BaseModel
    
    anomaly_router = APIRouter(prefix="/api/anomaly", tags=["anomaly"])
    
    # Global detector instance
    _detector: Optional[AnomalyDetector] = None
    
    def get_detector() -> AnomalyDetector:
        global _detector
        if _detector is None:
            _detector = AnomalyDetector()
        return _detector
    
    @anomaly_router.get("/status")
    async def get_status():
        """Get anomaly detector status."""
        detector = get_detector()
        return detector.get_status()
    
    @anomaly_router.post("/check")
    async def run_check():
        """Manually trigger an anomaly check."""
        detector = get_detector()
        result = await detector.run_check()
        
        if result:
            return {"status": "anomaly_detected", "result": result.to_dict()}
        return {"status": "normal"}
    
    @anomaly_router.post("/train")
    async def train_model(background_tasks: BackgroundTasks):
        """Retrain the Prophet model."""
        detector = get_detector()
        background_tasks.add_task(detector.train_model)
        return {"status": "training_started"}
    
    class DefenseModeRequest(BaseModel):
        enabled: bool
        reason: str = ""
        duration_minutes: int = 30
    
    @anomaly_router.post("/defense-mode")
    async def set_defense_mode(request: DefenseModeRequest):
        """Manually control defense mode."""
        detector = get_detector()
        
        if request.enabled:
            success = await detector.defense_controller.activate(
                reason=request.reason or "Manual activation",
                duration_minutes=request.duration_minutes
            )
        else:
            success = await detector.defense_controller.deactivate()
        
        return {
            "success": success,
            "defense_mode_active": detector.defense_controller.is_active
        }
    
    @anomaly_router.get("/history")
    async def get_history(hours: int = 24):
        """Get anomaly detection history."""
        # TODO: Implement history storage
        return {"message": "Not implemented yet"}

except ImportError:
    anomaly_router = None


# =============================================================================
# CLI
# =============================================================================

async def main():
    """Main entry point for standalone execution."""
    import argparse
    
    parser = argparse.ArgumentParser(description='SSI Shadow Anomaly Detector')
    parser.add_argument('--once', action='store_true', help='Run single check and exit')
    parser.add_argument('--train', action='store_true', help='Train model and exit')
    parser.add_argument('--status', action='store_true', help='Show status and exit')
    args = parser.parse_args()
    
    detector = AnomalyDetector()
    
    if args.train:
        print("Training model...")
        success = await detector.train_model()
        print(f"Training {'succeeded' if success else 'failed'}")
        return
    
    if args.once:
        print("Running single check...")
        result = await detector.run_check()
        if result:
            print(f"ANOMALY DETECTED: {json.dumps(result.to_dict(), indent=2)}")
        else:
            print("No anomaly detected")
        return
    
    if args.status:
        print(json.dumps(detector.get_status(), indent=2))
        return
    
    # Run continuous monitoring
    try:
        await detector.start()
    except KeyboardInterrupt:
        print("\nShutting down...")
        await detector.stop()


if __name__ == '__main__':
    asyncio.run(main())
