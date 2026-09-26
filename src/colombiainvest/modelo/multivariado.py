# -*- coding: utf-8 -*-
"""Analisis multivariado exploratorio de las variables del indice.

Etapa del manual OCDE-JRC exigida por la direccion: verificar que las
dimensiones propuestas tengan sustento empirico y no solo conceptual, y
detectar redundancia entre variables.

Tres diagnosticos, todos sobre las variables ya normalizadas y orientadas:
1. Matriz de correlaciones y pares redundantes.
2. Componentes principales (sobre variables estandarizadas): varianza
   explicada, criterio de Kaiser y a que componente carga cada variable.
3. Alfa de Cronbach por dimension (consistencia interna).

Es un diagnostico, no un paso que cambie el score. Si revela un problema,
la decision de corregirlo pasa por el grupo y queda documentada.
"""
from __future__ import annotations

from typing import Dict

import numpy as np
import pandas as pd

from ..config import DIMENSIONES, ConfigModelo
from .score import calcular_dimensiones


def matriz_variables(df: pd.DataFrame, cfg: ConfigModelo) -> pd.DataFrame:
    """Variables normalizadas en [0, 1] con columnas 'dimension__variable'."""
    puntajes, _ = calcular_dimensiones(df, cfg)
    return puntajes[[c for c in puntajes.columns if "__" in c]]


def pares_redundantes(x: pd.DataFrame, umbral: float = 0.8) -> pd.DataFrame:
    """Pares de variables con correlacion de Spearman absoluta >= umbral."""
    corr = x.corr(method="spearman")
    filas = []
    cols = list(corr.columns)
    for i, a in enumerate(cols):
        for b in cols[i + 1:]:
            r = corr.loc[a, b]
            if np.isfinite(r) and abs(r) >= umbral:
                filas.append({"variable_a": a, "variable_b": b, "spearman": round(float(r), 3),
                              "misma_dimension": a.split("__")[0] == b.split("__")[0]})
    return pd.DataFrame(filas, columns=["variable_a", "variable_b", "spearman", "misma_dimension"])


def componentes_principales(x: pd.DataFrame) -> Dict[str, pd.DataFrame]:
    """PCA por descomposicion en valores singulares, sin dependencias extra.

    Los faltantes se imputan con la mediana SOLO para este diagnostico, que
    necesita una matriz completa; el score no usa esa imputacion.
    """
    z = x.fillna(x.median())
    desv = z.std(ddof=0).replace(0, np.nan)
    z = ((z - z.mean()) / desv).dropna(axis=1)
    _, s, vt = np.linalg.svd(z.to_numpy(), full_matrices=False)
    autovalores = s ** 2 / len(z)
    var = autovalores / autovalores.sum()
    varianza = pd.DataFrame({
        "componente": [f"CP{i + 1}" for i in range(len(var))],
        "autovalor": autovalores.round(3),
        "varianza_explicada": var.round(4),
        "acumulada": np.cumsum(var).round(4),
    })
    k = max(int((autovalores > 1).sum()), 1)
    cargas = pd.DataFrame(vt[:k].T * np.sqrt(autovalores[:k]), index=z.columns,
                          columns=[f"CP{i + 1}" for i in range(k)]).round(3)
    cargas.insert(0, "dimension", [c.split("__")[0] for c in cargas.index])
    cargas["componente_dominante"] = cargas[[f"CP{i + 1}" for i in range(k)]].abs().idxmax(axis=1)
    return {"varianza": varianza, "cargas": cargas, "n_kaiser": pd.DataFrame({"n": [k]})}


def alfa_cronbach(x: pd.DataFrame) -> pd.DataFrame:
    """Alfa de Cronbach de cada dimension sobre sus variables normalizadas.

    Referencia usual: 0,7 o mas indica consistencia interna. Un alfa bajo no
    invalida la dimension (un indice formativo puede reunir aspectos
    distintos de un mismo concepto), pero obliga a justificarla.
    """
    filas = []
    for dim in DIMENSIONES:
        cols = [c for c in x.columns if c.startswith(f"{dim}__")]
        k = len(cols)
        if k < 2:
            filas.append({"dimension": dim, "n_variables": k, "alfa_cronbach": np.nan})
            continue
        bloque = x[cols].dropna()
        var_items = bloque.var(ddof=1).sum()
        var_total = bloque.sum(axis=1).var(ddof=1)
        alfa = k / (k - 1) * (1 - var_items / var_total) if var_total > 0 else np.nan
        filas.append({"dimension": dim, "n_variables": k, "alfa_cronbach": round(float(alfa), 3)})
    return pd.DataFrame(filas)


def analisis_multivariado(df: pd.DataFrame, cfg: ConfigModelo) -> Dict[str, pd.DataFrame]:
    x = matriz_variables(df, cfg)
    pca = componentes_principales(x)
    return {
        "correlaciones": x.corr(method="spearman").round(3),
        "redundantes": pares_redundantes(x),
        "pca_varianza": pca["varianza"],
        "pca_cargas": pca["cargas"],
        "cronbach": alfa_cronbach(x),
    }
