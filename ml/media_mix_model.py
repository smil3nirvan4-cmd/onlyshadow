"""
S.S.I. SHADOW — MEDIA MIX MODELING (MMM)
MARKETING ATTRIBUTION + BUDGET OPTIMIZATION

Implementa MMM usando abordagem Bayesian similar ao Meta Robyn / Google LightweightMMM.

Features:
- Decomposição de contribuição por canal
- Efeitos de saturação (diminishing returns)
- Efeitos de adstock (carryover)
- Otimização de budget
- Cenários what-if

MMM vs MTA:
- MMM: Top-down, usa dados agregados, inclui offline
- MTA: Bottom-up, usa dados individuais, só digital

Melhor resultado: Usar ambos (MMM + MTA) com triangulação.
"""

import os
import json
import logging
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass
import numpy as np
from scipy.optimize import minimize, differential_evolution
from scipy.stats import norm
import warnings

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger('ssi_mmm')

# =============================================================================
# TYPES
# =============================================================================

@dataclass
class ChannelConfig:
    """Configuração de canal para MMM"""
    name: str
    spend_column: str
    
    # Adstock parameters
    adstock_type: str = 'geometric'  # 'geometric' | 'weibull'
    decay_rate: float = 0.5  # Taxa de decaimento
    max_lag: int = 8  # Semanas de carryover
    
    # Saturation parameters
    saturation_type: str = 'hill'  # 'hill' | 'logistic'
    saturation_alpha: float = 2.0  # Curvatura
    saturation_gamma: float = 0.5  # Ponto de inflexão
    
    # Priors (para Bayesian)
    prior_mean: float = 0.0
    prior_std: float = 1.0


@dataclass
class MMMConfig:
    """Configuração do modelo MMM"""
    # Data
    date_column: str = 'date'
    target_column: str = 'revenue'
    
    # Model
    include_trend: bool = True
    include_seasonality: bool = True
    seasonality_period: int = 52  # Semanal
    
    # Training
    train_size: float = 0.8
    n_iterations: int = 1000
    
    # Optimization
    optimize_hyperparams: bool = True
    budget_constraint: float = None  # Total budget para otimização


@dataclass
class MMMResult:
    """Resultado do modelo MMM"""
    # Fit metrics
    r_squared: float
    mape: float
    rmse: float
    
    # Channel contributions
    channel_contributions: Dict[str, float]
    channel_roi: Dict[str, float]
    channel_marginal_roi: Dict[str, float]
    
    # Decomposition
    baseline: float
    trend_contribution: float
    seasonality_contribution: float
    media_contribution: float
    
    # Optimal allocation
    optimal_budget: Dict[str, float]
    expected_lift: float
    
    # Parameters
    fitted_params: Dict[str, Any]


# =============================================================================
# ADSTOCK TRANSFORMATIONS
# =============================================================================

def geometric_adstock(x: np.ndarray, decay: float) -> np.ndarray:
    """
    Adstock geométrico: efeito decai exponencialmente.
    
    x[t]_adstock = x[t] + decay * x[t-1]_adstock
    """
    result = np.zeros_like(x, dtype=float)
    result[0] = x[0]
    
    for t in range(1, len(x)):
        result[t] = x[t] + decay * result[t-1]
    
    return result


def weibull_adstock(
    x: np.ndarray, 
    shape: float, 
    scale: float, 
    max_lag: int = 13
) -> np.ndarray:
    """
    Adstock Weibull: mais flexível, permite pico atrasado.
    
    Útil para campanhas de awareness que têm efeito atrasado.
    """
    # Criar kernel Weibull
    lags = np.arange(max_lag)
    
    # Weibull PDF
    if shape > 0 and scale > 0:
        kernel = (shape / scale) * ((lags / scale) ** (shape - 1)) * np.exp(-((lags / scale) ** shape))
        kernel = kernel / kernel.sum()  # Normalizar
    else:
        kernel = np.zeros(max_lag)
        kernel[0] = 1.0
    
    # Convolução
    result = np.convolve(x, kernel, mode='full')[:len(x)]
    
    return result


# =============================================================================
# SATURATION FUNCTIONS
# =============================================================================

def hill_saturation(x: np.ndarray, alpha: float, gamma: float) -> np.ndarray:
    """
    Função Hill: diminishing returns suave.
    
    f(x) = x^alpha / (gamma^alpha + x^alpha)
    
    alpha: curvatura (quanto maior, mais abrupta a saturação)
    gamma: ponto de inflexão (50% da saturação)
    """
    x_normalized = x / (x.max() + 1e-10)
    return x_normalized ** alpha / (gamma ** alpha + x_normalized ** alpha + 1e-10)


def logistic_saturation(x: np.ndarray, k: float, m: float) -> np.ndarray:
    """
    Função Logística: S-curve.
    
    f(x) = 1 / (1 + exp(-k * (x - m)))
    """
    x_normalized = x / (x.max() + 1e-10)
    return 1 / (1 + np.exp(-k * (x_normalized - m)))


# =============================================================================
# MEDIA MIX MODEL
# =============================================================================

class MediaMixModel:
    """
    Media Mix Model com transformações de adstock e saturação.
    """
    
    def __init__(
        self,
        config: MMMConfig,
        channels: List[ChannelConfig]
    ):
        self.config = config
        self.channels = {ch.name: ch for ch in channels}
        self.fitted = False
        self.params = {}
        self.result = None
    
    def _transform_channel(
        self,
        x: np.ndarray,
        channel: ChannelConfig
    ) -> np.ndarray:
        """Aplica transformações de adstock e saturação"""
        
        # 1. Adstock
        if channel.adstock_type == 'geometric':
            x_adstock = geometric_adstock(x, channel.decay_rate)
        elif channel.adstock_type == 'weibull':
            x_adstock = weibull_adstock(
                x, 
                shape=channel.decay_rate * 2,
                scale=channel.max_lag / 2
            )
        else:
            x_adstock = x
        
        # 2. Saturação
        if channel.saturation_type == 'hill':
            x_saturated = hill_saturation(
                x_adstock,
                channel.saturation_alpha,
                channel.saturation_gamma
            )
        elif channel.saturation_type == 'logistic':
            x_saturated = logistic_saturation(
                x_adstock,
                k=channel.saturation_alpha,
                m=channel.saturation_gamma
            )
        else:
            x_saturated = x_adstock
        
        return x_saturated
    
    def _create_seasonality_features(self, n: int) -> np.ndarray:
        """Cria features de sazonalidade (Fourier)"""
        t = np.arange(n)
        period = self.config.seasonality_period
        
        features = []
        for i in range(1, 4):  # 3 harmônicos
            features.append(np.sin(2 * np.pi * i * t / period))
            features.append(np.cos(2 * np.pi * i * t / period))
        
        return np.column_stack(features)
    
    def _create_trend_feature(self, n: int) -> np.ndarray:
        """Cria feature de tendência (linear + quadrática)"""
        t = np.arange(n) / n
        return np.column_stack([t, t**2])
    
    def _objective(
        self,
        params: np.ndarray,
        X: np.ndarray,
        y: np.ndarray,
        channel_names: List[str]
    ) -> float:
        """Função objetivo para otimização"""
        
        n_channels = len(channel_names)
        
        # Extrair parâmetros
        intercept = params[0]
        channel_coeffs = params[1:n_channels+1]
        other_coeffs = params[n_channels+1:]
        
        # Predição
        y_pred = intercept + X[:, :n_channels] @ channel_coeffs
        
        if len(other_coeffs) > 0:
            y_pred += X[:, n_channels:] @ other_coeffs
        
        # MSE
        mse = np.mean((y - y_pred) ** 2)
        
        # Regularização L2
        reg = 0.01 * np.sum(channel_coeffs ** 2)
        
        return mse + reg
    
    def fit(
        self,
        data: Dict[str, np.ndarray]
    ) -> MMMResult:
        """
        Ajusta o modelo aos dados.
        
        data: Dict com arrays para cada coluna
              {'date': [...], 'revenue': [...], 'meta_spend': [...], ...}
        """
        logger.info("Fitting MMM model...")
        
        y = data[self.config.target_column]
        n = len(y)
        
        # Transformar canais
        X_channels = []
        channel_names = []
        
        for name, channel in self.channels.items():
            spend = data.get(channel.spend_column, np.zeros(n))
            transformed = self._transform_channel(spend, channel)
            X_channels.append(transformed)
            channel_names.append(name)
        
        X = np.column_stack(X_channels)
        
        # Adicionar trend e sazonalidade
        n_channel_features = X.shape[1]
        
        if self.config.include_trend:
            trend_features = self._create_trend_feature(n)
            X = np.column_stack([X, trend_features])
        
        if self.config.include_seasonality:
            seasonality_features = self._create_seasonality_features(n)
            X = np.column_stack([X, seasonality_features])
        
        # Número de parâmetros
        n_params = 1 + X.shape[1]  # intercept + features
        
        # Bounds para parâmetros
        bounds = [(None, None)]  # intercept
        bounds += [(0, None)] * len(channel_names)  # canais (positivos)
        bounds += [(None, None)] * (n_params - 1 - len(channel_names))  # outros
        
        # Initial guess
        x0 = np.zeros(n_params)
        x0[0] = y.mean()
        
        # Otimizar
        if self.config.optimize_hyperparams:
            result = minimize(
                self._objective,
                x0,
                args=(X, y, channel_names),
                method='L-BFGS-B',
                bounds=bounds,
                options={'maxiter': self.config.n_iterations}
            )
            optimal_params = result.x
        else:
            # OLS simples
            X_with_intercept = np.column_stack([np.ones(n), X])
            optimal_params = np.linalg.lstsq(X_with_intercept, y, rcond=None)[0]
        
        # Extrair resultados
        intercept = optimal_params[0]
        channel_coeffs = dict(zip(channel_names, optimal_params[1:len(channel_names)+1]))
        
        # Calcular predições
        y_pred = intercept + X @ optimal_params[1:]
        
        # Métricas
        ss_res = np.sum((y - y_pred) ** 2)
        ss_tot = np.sum((y - y.mean()) ** 2)
        r_squared = 1 - (ss_res / ss_tot)
        
        mape = np.mean(np.abs((y - y_pred) / (y + 1e-10))) * 100
        rmse = np.sqrt(np.mean((y - y_pred) ** 2))
        
        # Contribuições por canal
        total_media = sum(optimal_params[1:len(channel_names)+1] * X[:, :len(channel_names)].mean(axis=0))
        
        channel_contributions = {}
        channel_roi = {}
        channel_marginal_roi = {}
        
        for i, name in enumerate(channel_names):
            coeff = optimal_params[1 + i]
            spend = data.get(self.channels[name].spend_column, np.zeros(n))
            
            contribution = coeff * X[:, i].sum()
            channel_contributions[name] = contribution
            
            total_spend = spend.sum()
            if total_spend > 0:
                channel_roi[name] = contribution / total_spend
                
                # Marginal ROI (derivada)
                channel_marginal_roi[name] = coeff * 0.5  # Aproximação
        
        # Baseline e decomposição
        baseline = intercept * n
        trend_contrib = 0
        seasonality_contrib = 0
        
        if self.config.include_trend:
            trend_coeffs = optimal_params[len(channel_names)+1:len(channel_names)+3]
            trend_features = self._create_trend_feature(n)
            trend_contrib = (trend_features @ trend_coeffs).sum()
        
        # Normalizar contribuições
        total_contrib = abs(baseline) + abs(trend_contrib) + sum(abs(c) for c in channel_contributions.values())
        
        # Store params
        self.params = {
            'intercept': intercept,
            'channel_coeffs': channel_coeffs,
            'all_params': optimal_params
        }
        self.fitted = True
        
        # Criar resultado
        self.result = MMMResult(
            r_squared=r_squared,
            mape=mape,
            rmse=rmse,
            channel_contributions=channel_contributions,
            channel_roi=channel_roi,
            channel_marginal_roi=channel_marginal_roi,
            baseline=baseline / total_contrib if total_contrib > 0 else 0,
            trend_contribution=trend_contrib / total_contrib if total_contrib > 0 else 0,
            seasonality_contribution=seasonality_contrib / total_contrib if total_contrib > 0 else 0,
            media_contribution=sum(channel_contributions.values()) / total_contrib if total_contrib > 0 else 0,
            optimal_budget={},  # Calculado separadamente
            expected_lift=0,
            fitted_params=self.params
        )
        
        logger.info(f"MMM fit complete. R²: {r_squared:.3f}, MAPE: {mape:.1f}%")
        
        return self.result
    
    def optimize_budget(
        self,
        total_budget: float,
        current_spend: Dict[str, float],
        constraints: Dict[str, Tuple[float, float]] = None
    ) -> Dict[str, Any]:
        """
        Otimiza alocação de budget entre canais.
        
        Usa programação não-linear para maximizar ROI total
        respeitando restrições de budget.
        """
        if not self.fitted:
            raise ValueError("Model must be fitted first")
        
        channel_names = list(self.channels.keys())
        n_channels = len(channel_names)
        
        # Bounds padrão: 0.5x a 2x do spend atual
        if constraints is None:
            constraints = {}
        
        bounds = []
        for name in channel_names:
            current = current_spend.get(name, 0)
            if name in constraints:
                bounds.append(constraints[name])
            else:
                bounds.append((current * 0.3, current * 3.0))
        
        def objective(spend_alloc):
            """Negativo do ROI total (minimizamos)"""
            total_return = 0
            
            for i, name in enumerate(channel_names):
                coeff = self.params['channel_coeffs'].get(name, 0)
                channel = self.channels[name]
                
                # Simular transformação
                x = np.array([spend_alloc[i]])
                x_transformed = self._transform_channel(x, channel)
                
                total_return += coeff * x_transformed[0]
            
            return -total_return  # Negativo porque minimizamos
        
        def budget_constraint(spend_alloc):
            """Restrição de budget total"""
            return total_budget - sum(spend_alloc)
        
        # Otimizar
        result = minimize(
            objective,
            x0=[current_spend.get(name, total_budget/n_channels) for name in channel_names],
            method='SLSQP',
            bounds=bounds,
            constraints={'type': 'eq', 'fun': budget_constraint},
            options={'maxiter': 500}
        )
        
        optimal_spend = dict(zip(channel_names, result.x))
        
        # Calcular lift esperado
        current_roi = sum(
            self.params['channel_coeffs'].get(name, 0) * 
            self._transform_channel(np.array([current_spend.get(name, 0)]), self.channels[name])[0]
            for name in channel_names
        )
        
        optimal_roi = -result.fun
        expected_lift = (optimal_roi - current_roi) / (current_roi + 1e-10)
        
        return {
            'optimal_budget': optimal_spend,
            'expected_return': optimal_roi,
            'current_return': current_roi,
            'expected_lift': expected_lift,
            'optimization_success': result.success
        }
    
    def simulate_scenario(
        self,
        scenario_spend: Dict[str, float],
        weeks: int = 12
    ) -> Dict[str, Any]:
        """
        Simula cenário what-if.
        
        scenario_spend: Spend semanal por canal
        weeks: Número de semanas para simular
        """
        if not self.fitted:
            raise ValueError("Model must be fitted first")
        
        total_return = 0
        channel_returns = {}
        
        for name, weekly_spend in scenario_spend.items():
            if name not in self.channels:
                continue
            
            channel = self.channels[name]
            coeff = self.params['channel_coeffs'].get(name, 0)
            
            # Simular série temporal
            spend_series = np.ones(weeks) * weekly_spend
            transformed = self._transform_channel(spend_series, channel)
            
            channel_return = coeff * transformed.sum()
            channel_returns[name] = channel_return
            total_return += channel_return
        
        total_spend = sum(scenario_spend.values()) * weeks
        
        return {
            'total_spend': total_spend,
            'total_return': total_return,
            'overall_roi': total_return / (total_spend + 1e-10),
            'channel_returns': channel_returns,
            'channel_roi': {
                name: ret / (scenario_spend.get(name, 1) * weeks)
                for name, ret in channel_returns.items()
            }
        }


# =============================================================================
# HELPER: CREATE MODEL FROM BIGQUERY DATA
# =============================================================================

def create_mmm_from_bigquery(
    bq_client,
    project_id: str,
    lookback_weeks: int = 52
) -> Tuple[MediaMixModel, Dict[str, np.ndarray]]:
    """
    Cria modelo MMM a partir de dados do BigQuery.
    """
    query = f"""
    WITH weekly_data AS (
        SELECT
            DATE_TRUNC(date, WEEK) as week,
            SUM(CASE WHEN channel = 'meta_paid' THEN cost ELSE 0 END) as meta_spend,
            SUM(CASE WHEN channel = 'google_paid' THEN cost ELSE 0 END) as google_spend,
            SUM(CASE WHEN channel = 'tiktok_paid' THEN cost ELSE 0 END) as tiktok_spend
        FROM `{project_id}.ssi_shadow.platform_costs`
        WHERE date >= DATE_SUB(CURRENT_DATE(), INTERVAL {lookback_weeks} WEEK)
        GROUP BY week
    ),
    weekly_revenue AS (
        SELECT
            DATE_TRUNC(DATE(event_time), WEEK) as week,
            SUM(SAFE_CAST(JSON_EXTRACT_SCALAR(custom_data, '$.value') AS FLOAT64)) as revenue
        FROM `{project_id}.ssi_shadow.events`
        WHERE event_name = 'Purchase'
        AND event_time >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL {lookback_weeks} WEEK)
        GROUP BY week
    )
    SELECT
        wd.week,
        COALESCE(wr.revenue, 0) as revenue,
        COALESCE(wd.meta_spend, 0) as meta_spend,
        COALESCE(wd.google_spend, 0) as google_spend,
        COALESCE(wd.tiktok_spend, 0) as tiktok_spend
    FROM weekly_data wd
    LEFT JOIN weekly_revenue wr ON wd.week = wr.week
    ORDER BY wd.week
    """
    
    rows = list(bq_client.query(query).result())
    
    data = {
        'date': np.array([row.week for row in rows]),
        'revenue': np.array([float(row.revenue or 0) for row in rows]),
        'meta_spend': np.array([float(row.meta_spend or 0) for row in rows]),
        'google_spend': np.array([float(row.google_spend or 0) for row in rows]),
        'tiktok_spend': np.array([float(row.tiktok_spend or 0) for row in rows])
    }
    
    # Configurar canais
    channels = [
        ChannelConfig(
            name='meta',
            spend_column='meta_spend',
            decay_rate=0.6,
            saturation_alpha=2.0,
            saturation_gamma=0.4
        ),
        ChannelConfig(
            name='google',
            spend_column='google_spend',
            decay_rate=0.4,  # Menor decay (efeito mais imediato)
            saturation_alpha=2.5,
            saturation_gamma=0.5
        ),
        ChannelConfig(
            name='tiktok',
            spend_column='tiktok_spend',
            decay_rate=0.7,  # Maior decay (efeito mais duradouro)
            saturation_alpha=1.5,
            saturation_gamma=0.3
        )
    ]
    
    config = MMMConfig(
        include_trend=True,
        include_seasonality=True
    )
    
    model = MediaMixModel(config, channels)
    
    return model, data


# =============================================================================
# CLI
# =============================================================================

def main():
    import argparse
    
    parser = argparse.ArgumentParser(description='SSI Shadow MMM')
    parser.add_argument('--action', choices=['fit', 'optimize', 'simulate'])
    parser.add_argument('--project', help='GCP Project ID')
    parser.add_argument('--budget', type=float, help='Total budget for optimization')
    
    args = parser.parse_args()
    
    if args.action == 'fit':
        # Demo com dados sintéticos
        np.random.seed(42)
        n = 52
        
        data = {
            'date': np.arange(n),
            'revenue': 100000 + np.random.randn(n) * 10000 + np.linspace(0, 20000, n),
            'meta_spend': 5000 + np.random.randn(n) * 1000,
            'google_spend': 3000 + np.random.randn(n) * 500,
            'tiktok_spend': 2000 + np.random.randn(n) * 300
        }
        
        channels = [
            ChannelConfig(name='meta', spend_column='meta_spend'),
            ChannelConfig(name='google', spend_column='google_spend'),
            ChannelConfig(name='tiktok', spend_column='tiktok_spend')
        ]
        
        model = MediaMixModel(MMMConfig(), channels)
        result = model.fit(data)
        
        print(f"\nMMM Results:")
        print(f"R²: {result.r_squared:.3f}")
        print(f"MAPE: {result.mape:.1f}%")
        print(f"\nChannel Contributions:")
        for name, contrib in result.channel_contributions.items():
            roi = result.channel_roi.get(name, 0)
            print(f"  {name}: {contrib:,.0f} (ROI: {roi:.2f}x)")

if __name__ == '__main__':
    main()
