# -*- coding: utf-8 -*-
"""Normalizacion de variables a escala comparable [0, 1].

Decision abierta 2 del proyecto, resuelta de forma parametrizada para poder
comparar metodos en lugar de imponer uno.

Justificacion empirica del winsorizado por defecto: en el diagnostico de
SECOP del 2026-09-11 se hallaron 13 contratos por encima de un billon de
pesos, con maximo de 2.582 billones frente a una mediana de 24,6 millones.
Con esa cola, min-max crudo comprime el 99,9% de los registros contra cero.
"""
from __future__ import annotations

import logging
from typing import Dict, Tuple

import numpy as np
import pandas as pd

log = logging.getLogger(__name__)

# Variables monetarias o de conteo con cola larga: se les aplica log1p
# antes de escalar cuando la configuracion lo pide.
VARIABLES_MONETARIAS = {
    "inversion_relativa",
    "escala_proyecto",
    "valor_vigente_total",
    "valor_obligado_total",
    "valor_pagado_total",
}


def winsorizar(s: pd.Series, p_inf: float, p_sup: float) -> pd.Series:
    """Acota la serie a sus percentiles, de forma conservadora.

    Se usa interpolacion 'lower' para el limite superior y 'higher' para el
    inferior. Con la interpolacion lineal por defecto de pandas, un unico
    valor extremo sobrevive al recorte: en una serie de 100 datos, el
    percentil 99 lineal cae entre el penultimo y el atipico, de modo que el
    limite queda contaminado por el propio atipico que se pretende acotar.
    Verificado con el caso real de SECOP (contrato de 2.582 billones frente
    a una mediana de 24,6 millones).
    """
    if s.notna().sum() == 0:
        return s
    lo = s.quantile(p_inf, interpolation="higher")
    hi = s.quantile(p_sup, interpolation="lower")
    if not np.isfinite(lo) or not np.isfinite(hi) or lo > hi:
        return s
    return s.clip(lower=lo, upper=hi)


def _constante(s: pd.Series) -> pd.Series:
    """Variable sin varianza: 0.5 a todos, respetando los faltantes."""
    return pd.Series(np.where(s.notna(), 0.5, np.nan), index=s.index)


def _minmax(s: pd.Series) -> pd.Series:
    lo, hi = s.min(), s.max()
    if not np.isfinite(lo) or not np.isfinite(hi) or hi == lo:
        return _constante(s)
    return (s - lo) / (hi - lo)


def _zscore(s: pd.Series) -> pd.Series:
    mu, sd = s.mean(), s.std(ddof=0)
    if sd == 0 or not np.isfinite(sd):
        return _constante(s)
    z = (s - mu) / sd
    # se reescala a [0,1] con un recorte a +-3 sigma para poder ponderar
    return ((z.clip(-3, 3) + 3) / 6)


def _robusta(s: pd.Series) -> pd.Series:
    med = s.median()
    mad = (s - med).abs().median()
    if mad == 0 or not np.isfinite(mad):
        return _minmax(s)
    z = (s - med) / (1.4826 * mad)
    return ((z.clip(-3, 3) + 3) / 6)


def _rango_percentil(s: pd.Series) -> pd.Series:
    return s.rank(pct=True, method="average")


METODOS = {
    "minmax": _minmax,
    "zscore": _zscore,
    "robusta": _robusta,
    "rango_percentil": _rango_percentil,
}


def normalizar_variable(
    s: pd.Series,
    sentido: int,
    metodo: str,
    winsor: bool,
    p_inf: float,
    p_sup: float,
    log_montos: bool,
    nombre: str = "",
    imputacion: str = "mediana",
) -> pd.Series:
    """Devuelve la variable en [0, 1] donde 1 siempre es mejor.

    imputacion: 'mediana' o 'cero' rellenan los faltantes; 'ninguna' los
    conserva como NaN para que la dimension se repondere con las variables
    disponibles (tratamiento por defecto del modelo).
    """
    x = pd.to_numeric(s, errors="coerce").replace([np.inf, -np.inf], np.nan)

    if imputacion == "mediana":
        x = x.fillna(x.median())
    elif imputacion == "cero":
        x = x.fillna(0.0)

    if log_montos and nombre in VARIABLES_MONETARIAS:
        x = np.log1p(x.clip(lower=0))

    if winsor:
        x = winsorizar(x, p_inf, p_sup)

    y = METODOS[metodo](x)

    if sentido == -1:
        y = 1.0 - y
    return y.clip(0.0, 1.0)


def normalizar_bloque(
    df: pd.DataFrame,
    especificaciones: Dict[str, Dict[str, float]],
    config_norm: Dict[str, object],
) -> Tuple[pd.DataFrame, Dict[str, Dict[str, float]]]:
    """Normaliza un conjunto de variables y devuelve tambien su diagnostico."""
    metodo = str(config_norm["metodo"])
    winsor = bool(config_norm["winsorizar"])
    p_inf = float(config_norm["percentil_inferior"])
    p_sup = float(config_norm["percentil_superior"])
    log_montos = bool(config_norm["log_montos"])
    imputacion = str(config_norm.get("imputacion_faltantes", "mediana"))
    if imputacion == "reponderar":
        imputacion = "ninguna"

    salida = pd.DataFrame(index=df.index)
    diagnostico: Dict[str, Dict[str, float]] = {}

    for nombre, spec in especificaciones.items():
        if nombre not in df.columns:
            log.warning("Variable '%s' ausente del dataset, se omite", nombre)
            continue
        cruda = pd.to_numeric(df[nombre], errors="coerce")
        norm = normalizar_variable(
            cruda, int(spec["sentido"]), metodo, winsor, p_inf, p_sup,
            log_montos, nombre, imputacion,
        )
        salida[nombre] = norm
        diagnostico[nombre] = {
            "faltantes": float(cruda.isna().mean()),
            "cruda_min": float(cruda.min(skipna=True)) if cruda.notna().any() else float("nan"),
            "cruda_mediana": float(cruda.median(skipna=True)) if cruda.notna().any() else float("nan"),
            "cruda_max": float(cruda.max(skipna=True)) if cruda.notna().any() else float("nan"),
            "norm_media": float(norm.mean()),
            "norm_desv": float(norm.std(ddof=0)),
            "sentido": int(spec["sentido"]),
        }
    return salida, diagnostico



def regla_faltantes(
    df: pd.DataFrame,
    variables: list[str],
    max_por_variable: float,
    max_por_proyecto: float,
) -> Tuple[list[str], pd.Series, pd.Series]:
    """Regla de exclusion por faltantes de la especificacion de direccion.

    Devuelve (variables descartadas, proporcion de faltantes por proyecto,
    mascara de proyectos con informacion insuficiente). La proporcion por
    proyecto se calcula sobre las variables que sobreviven, porque una
    variable descartada ya no es exigible a ningun proyecto.
    """
    presentes = [v for v in variables if v in df.columns]
    datos = df[presentes].apply(pd.to_numeric, errors="coerce")
    datos = datos.replace([np.inf, -np.inf], np.nan)
    por_variable = datos.isna().mean()
    descartadas = sorted(por_variable[por_variable > max_por_variable].index)
    vigentes = [v for v in presentes if v not in descartadas]
    if vigentes:
        por_proyecto = datos[vigentes].isna().mean(axis=1)
    else:
        por_proyecto = pd.Series(1.0, index=df.index)
    insuficiente = por_proyecto > max_por_proyecto
    if descartadas:
        log.warning("Variables descartadas por faltantes: %s", descartadas)
    return descartadas, por_proyecto, insuficiente
