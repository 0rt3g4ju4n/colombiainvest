# -*- coding: utf-8 -*-
"""Analisis de incertidumbre, sensibilidad y robustez de la calificacion.

Responde la pregunta previsible del jurado: si los pesos son juicio experto,
que tan dependiente del juicio es el resultado. Sigue la especificacion de
la direccion (v3 ajustada, seccion de construccion del indice):

1. Robustez frente a esquemas alternativos de ponderacion: los declarados en
   config/pesos.yaml, pesos iguales y ponderacion por entropia. Criterio de
   aceptacion: Spearman mayor que el umbral configurado (0,85).
2. Robustez frente a decisiones metodologicas: agregacion aritmetica en vez
   de geometrica, winsorizacion en p1 y p99, imputacion por mediana.
3. Incertidumbre sobre los pesos por Monte Carlo con distribucion de
   Dirichlet centrada en el esquema de referencia, con el intervalo de
   posiciones de cada proyecto.
4. Indices de sensibilidad de primer orden: que dimension gobierna el
   cambio del ranking.
"""
from __future__ import annotations

import copy
import logging
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
from scipy import stats

from ..config import DIMENSIONES, ConfigModelo
from .score import agregar_dimensiones, aplicar_esquema, calcular_dimensiones, calificar

log = logging.getLogger(__name__)


def _rankear(serie: pd.Series) -> pd.Series:
    return serie.rank(ascending=False, method="min")


def _estabilidad_topk(r0: pd.Series, r1: pd.Series, k: int) -> float:
    """Proporcion del top-k del esquema de referencia que sigue en el top-k."""
    a = set(r0.nsmallest(k).index)
    b = set(r1.nsmallest(k).index)
    return len(a & b) / k if k else float("nan")


def _metricas_rankings(r0: pd.Series, r1: pd.Series, umbral: float) -> Dict[str, float]:
    desplazamiento = (r1 - r0).abs()
    rho = float(stats.spearmanr(r0, r1).statistic)
    return {
        "spearman": rho,
        "kendall_tau": float(stats.kendalltau(r0, r1).statistic),
        "cumple_umbral": bool(rho > umbral),
        "desplaz_medio": float(desplazamiento.mean()),
        "desplaz_mediano": float(desplazamiento.median()),
        "desplaz_max": int(desplazamiento.max()),
        "pct_mueve_mas_10": float((desplazamiento > 10).mean()),
        "top10_estable": _estabilidad_topk(r0, r1, 10),
        "top20_estable": _estabilidad_topk(r0, r1, 20),
    }


# ---------------------------------------------------------------------------
# esquemas de ponderacion
# ---------------------------------------------------------------------------
def pesos_entropia(puntajes_dim: pd.DataFrame) -> Dict[str, float]:
    """Ponderacion por entropia de Shannon.

    Asigna mas peso a la dimension que mas discrimina entre proyectos. Es un
    esquema derivado de los datos y no de juicio experto: se usa solo como
    contraste de robustez, nunca como esquema principal.
    """
    x = puntajes_dim[DIMENSIONES].dropna().to_numpy(dtype=float) + 1e-12
    n = len(x)
    if n < 2:
        return {d: 1 / len(DIMENSIONES) for d in DIMENSIONES}
    p = x / x.sum(axis=0)
    e = -(p * np.log(p)).sum(axis=0) / np.log(n)
    d = 1.0 - e
    w = d / d.sum() if d.sum() > 0 else np.full(len(DIMENSIONES), 1 / len(DIMENSIONES))
    return {dim: float(v) for dim, v in zip(DIMENSIONES, w)}


def comparar_esquemas(
    df: pd.DataFrame,
    cfg: ConfigModelo,
    esquemas: Optional[List[str]] = None,
    incluir_entropia: bool = True,
    subconjunto: Optional[pd.Series] = None,
) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """Recalcula el score bajo cada esquema y compara los rankings.

    Devuelve (tabla de metricas, tabla de rankings por proyecto). La
    referencia es el primer esquema de la lista (el base, por defecto).

    subconjunto (mascara booleana alineada con df): el score se calcula con
    todo df, pero el ranking y las metricas se miden solo dentro del
    subconjunto. Sirve para medir la estabilidad de lo que ve el usuario
    (los proyectos vigentes) sin cambiar la base de normalizacion.
    """
    esquemas = esquemas or cfg.esquemas_disponibles
    puntajes, _ = calcular_dimensiones(df, cfg)
    agr = cfg.agregacion
    umbral = cfg.montecarlo["umbral_spearman"]

    definiciones = {n: (cfg.esquema(n), cfg.descripcion_esquema(n)) for n in esquemas}
    if incluir_entropia:
        definiciones["entropia"] = (
            pesos_entropia(puntajes),
            "Derivado de los datos: pesa mas la dimension que mas discrimina.",
        )

    scores = pd.DataFrame(index=df.index)
    for nombre, (esq, _) in definiciones.items():
        scores[nombre] = aplicar_esquema(puntajes, esq, agr)
    base_df = df
    if subconjunto is not None:
        mascara = subconjunto.to_numpy(dtype=bool)
        scores, base_df = scores[mascara], df[mascara]

    rankings = scores.apply(_rankear)
    rankings.insert(0, "bpin", base_df["bpin"].values)
    rankings.insert(1, "nombreproyecto",
                    base_df.get("nombreproyecto", pd.Series(index=base_df.index)).values)

    referencia = esquemas[0]
    filas = []
    for nombre, (esq, desc) in definiciones.items():
        if nombre == referencia:
            continue
        filas.append({
            "esquema": nombre,
            "descripcion": desc,
            **{f"w_{d}": round(esq[d], 4) for d in DIMENSIONES},
            **_metricas_rankings(rankings[referencia], rankings[nombre], umbral),
        })
    metricas = pd.DataFrame(filas)
    log.info("Sensibilidad entre esquemas calculada sobre %d proyectos", len(df))
    return metricas, rankings


# ---------------------------------------------------------------------------
# decisiones metodologicas
# ---------------------------------------------------------------------------
def _variante(cfg: ConfigModelo, ruta: Tuple[str, ...], valor) -> ConfigModelo:
    bruto = copy.deepcopy(cfg.bruto)
    nodo = bruto
    for clave in ruta[:-1]:
        nodo = nodo.setdefault(clave, {})
    nodo[ruta[-1]] = valor
    return ConfigModelo(bruto)


def comparar_variantes(df: pd.DataFrame, cfg: ConfigModelo,
                       bpins: Optional[set] = None) -> pd.DataFrame:
    """Robustez del ranking frente a las decisiones metodologicas.

    Cada variante cambia una sola decision respecto de la configuracion
    vigente, con los mismos pesos, y mide cuanto se mueve el orden. Con
    bpins, el ranking se mide solo dentro de ese conjunto de proyectos.
    """
    umbral = cfg.montecarlo["umbral_spearman"]
    agr = cfg.agregacion["metodo"]
    otra_agr = "aritmetica" if agr == "geometrica" else "geometrica"
    norm = cfg.normalizacion
    variantes = [
        (f"agregacion {otra_agr}", ("agregacion", "metodo"), otra_agr),
        ("winsorizacion p1 y p99", ("normalizacion", "percentil_inferior"), 0.01),
        ("imputacion por mediana", ("normalizacion", "imputacion_faltantes"),
         "mediana" if norm.get("imputacion_faltantes") != "mediana" else "reponderar"),
        ("normalizacion por rango percentil", ("normalizacion", "metodo"), "rango_percentil"),
    ]

    base, _ = calificar(df, cfg)
    base = base.dropna(subset=["score"]).set_index("bpin")
    r0 = _rankear(base["score"])

    filas = []
    for nombre, ruta, valor in variantes:
        cfg_v = _variante(cfg, ruta, valor)
        if nombre.startswith("winsorizacion"):
            cfg_v = _variante(cfg_v, ("normalizacion", "percentil_superior"), 0.99)
        alt, _ = calificar(df, cfg_v)
        alt = alt.dropna(subset=["score"]).set_index("bpin")
        comunes = r0.index.intersection(alt.index)
        if bpins is not None:
            comunes = comunes[comunes.isin(list(bpins))]
        r1 = _rankear(alt.loc[comunes, "score"])
        filas.append({"variante": nombre,
                      **_metricas_rankings(_rankear(base.loc[comunes, "score"]), r1, umbral)})
    return pd.DataFrame(filas)


# ---------------------------------------------------------------------------
# Monte Carlo
# ---------------------------------------------------------------------------
def _indices_primer_orden(entradas: np.ndarray, y: np.ndarray, bins: int) -> np.ndarray:
    """Indice de primer orden S_i = Var(E[Y | X_i]) / Var(Y), desde la muestra.

    Estimador por particion en cuantiles de cada entrada (razon de
    correlacion). Reutiliza las mismas simulaciones, sin corridas extra.
    Requiere entradas independientes: por eso se estima sobre las variables
    gamma que generan la Dirichlet, y no sobre los pesos, que suman 1 y
    estan correlacionados por construccion.
    """
    var_y = y.var()
    if not np.isfinite(var_y) or var_y == 0:
        return np.full(entradas.shape[1], np.nan)
    salida = np.empty(entradas.shape[1])
    for i in range(entradas.shape[1]):
        cortes = np.quantile(entradas[:, i], np.linspace(0, 1, bins + 1))
        grupo = np.clip(np.searchsorted(cortes, entradas[:, i], side="right") - 1, 0, bins - 1)
        conteo = np.bincount(grupo, minlength=bins)
        suma = np.bincount(grupo, weights=y, minlength=bins)
        usados = conteo > 0
        medias = suma[usados] / conteo[usados]
        salida[i] = np.sum(conteo[usados] * (medias - y.mean()) ** 2) / len(y) / var_y
    return salida


def perturbacion_montecarlo(
    df: pd.DataFrame,
    cfg: ConfigModelo,
    n_simulaciones: Optional[int] = None,
    ruido: float = 0.15,
    esquema_base: Optional[Dict[str, float]] = None,
    semilla: Optional[int] = None,
    distribucion: Optional[str] = None,
    concentracion: Optional[float] = None,
) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Perturba los pesos y mide la estabilidad del ranking.

    distribucion 'dirichlet' (por defecto, especificacion de direccion):
        w ~ Dirichlet(concentracion * w_base). Siempre suma 1 y es positiva.
    distribucion 'normal' (variante previa): cada peso se multiplica por un
        factor N(1, ruido) y se renormaliza.

    Devuelve (resumen, estabilidad por proyecto, indices de primer orden).
    """
    mc = cfg.montecarlo
    n = int(n_simulaciones or mc["iteraciones"])
    distribucion = distribucion or mc["distribucion"]
    concentracion = float(concentracion or mc["concentracion"])
    rng = np.random.default_rng(semilla if semilla is not None else cfg.semilla)
    base = esquema_base or cfg.esquema_base
    agr = cfg.agregacion

    puntajes, _ = calcular_dimensiones(df, cfg)
    matriz = puntajes[DIMENSIONES].to_numpy()
    w0 = np.array([base[d] for d in DIMENSIONES], dtype=float)

    score_base = agregar_dimensiones(matriz, w0, agr["metodo"], agr["piso"])
    rank_base = stats.rankdata(-score_base, method="min")
    rank_base_prom = stats.rankdata(-score_base, method="average")

    if distribucion == "dirichlet":
        entradas = rng.gamma(np.clip(concentracion * w0, 1e-3, None), 1.0, size=(n, len(w0)))
        pesos = entradas / entradas.sum(axis=1, keepdims=True)
        etiqueta_param = f"concentracion {concentracion:g}"
    elif distribucion == "normal":
        entradas = rng.normal(1.0, ruido, size=(n, len(w0)))
        p = np.clip(w0 * entradas, 1e-6, None)
        pesos = p / p.sum(axis=1, keepdims=True)
        etiqueta_param = f"ruido relativo {ruido:g}"
    else:
        raise ValueError(f"Distribucion '{distribucion}' invalida")

    rangos = np.empty((n, len(score_base)), dtype=np.int32)
    spearmans = np.empty(n)
    rb = rank_base_prom - rank_base_prom.mean()
    for ini in range(0, n, 2000):
        fin = min(ini + 2000, n)
        s = agregar_dimensiones(matriz, pesos[ini:fin], agr["metodo"], agr["piso"])
        rangos[ini:fin] = stats.rankdata(-s, method="min", axis=1)
        ra = stats.rankdata(-s, method="average", axis=1)
        ra = ra - ra.mean(axis=1, keepdims=True)
        denom = np.sqrt((ra ** 2).sum(axis=1) * (rb ** 2).sum())
        with np.errstate(invalid="ignore", divide="ignore"):
            spearmans[ini:fin] = np.where(denom > 0, (ra @ rb) / denom, 1.0)

    desplaz = np.abs(rangos - rank_base).mean(axis=1)
    umbral = mc["umbral_spearman"]
    resumen = pd.DataFrame({
        "distribucion": [distribucion],
        "parametro": [etiqueta_param],
        "n_simulaciones": [n],
        "agregacion": [agr["metodo"]],
        "spearman_medio": [float(spearmans.mean())],
        "spearman_p05": [float(np.percentile(spearmans, 5))],
        "spearman_min": [float(spearmans.min())],
        "pct_sobre_umbral": [float((spearmans > umbral).mean())],
        "desplaz_medio_abs": [float(desplaz.mean())],
    })

    p05 = np.percentile(rangos, 5, axis=0)
    p95 = np.percentile(rangos, 95, axis=0)
    por_proyecto = pd.DataFrame({
        "bpin": df["bpin"].values,
        "nombreproyecto": df.get("nombreproyecto", pd.Series(index=df.index)).values,
        "score_base": np.round(score_base, 2),
        "rank_base": rank_base.astype(int),
        "rank_medio": rangos.mean(axis=0).round(1),
        "rank_p05": p05.round(0),
        "rank_p95": p95.round(0),
        "amplitud_ic90": (p95 - p05).round(1),
    }).sort_values("rank_base").reset_index(drop=True)

    s1 = _indices_primer_orden(entradas, desplaz, mc["bins_sensibilidad"])
    primer_orden = pd.DataFrame({
        "dimension": DIMENSIONES,
        "peso_referencia": w0,
        "indice_primer_orden": np.round(s1, 4),
    }).sort_values("indice_primer_orden", ascending=False).reset_index(drop=True)

    log.info("Monte Carlo %s: %d simulaciones, spearman medio %.4f",
             distribucion, n, spearmans.mean())
    return resumen, por_proyecto, primer_orden


def contribucion_dimensiones(df: pd.DataFrame, cfg: ConfigModelo) -> pd.DataFrame:
    """Cuanto aporta cada dimension a la varianza del score.

    Si una dimension no tiene varianza, su peso es decorativo. Esto detecto
    el problema que tenia 'atractivo inversor' en la formulacion original.
    La desviacion aportada es la de la version aritmetica (peso por
    puntaje); la correlacion con el score usa la agregacion configurada.
    """
    puntajes, _ = calcular_dimensiones(df, cfg)
    base = cfg.esquema_base
    score = aplicar_esquema(puntajes, base, cfg.agregacion)
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
                "corr_con_score": float(np.corrcoef(serie, score)[0, 1]),
            }
        )
    tabla = pd.DataFrame(filas)
    tabla["pct_desv_aportada"] = (
        tabla["desv_aportada"] / tabla["desv_aportada"].sum()
    ).round(4)
    return tabla.sort_values("pct_desv_aportada", ascending=False).reset_index(drop=True)
