# -*- coding: utf-8 -*-
"""Pruebas del modelo de calificacion.

Los datos sinteticos se usan aqui de forma deliberada y acotada: sirven para
verificar el comportamiento del codigo en casos borde, no sustituyen los
datos reales del caso de aplicacion.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "src"))

from colombiainvest.config import DIMENSIONES, ConfigModelo, cargar_modelo  # noqa: E402
from colombiainvest.modelo.score import aplicar_esquema, calcular_dimensiones, calificar  # noqa: E402
from colombiainvest.modelo.sensibilidad import comparar_esquemas, perturbacion_montecarlo  # noqa: E402
from colombiainvest.procesamiento.normalizacion import normalizar_variable, winsorizar  # noqa: E402
from colombiainvest.procesamiento.variables import _anios_horizonte, mapear, sin_tildes  # noqa: E402

SEMILLA = 42


@pytest.fixture(scope="module")
def cfg() -> ConfigModelo:
    return cargar_modelo()


@pytest.fixture(scope="module")
def datos_sinteticos(cfg: ConfigModelo) -> pd.DataFrame:
    """Dataset minimo con todas las variables que el modelo exige."""
    rng = np.random.default_rng(SEMILLA)
    n = 60
    filas = {"bpin": [f"B{i:04d}" for i in range(n)],
             "nombreproyecto": [f"Proyecto {i}" for i in range(n)]}
    for dim in DIMENSIONES:
        for var in cfg.variables_activas(dim):
            filas[var] = rng.uniform(0, 100, n)
    return pd.DataFrame(filas)


# ---------------------------------------------------------------------------
# configuracion
# ---------------------------------------------------------------------------
def test_esquemas_suman_uno(cfg: ConfigModelo) -> None:
    for nombre in cfg.esquemas_disponibles:
        assert abs(sum(cfg.esquema(nombre).values()) - 1.0) < 1e-9, nombre


def test_pesos_intra_dimension_suman_uno(cfg: ConfigModelo) -> None:
    for dim in DIMENSIONES:
        suma = sum(v["peso"] for v in cfg.variables(dim).values())
        assert abs(suma - 1.0) < 1e-9, dim


def test_config_invalida_falla_temprano() -> None:
    bruto = {
        "esquema_base": {d: 0.2 for d in DIMENSIONES},
        "esquemas_alternativos": {},
        "variables": {d: {"x": {"peso": 0.5, "sentido": 1}} for d in DIMENSIONES},
        "normalizacion": {"metodo": "minmax", "winsorizar": False,
                          "percentil_inferior": 0.0, "percentil_superior": 1.0,
                          "log_montos": False},
        "mapeos": {}, "poblacion": {}, "perfiles_inversionista": {"habilitado": False, "perfiles": {}},
    }
    with pytest.raises(ValueError, match="suman"):
        ConfigModelo(bruto)


def test_esquema_inexistente(cfg: ConfigModelo) -> None:
    with pytest.raises(KeyError):
        cfg.esquema("no_existe")


# ---------------------------------------------------------------------------
# normalizacion
# ---------------------------------------------------------------------------
def test_normalizacion_en_rango_unitario() -> None:
    s = pd.Series([1, 5, 10, 1_000_000_000])
    for metodo in ("minmax", "zscore", "robusta", "rango_percentil"):
        y = normalizar_variable(s, 1, metodo, False, 0.01, 0.99, False)
        assert y.min() >= 0.0 and y.max() <= 1.0, metodo


def test_sentido_invierte_el_orden() -> None:
    s = pd.Series([1.0, 2.0, 3.0, 4.0])
    sube = normalizar_variable(s, 1, "minmax", False, 0.01, 0.99, False)
    baja = normalizar_variable(s, -1, "minmax", False, 0.01, 0.99, False)
    assert sube.iloc[0] < sube.iloc[-1]
    assert baja.iloc[0] > baja.iloc[-1]
    assert np.allclose(sube + baja, 1.0)


def test_variable_constante_no_rompe() -> None:
    s = pd.Series([7.0] * 10)
    y = normalizar_variable(s, 1, "minmax", False, 0.01, 0.99, False)
    assert y.notna().all() and (y == 0.5).all()


def test_winsorizado_acota_el_valor_atipico() -> None:
    """Caso real: SECOP tiene contratos de 2.582 billones junto a medianas
    de 24,6 millones. Sin winsorizar, min-max aplasta todo contra cero."""
    s = pd.Series(list(np.linspace(1e6, 5e7, 99)) + [2.58e15])
    crudo = normalizar_variable(s, 1, "minmax", False, 0.01, 0.99, False)
    acotado = normalizar_variable(s, 1, "minmax", True, 0.01, 0.99, False)
    assert crudo.iloc[:99].max() < 0.01          # todo comprimido contra cero
    assert acotado.iloc[:99].max() > 0.9         # el rango se recupera


def test_winsorizar_respeta_percentiles() -> None:
    s = pd.Series(range(101))
    w = winsorizar(s, 0.05, 0.95)
    assert w.min() >= 5 and w.max() <= 95


def test_faltantes_se_imputan() -> None:
    s = pd.Series([1.0, np.nan, 3.0, np.inf])
    y = normalizar_variable(s, 1, "minmax", False, 0.01, 0.99, False, imputacion="mediana")
    assert y.notna().all()


# ---------------------------------------------------------------------------
# utilidades de variables
# ---------------------------------------------------------------------------
def test_sin_tildes() -> None:
    assert sin_tildes("Educación") == "Educacion"
    assert sin_tildes("Inactivo\xa0 (PGN, Territorio)") == "Inactivo (PGN, Territorio)"
    assert sin_tildes(None) == ""


def test_mapear_ignora_tildes_y_caja() -> None:
    tabla = {"Educacion": 1.0, "_defecto": 0.1}
    assert mapear("Educación", tabla) == 1.0
    assert mapear("EDUCACION", tabla) == 1.0
    assert mapear("Otra cosa", tabla) == 0.1


def test_anios_horizonte() -> None:
    assert _anios_horizonte("2020-2024") == 5.0
    assert _anios_horizonte("2024-2027") == 4.0
    assert _anios_horizonte("basura") == 0.0
    assert _anios_horizonte(None) == 0.0


# ---------------------------------------------------------------------------
# score
# ---------------------------------------------------------------------------
def test_score_en_rango(datos_sinteticos: pd.DataFrame, cfg: ConfigModelo) -> None:
    res, _ = calificar(datos_sinteticos, cfg)
    assert res["score"].between(0, 100).all()


def test_ranking_es_consistente_con_el_score(datos_sinteticos, cfg) -> None:
    res, _ = calificar(datos_sinteticos, cfg)
    assert res["score"].is_monotonic_decreasing
    assert res["ranking"].iloc[0] == 1


def test_pesos_no_estan_incrustados(datos_sinteticos, cfg) -> None:
    """Cambiar el esquema DEBE cambiar el resultado."""
    base, _ = calificar(datos_sinteticos, cfg, nombre_esquema="esquema_base")
    alt, _ = calificar(datos_sinteticos, cfg, nombre_esquema="enfasis_financiero")
    unido = base[["bpin", "score"]].merge(alt[["bpin", "score"]], on="bpin", suffixes=("_b", "_a"))
    assert not np.allclose(unido["score_b"], unido["score_a"])


def test_esquema_que_no_suma_uno_es_rechazado(datos_sinteticos, cfg) -> None:
    puntajes, _ = calcular_dimensiones(datos_sinteticos, cfg)
    malo = {d: 0.5 for d in DIMENSIONES}
    with pytest.raises(ValueError, match="suma"):
        aplicar_esquema(puntajes, malo)


def test_esquema_incompleto_es_rechazado(datos_sinteticos, cfg) -> None:
    puntajes, _ = calcular_dimensiones(datos_sinteticos, cfg)
    with pytest.raises(ValueError, match="no cubre"):
        aplicar_esquema(puntajes, {"gobernanza": 1.0})


def test_reproducibilidad(datos_sinteticos, cfg) -> None:
    a, _ = calificar(datos_sinteticos, cfg)
    b, _ = calificar(datos_sinteticos, cfg)
    pd.testing.assert_series_equal(a["score"], b["score"])


def test_perfiles_bloqueados_si_no_estan_habilitados(datos_sinteticos, cfg) -> None:
    from colombiainvest.modelo.score import calificar_por_perfil
    if not cfg.perfiles_habilitados:
        with pytest.raises(RuntimeError, match="no estan habilitados"):
            calificar_por_perfil(datos_sinteticos, cfg, "institucional")


# ---------------------------------------------------------------------------
# sensibilidad
# ---------------------------------------------------------------------------
def test_comparacion_de_esquemas(datos_sinteticos, cfg) -> None:
    metricas, rankings = comparar_esquemas(datos_sinteticos, cfg)
    assert len(metricas) == len(cfg.esquemas_disponibles) - 1
    assert metricas["spearman"].between(-1, 1).all()
    assert metricas["top10_estable"].between(0, 1).all()


def test_montecarlo_reproducible(datos_sinteticos, cfg) -> None:
    r1, p1 = perturbacion_montecarlo(datos_sinteticos, cfg, n_simulaciones=50, semilla=SEMILLA)
    r2, p2 = perturbacion_montecarlo(datos_sinteticos, cfg, n_simulaciones=50, semilla=SEMILLA)
    pd.testing.assert_frame_equal(r1, r2)
    pd.testing.assert_frame_equal(p1, p2)


def test_ruido_cero_no_altera_el_ranking(datos_sinteticos, cfg) -> None:
    _, por_proyecto = perturbacion_montecarlo(
        datos_sinteticos, cfg, n_simulaciones=20, ruido=0.0, semilla=SEMILLA
    )
    assert (por_proyecto["rank_base"] == por_proyecto["rank_medio"]).all()
    assert (por_proyecto["amplitud_ic90"] == 0).all()


def test_mas_ruido_produce_menos_estabilidad(datos_sinteticos, cfg) -> None:
    bajo, _ = perturbacion_montecarlo(datos_sinteticos, cfg, n_simulaciones=200,
                                      ruido=0.05, semilla=SEMILLA)
    alto, _ = perturbacion_montecarlo(datos_sinteticos, cfg, n_simulaciones=200,
                                      ruido=0.60, semilla=SEMILLA)
    assert bajo["spearman_medio"].iat[0] > alto["spearman_medio"].iat[0]
