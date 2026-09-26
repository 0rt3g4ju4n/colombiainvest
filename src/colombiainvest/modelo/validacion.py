# -*- coding: utf-8 -*-
"""Validez convergente del indice frente a una fuente independiente.

La especificacion de direccion pide correlacionar la calificacion con
indicadores independientes (desempeno fiscal, gobierno abierto, avance de
ejecucion). Con dos municipios, los indicadores municipales toman solo dos
valores y la correlacion con cientos de proyectos solo mediria si Chia y
Cajica difieren. Se adapta asi:

- Fuente independiente: el Informe de Gestion 2024 de Cajica, que reporta
  por sector el avance fisico y la ejecucion presupuestal de la vigencia.
  Lo produce el municipio, no el DNP, de modo que no comparte origen con el
  SUIFP que alimenta el score.
- Unidad: el sector. Se compara el puntaje medio de los proyectos vigentes
  de Cajica en cada sector con lo que el informe reporta para ese sector.
- Criterio de direccion: correlacion en el sentido esperado (positivo) y
  estadisticamente significativa.

Limitaciones que se declaran: un solo municipio, pocos sectores, y el
informe mide la vigencia 2024 mientras el SUIFP acumula todo el horizonte.
"""
from __future__ import annotations

from typing import Dict, Optional, Tuple

import pandas as pd
from scipy import stats

from ..ingesta.documentos import PUENTE_SECTOR, norm

# (columna del score, columna del informe) con relacion esperada positiva.
PARES_POR_DEFECTO: Tuple[Tuple[str, str, str], ...] = (
    ("score", "avance_fisico_sector", "Score total frente a avance fisico del sector"),
    ("score", "ejecucion_presupuestal_sector", "Score total frente a ejecucion presupuestal"),
    ("puntaje_viabilidad_financiera", "ejecucion_presupuestal_sector",
     "Viabilidad financiera frente a ejecucion presupuestal"),
    ("puntaje_madurez_ejecucion", "avance_fisico_sector",
     "Madurez de ejecucion frente a avance fisico"),
)


def tabla_por_sector(calificados: pd.DataFrame, sectores_informe: pd.DataFrame,
                     municipio: str = "Cajicá", grupo: Optional[str] = "Vigente",
                     columnas: Optional[Dict[str, str]] = None) -> pd.DataFrame:
    """Puntaje medio por sector junto a las cifras del informe del mismo sector.

    columnas permite renombrar las columnas de puntaje (el tablero usa
    'p_dimension' en lugar de 'puntaje_dimension').
    """
    datos = calificados.rename(columns=columnas or {})
    datos = datos[datos["municipio"] == municipio].dropna(subset=["score"])
    if grupo and "grupo_universo" in datos.columns:
        datos = datos[datos["grupo_universo"] == grupo]
    datos = datos.assign(sector_norm=datos["sector"].map(norm).map(lambda s: PUENTE_SECTOR.get(s, s)))
    cols = [c for c, _, _ in PARES_POR_DEFECTO if c in datos.columns]
    medias = (datos.groupby("sector_norm")
              .agg(proyectos=("bpin", "size"), **{c: (c, "mean") for c in dict.fromkeys(cols)})
              .reset_index())
    informe = sectores_informe.assign(sector_norm=sectores_informe["sector_informe"].map(norm))
    return medias.merge(
        informe[["sector_norm", "avance_fisico_sector", "ejecucion_presupuestal_sector"]],
        on="sector_norm", how="inner",
    )


def validez_convergente(calificados: pd.DataFrame, sectores_informe: pd.DataFrame,
                        municipio: str = "Cajicá", grupo: Optional[str] = "Vigente",
                        columnas: Optional[Dict[str, str]] = None,
                        alfa: float = 0.05) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """Correlaciones de Spearman entre el indice y el informe municipal.

    Devuelve (tabla de pruebas, tabla por sector).
    """
    por_sector = tabla_por_sector(calificados, sectores_informe, municipio, grupo, columnas)
    filas = []
    for col_score, col_informe, etiqueta in PARES_POR_DEFECTO:
        if col_score not in por_sector.columns:
            continue
        par = por_sector[[col_score, col_informe]].dropna()
        n = len(par)
        # Con una serie constante la correlacion no esta definida.
        if n >= 3 and par[col_score].nunique() > 1 and par[col_informe].nunique() > 1:
            prueba = stats.spearmanr(par[col_score], par[col_informe])
            rho, p = float(prueba.statistic), float(prueba.pvalue)
        else:
            rho = p = float("nan")
        filas.append({"contraste": etiqueta, "sectores": n, "spearman": round(rho, 3),
                      "p_valor": round(p, 4), "sentido_esperado": "positivo",
                      "cumple": bool(rho > 0 and p < alfa)})
    return pd.DataFrame(filas), por_sector
