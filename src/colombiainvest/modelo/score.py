# -*- coding: utf-8 -*-
"""Modelo de calificacion compuesta.

Score = suma sobre dimensiones de peso_dimension * puntaje_dimension,
donde puntaje_dimension = suma sobre variables de peso_variable * variable
normalizada en [0, 1] y orientada de modo que mas siempre sea mejor.

Los pesos NO se aprenden de los datos. Provienen de juicio experto y viven
en config/pesos.yaml. Esta funcion los recibe como parametro, nunca los
incrusta.
"""
from __future__ import annotations

import logging
from typing import Dict, Optional, Tuple

import pandas as pd

from ..config import DIMENSIONES, ConfigModelo
from ..procesamiento.normalizacion import normalizar_bloque

log = logging.getLogger(__name__)

ESCALA = 100.0


def calcular_dimensiones(
    df: pd.DataFrame, cfg: ConfigModelo
) -> Tuple[pd.DataFrame, Dict[str, Dict[str, float]]]:
    """Calcula el puntaje 0 a 100 de cada dimension."""
    puntajes = pd.DataFrame(index=df.index)
    diagnostico_total: Dict[str, Dict[str, float]] = {}
    normalizadas = pd.DataFrame(index=df.index)

    for dim in DIMENSIONES:
        specs = cfg.variables_activas(dim)
        bloque, diag = normalizar_bloque(df, specs, cfg.normalizacion)
        diagnostico_total.update({f"{dim}.{k}": v for k, v in diag.items()})

        presentes = [c for c in specs if c in bloque.columns]
        if not presentes:
            raise ValueError(f"Ninguna variable de '{dim}' esta en el dataset")

        # renormaliza los pesos si alguna variable falto, para no sesgar
        pesos = {c: specs[c]["peso"] for c in presentes}
        suma = sum(pesos.values())
        if suma <= 0:
            raise ValueError(f"Pesos nulos en la dimension '{dim}'")
        if abs(suma - 1.0) > 1e-9:
            log.warning("Dimension '%s': pesos presentes suman %.4f, se renormaliza",
                        dim, suma)
            pesos = {c: p / suma for c, p in pesos.items()}

        puntajes[dim] = sum(bloque[c] * p for c, p in pesos.items()) * ESCALA
        normalizadas = pd.concat([normalizadas, bloque.add_prefix(f"{dim}__")], axis=1)

    puntajes = pd.concat([puntajes, normalizadas], axis=1)
    return puntajes, diagnostico_total


def aplicar_esquema(
    puntajes_dim: pd.DataFrame, esquema: Dict[str, float]
) -> pd.Series:
    """Combina los puntajes de dimension con un esquema de ponderacion."""
    faltan = set(DIMENSIONES) - set(esquema)
    if faltan:
        raise ValueError(f"El esquema no cubre {faltan}")
    suma = sum(esquema[d] for d in DIMENSIONES)
    if abs(suma - 1.0) > 1e-6:
        raise ValueError(f"El esquema suma {suma:.6f}, debe sumar 1.0")
    return sum(puntajes_dim[d] * esquema[d] for d in DIMENSIONES)


def calificar(
    df: pd.DataFrame,
    cfg: ConfigModelo,
    esquema: Optional[Dict[str, float]] = None,
    nombre_esquema: str = "esquema_base",
) -> Tuple[pd.DataFrame, Dict[str, Dict[str, float]]]:
    """Punto de entrada. Devuelve el dataset calificado y el diagnostico."""
    esquema = esquema or cfg.esquema(nombre_esquema)
    puntajes, diag = calcular_dimensiones(df, cfg)

    res = df.copy()
    for dim in DIMENSIONES:
        res[f"puntaje_{dim}"] = puntajes[dim].round(2)
    res["score"] = aplicar_esquema(puntajes, esquema).round(2)
    res["ranking"] = res["score"].rank(ascending=False, method="min").astype(int)
    res["esquema_aplicado"] = nombre_esquema

    cols_norm = [c for c in puntajes.columns if "__" in c]
    for c in cols_norm:
        res[f"n_{c}"] = puntajes[c].round(4)

    res = res.sort_values("score", ascending=False).reset_index(drop=True)
    log.info("Calificados %d proyectos con esquema '%s'. Score medio %.1f, rango %.1f a %.1f",
             len(res), nombre_esquema, res["score"].mean(), res["score"].min(), res["score"].max())
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
