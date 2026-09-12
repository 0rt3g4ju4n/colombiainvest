# -*- coding: utf-8 -*-
"""Analisis de sensibilidad de la ponderacion.

Responde la pregunta previsible del jurado: si los pesos son juicio experto,
que tan dependiente del juicio es el resultado.

Dos ejercicios:
1. Comparacion entre esquemas declarados (base contra alternativos).
2. Perturbacion aleatoria de los pesos, tipo Monte Carlo, para medir la
   estabilidad del ranking bajo incertidumbre en el juicio experto.

Metricas reportadas: correlacion de Spearman y de Kendall entre rankings,
desplazamiento medio y maximo de posiciones, y estabilidad del top-k.
"""
from __future__ import annotations

import logging
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
from scipy import stats

from ..config import DIMENSIONES, ConfigModelo
from .score import ESCALA, aplicar_esquema, calcular_dimensiones

log = logging.getLogger(__name__)


def _rankear(serie: pd.Series) -> pd.Series:
    return serie.rank(ascending=False, method="min")


def comparar_esquemas(
    df: pd.DataFrame, cfg: ConfigModelo, esquemas: Optional[List[str]] = None
) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """Recalcula el score bajo cada esquema y compara los rankings.

    Devuelve (tabla de metricas, tabla de rankings por proyecto).
    """
    esquemas = esquemas or cfg.esquemas_disponibles
    puntajes, _ = calcular_dimensiones(df, cfg)

    scores = pd.DataFrame(index=df.index)
    for nombre in esquemas:
        scores[nombre] = aplicar_esquema(puntajes, cfg.esquema(nombre))

    rankings = scores.apply(_rankear)
    rankings.insert(0, "bpin", df["bpin"].values)
    rankings.insert(1, "nombreproyecto", df.get("nombreproyecto", pd.Series(index=df.index)).values)

    referencia = esquemas[0]
    filas = []
    for nombre in esquemas[1:]:
        r0, r1 = rankings[referencia], rankings[nombre]
        desplazamiento = (r1 - r0).abs()
        filas.append(
            {
                "esquema": nombre,
                "descripcion": cfg.descripcion_esquema(nombre),
                "spearman": float(stats.spearmanr(r0, r1).statistic),
                "kendall_tau": float(stats.kendalltau(r0, r1).statistic),
                "desplaz_medio": float(desplazamiento.mean()),
                "desplaz_mediano": float(desplazamiento.median()),
                "desplaz_max": int(desplazamiento.max()),
                "pct_mueve_mas_10": float((desplazamiento > 10).mean()),
                "top10_estable": _estabilidad_topk(r0, r1, 10),
                "top20_estable": _estabilidad_topk(r0, r1, 20),
            }
        )
    metricas = pd.DataFrame(filas)
    log.info("Sensibilidad entre esquemas calculada sobre %d proyectos", len(df))
    return metricas, rankings


def _estabilidad_topk(r0: pd.Series, r1: pd.Series, k: int) -> float:
    """Proporcion del top-k del esquema de referencia que sigue en el top-k."""
    a = set(r0.nsmallest(k).index)
    b = set(r1.nsmallest(k).index)
    return len(a & b) / k if k else float("nan")


def perturbacion_montecarlo(
    df: pd.DataFrame,
    cfg: ConfigModelo,
    n_simulaciones: int = 1000,
    ruido: float = 0.15,
    esquema_base: Optional[Dict[str, float]] = None,
    semilla: Optional[int] = None,
) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """Perturba los pesos con ruido relativo y mide la estabilidad del ranking.

    ruido = 0.15 significa que cada peso se multiplica por un factor
    aleatorio en torno a 1 con desviacion del 15%, y luego se renormaliza
    para que el esquema siga sumando 1.
    """
    rng = np.random.default_rng(semilla if semilla is not None else cfg.semilla)
    base = esquema_base or cfg.esquema_base
    puntajes, _ = calcular_dimensiones(df, cfg)

    score_base = aplicar_esquema(puntajes, base)
    rank_base = _rankear(score_base)

    matriz_rank = np.zeros((n_simulaciones, len(df)))
    spearmans = np.zeros(n_simulaciones)

    pesos_base = np.array([base[d] for d in DIMENSIONES])
    mat_dim = puntajes[DIMENSIONES].to_numpy()

    for i in range(n_simulaciones):
        factor = rng.normal(1.0, ruido, size=len(DIMENSIONES))
        p = np.clip(pesos_base * factor, 1e-6, None)
        p = p / p.sum()
        s = mat_dim @ p
        r = pd.Series(s).rank(ascending=False, method="min").to_numpy()
        matriz_rank[i] = r
        spearmans[i] = stats.spearmanr(rank_base.to_numpy(), r).statistic

    resumen = pd.DataFrame(
        {
            "n_simulaciones": [n_simulaciones],
            "ruido_relativo": [ruido],
            "spearman_medio": [float(spearmans.mean())],
            "spearman_p05": [float(np.percentile(spearmans, 5))],
            "spearman_min": [float(spearmans.min())],
            "desplaz_medio_abs": [float(np.abs(matriz_rank - rank_base.to_numpy()).mean())],
        }
    )

    por_proyecto = pd.DataFrame(
        {
            "bpin": df["bpin"].values,
            "nombreproyecto": df.get("nombreproyecto", pd.Series(index=df.index)).values,
            "score_base": score_base.round(2).values,
            "rank_base": rank_base.astype(int).values,
            "rank_medio": matriz_rank.mean(axis=0).round(1),
            "rank_p05": np.percentile(matriz_rank, 5, axis=0).round(0),
            "rank_p95": np.percentile(matriz_rank, 95, axis=0).round(0),
            "amplitud_ic90": (
                np.percentile(matriz_rank, 95, axis=0) - np.percentile(matriz_rank, 5, axis=0)
            ).round(1),
        }
    ).sort_values("rank_base").reset_index(drop=True)

    log.info("Monte Carlo: %d simulaciones, spearman medio %.4f",
             n_simulaciones, spearmans.mean())
    return resumen, por_proyecto


def contribucion_dimensiones(df: pd.DataFrame, cfg: ConfigModelo) -> pd.DataFrame:
    """Cuanto aporta cada dimension a la varianza del score.

    Si una dimension no tiene varianza, su peso es decorativo. Esto detecta
    el problema que tenia 'atractivo inversor' en la formulacion original.
    """
    puntajes, _ = calcular_dimensiones(df, cfg)
    base = cfg.esquema_base
    filas = []
    for dim in DIMENSIONES:
        serie = puntajes[dim]
        aporte = serie * base[dim]
        filas.append(
            {
                "dimension": dim,
                "peso": base[dim],
                "puntaje_medio": float(serie.mean()),
                "puntaje_desv": float(serie.std(ddof=0)),
                "coef_variacion": float(serie.std(ddof=0) / serie.mean()) if serie.mean() else np.nan,
                "desv_aportada": float(aporte.std(ddof=0)),
                "corr_con_score": float(
                    np.corrcoef(serie, aplicar_esquema(puntajes, base))[0, 1]
                ),
            }
        )
    tabla = pd.DataFrame(filas)
    tabla["pct_desv_aportada"] = (
        tabla["desv_aportada"] / tabla["desv_aportada"].sum()
    ).round(4)
    return tabla.sort_values("pct_desv_aportada", ascending=False).reset_index(drop=True)
