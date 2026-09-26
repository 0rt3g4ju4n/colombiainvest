# -*- coding: utf-8 -*-
"""Modelo de calificacion compuesta.

Dentro de cada dimension:
    P_d = suma de peso_variable * variable normalizada en [0, 1], orientada de
    modo que mas siempre sea mejor, sobre las variables DISPONIBLES del
    proyecto (si falta una, sus pesos se renormalizan; no se inventa el dato).

Entre dimensiones, segun config/pesos.yaml (bloque 'agregacion'):
    geometrica:  S = prod_d (P'_d) ** w_d, con P'_d = piso + (100 - piso) * P_d / 100,
                 devuelto a [0, 100]. Limita la compensacion entre dimensiones.
    aritmetica:  S = suma_d w_d * P_d. Se conserva como variante de robustez.

Los pesos NO se aprenden de los datos. Provienen de juicio experto (y del
panel AHP cuando exista) y viven en config/. Estas funciones los reciben
como parametro, nunca los incrustan.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from ..config import DIMENSIONES, ConfigModelo
from ..procesamiento.normalizacion import normalizar_bloque, regla_faltantes

log = logging.getLogger(__name__)

ESCALA = 100.0


# ---------------------------------------------------------------------------
# faltantes
# ---------------------------------------------------------------------------
def variables_del_modelo(cfg: ConfigModelo) -> List[str]:
    return [v for d in DIMENSIONES for v in cfg.variables_activas(d)]


def evaluar_faltantes(df: pd.DataFrame, cfg: ConfigModelo) -> Dict[str, Any]:
    """Aplica la regla 30 % por variable y 40 % por proyecto."""
    reglas = cfg.faltantes
    descartadas, pct, insuf = regla_faltantes(
        df, variables_del_modelo(cfg),
        reglas["max_por_variable"], reglas["max_por_proyecto"],
    )
    return {"descartadas": descartadas, "pct_faltantes": pct, "insuficiente": insuf}


# ---------------------------------------------------------------------------
# dimensiones
# ---------------------------------------------------------------------------
def calcular_dimensiones(
    df: pd.DataFrame, cfg: ConfigModelo
) -> Tuple[pd.DataFrame, Dict[str, Dict[str, float]]]:
    """Calcula el puntaje 0 a 100 de cada dimension.

    Devuelve las cinco dimensiones y, con el prefijo 'dimension__', cada
    variable normalizada en [0, 1] (NaN si el proyecto no la tiene).
    """
    descartadas = set(evaluar_faltantes(df, cfg)["descartadas"])
    puntajes = pd.DataFrame(index=df.index)
    diagnostico_total: Dict[str, Dict[str, float]] = {}
    normalizadas = []

    for dim in DIMENSIONES:
        specs = {k: v for k, v in cfg.variables_activas(dim).items() if k not in descartadas}
        bloque, diag = normalizar_bloque(df, specs, cfg.normalizacion)
        diagnostico_total.update({f"{dim}.{k}": v for k, v in diag.items()})

        presentes = [c for c in specs if c in bloque.columns]
        if not presentes:
            raise ValueError(f"Ninguna variable de '{dim}' esta en el dataset")

        pesos = pd.Series({c: float(specs[c]["peso"]) for c in presentes})
        if pesos.sum() <= 0:
            raise ValueError(f"Pesos nulos en la dimension '{dim}'")
        valores = bloque[presentes]
        # Peso efectivo por proyecto: solo cuentan las variables que tiene.
        peso_disponible = valores.notna().mul(pesos, axis=1).sum(axis=1)
        suma = valores.fillna(0.0).mul(pesos, axis=1).sum(axis=1)
        puntajes[dim] = (suma / peso_disponible).where(peso_disponible > 0) * ESCALA
        normalizadas.append(bloque[presentes].add_prefix(f"{dim}__"))

    puntajes = pd.concat([puntajes] + normalizadas, axis=1)
    return puntajes, diagnostico_total


def aportes_por_variable(puntajes: pd.DataFrame, cfg: ConfigModelo) -> pd.DataFrame:
    """Puntos que aporta cada variable al puntaje de su dimension.

    Dentro de la dimension la agregacion es aritmetica, de modo que los
    aportes suman exactamente el puntaje de la dimension. Es el desglose por
    variable que pide la direccion para que el usuario audite el resultado.
    """
    salida = pd.DataFrame(index=puntajes.index)
    for dim in DIMENSIONES:
        cols = [c for c in puntajes.columns if c.startswith(f"{dim}__")]
        if not cols:
            continue
        pesos = pd.Series({c: float(cfg.variables(dim)[c.split("__", 1)[1]]["peso"]) for c in cols})
        valores = puntajes[cols]
        peso_disp = valores.notna().mul(pesos, axis=1).sum(axis=1)
        aporte = valores.mul(pesos, axis=1).div(peso_disp, axis=0) * ESCALA
        salida = pd.concat([salida, aporte], axis=1)
    return salida


# ---------------------------------------------------------------------------
# agregacion entre dimensiones
# ---------------------------------------------------------------------------
def agregar_dimensiones(
    matriz: np.ndarray, pesos: np.ndarray, metodo: str, piso: float
) -> np.ndarray:
    """Agrega puntajes de dimension (n x D) con uno o varios vectores de pesos.

    pesos puede ser (D,) o (k, D); en el segundo caso devuelve (k, n), que es
    lo que usa el Monte Carlo para evaluar miles de esquemas de una vez. Si a
    un proyecto le falta una dimension completa, se reponderan las demas.
    """
    m = np.asarray(matriz, dtype=float)
    w = np.atleast_2d(np.asarray(pesos, dtype=float))
    disponible = ~np.isnan(m)
    base = np.nan_to_num(m)
    if metodo == "geometrica":
        t = np.log(piso + (ESCALA - piso) * base / ESCALA)
    elif metodo == "aritmetica":
        t = base
    else:
        raise ValueError(f"Metodo de agregacion '{metodo}' invalido")
    t = np.where(disponible, t, 0.0)
    num = w @ t.T
    den = w @ disponible.T.astype(float)
    with np.errstate(invalid="ignore", divide="ignore"):
        media = np.where(den > 0, num / den, np.nan)
    if metodo == "geometrica":
        media = (np.exp(media) - piso) / (ESCALA - piso) * ESCALA
    return media[0] if np.ndim(pesos) == 1 else media


def aplicar_esquema(
    puntajes_dim: pd.DataFrame, esquema: Dict[str, float], agregacion: Dict[str, Any]
) -> pd.Series:
    """Combina los puntajes de dimension con un esquema de ponderacion.

    agregacion es el dict de cfg.agregacion ({'metodo', 'piso'}). Se exige
    de forma explicita para que ningun llamado use un metodo por omision
    distinto al configurado.
    """
    faltan = set(DIMENSIONES) - set(esquema)
    if faltan:
        raise ValueError(f"El esquema no cubre {faltan}")
    suma = sum(esquema[d] for d in DIMENSIONES)
    if abs(suma - 1.0) > 1e-6:
        raise ValueError(f"El esquema suma {suma:.6f}, debe sumar 1.0")
    pesos = np.array([esquema[d] for d in DIMENSIONES])
    valores = agregar_dimensiones(
        puntajes_dim[DIMENSIONES].to_numpy(), pesos,
        agregacion["metodo"], float(agregacion["piso"]),
    )
    return pd.Series(valores, index=puntajes_dim.index)


def percentil_en_grupo(score: pd.Series, grupo: pd.Series) -> pd.Series:
    """Posicion del proyecto dentro de su grupo (sector), de 0 a 100.

    Es la alternativa a normalizar por estrato: el score sigue siendo
    comparable entre sectores y la posicion frente a los pares del sector se
    reporta aparte. Con grupos de un solo proyecto el percentil es 100.
    """
    return (score.groupby(grupo).rank(pct=True, method="max") * 100).round(0)


# ---------------------------------------------------------------------------
# punto de entrada
# ---------------------------------------------------------------------------
def calificar(
    df: pd.DataFrame,
    cfg: ConfigModelo,
    esquema: Optional[Dict[str, float]] = None,
    nombre_esquema: str = "esquema_base",
    agregacion: Optional[Dict[str, Any]] = None,
) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    """Devuelve el dataset calificado y el diagnostico.

    Los proyectos que superan el umbral de faltantes no reciben score: quedan
    al final con la etiqueta de informacion insuficiente, en lugar de una
    calificacion baja que se confundiria con bajo desempeno.
    """
    esquema = esquema or cfg.esquema(nombre_esquema)
    agregacion = agregacion or cfg.agregacion
    falt = evaluar_faltantes(df, cfg)
    ok = ~falt["insuficiente"]

    calificables = df[ok]
    puntajes, diag = calcular_dimensiones(calificables, cfg)

    res = calificables.copy()
    for dim in DIMENSIONES:
        res[f"puntaje_{dim}"] = puntajes[dim].round(2)
    res["score"] = aplicar_esquema(puntajes, esquema, agregacion).round(2)
    res["ranking"] = res["score"].rank(ascending=False, method="min").astype("Int64")
    if "sector" in res.columns:
        res["percentil_sector"] = percentil_en_grupo(res["score"], res["sector"])
    res["estado_calificacion"] = "Calificado"

    for c in [c for c in puntajes.columns if "__" in c]:
        res[f"n_{c}"] = puntajes[c].round(4)
    for c, serie in aportes_por_variable(puntajes, cfg).items():
        res[f"aporte_{c}"] = serie.round(2)

    insuf = df[~ok].copy()
    if len(insuf):
        insuf["score"] = np.nan
        insuf["ranking"] = pd.array([pd.NA] * len(insuf), dtype="Int64")
        insuf["estado_calificacion"] = cfg.faltantes["etiqueta_insuficiente"]
    res = pd.concat([res, insuf]) if len(insuf) else res
    res["pct_faltantes_modelo"] = falt["pct_faltantes"].reindex(res.index).round(4)
    res["esquema_aplicado"] = nombre_esquema
    res["agregacion"] = agregacion["metodo"]

    res = res.sort_values("score", ascending=False, na_position="last").reset_index(drop=True)
    diag["_faltantes"] = {
        "variables_descartadas": falt["descartadas"],
        "proyectos_insuficientes": int((~ok).sum()),
        "proyectos_con_algun_faltante": int((falt["pct_faltantes"] > 0).sum()),
    }
    log.info("Calificados %d proyectos (%d con informacion insuficiente), esquema '%s', "
             "agregacion %s. Score medio %.1f, rango %.1f a %.1f",
             int(ok.sum()), int((~ok).sum()), nombre_esquema, agregacion["metodo"],
             res["score"].mean(), res["score"].min(), res["score"].max())
    return res, diag


def calificar_por_perfil(
    df: pd.DataFrame, cfg: ConfigModelo, perfil: str
) -> pd.DataFrame:
    """Ranking personalizado por perfil de inversionista (decision 5).

    Diseñado y funcional, pero gobernado por el interruptor
    perfiles_inversionista.habilitado del archivo de configuracion.
    """
    if not cfg.perfiles_habilitados:
        raise RuntimeError(
            "Los perfiles de inversionista no estan habilitados. "
            "Active perfiles_inversionista.habilitado en config/pesos.yaml "
            "cuando el grupo apruebe la decision 5."
        )
    esquema = cfg.esquema_de_perfil(perfil)
    res, _ = calificar(df, cfg, esquema=esquema, nombre_esquema=f"perfil:{perfil}")
    return res
