# -*- coding: utf-8 -*-
"""Pruebas de los cambios pedidos por la evaluacion de direccion.

Cubren: completitud fuera del score, cero real frente a faltante, regla de
exclusion por faltantes, agregacion geometrica, desglose por variable,
percentil por sector, reasignacion de municipio, AHP, W de Kendall, indice
de validez de contenido y analisis multivariado.

Los datos sinteticos se usan solo para verificar el comportamiento del
codigo en casos borde; no sustituyen los datos reales del caso.
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
from colombiainvest.modelo import ahp  # noqa: E402
from colombiainvest.modelo.score import (  # noqa: E402
    agregar_dimensiones, aportes_por_variable, calcular_dimensiones, calificar,
    percentil_en_grupo,
)

SEMILLA = 42


@pytest.fixture(scope="module")
def cfg() -> ConfigModelo:
    return cargar_modelo(ruta_panel=None)


@pytest.fixture()
def sinteticos(cfg: ConfigModelo) -> pd.DataFrame:
    rng = np.random.default_rng(SEMILLA)
    n = 50
    filas = {"bpin": [f"B{i:04d}" for i in range(n)],
             "nombreproyecto": [f"Proyecto {i}" for i in range(n)],
             "sector": rng.choice(["Salud", "Educacion", "Transporte"], n)}
    for dim in DIMENSIONES:
        for var in cfg.variables_activas(dim):
            filas[var] = rng.uniform(0, 100, n)
    return pd.DataFrame(filas)


# ---------------------------------------------------------------------------
# completitud y faltantes
# ---------------------------------------------------------------------------
def test_completitud_no_entra_al_score(cfg: ConfigModelo) -> None:
    """La direccion exige la completitud como metadato, nunca en el score."""
    activas = [v for d in DIMENSIONES for v in cfg.variables_activas(d)]
    assert not any("completitud" in v for v in activas)


def test_dimension_se_repondera_si_falta_una_variable(sinteticos, cfg) -> None:
    datos = sinteticos.copy()
    var = next(iter(cfg.variables_activas("madurez_ejecucion")))
    datos.loc[0, var] = np.nan
    puntajes, _ = calcular_dimensiones(datos, cfg)
    assert puntajes["madurez_ejecucion"].notna().all()
    # el puntaje es la media ponderada de las variables que si tiene
    cols = [c for c in puntajes.columns if c.startswith("madurez_ejecucion__")]
    pesos = {c: cfg.variables("madurez_ejecucion")[c.split("__")[1]]["peso"] for c in cols}
    fila = puntajes.loc[0, cols]
    esperado = sum(fila[c] * p for c, p in pesos.items() if pd.notna(fila[c]))
    esperado /= sum(p for c, p in pesos.items() if pd.notna(fila[c]))
    assert puntajes.loc[0, "madurez_ejecucion"] == pytest.approx(esperado * 100)


def test_variable_con_muchos_faltantes_se_descarta(sinteticos, cfg) -> None:
    datos = sinteticos.copy()
    var = next(iter(cfg.variables_activas("impacto_social")))
    datos.loc[datos.index[:20], var] = np.nan          # 40 % > 30 %
    _, diag = calificar(datos, cfg)
    assert var in diag["_faltantes"]["variables_descartadas"]


def test_proyecto_con_muchos_faltantes_no_se_califica(sinteticos, cfg) -> None:
    datos = sinteticos.copy()
    activas = [v for d in DIMENSIONES for v in cfg.variables_activas(d)]
    datos.loc[0, activas[: int(len(activas) * 0.6)]] = np.nan
    res, diag = calificar(datos, cfg)
    fila = res.loc[res["bpin"] == "B0000"].iloc[0]
    assert pd.isna(fila["score"])
    assert fila["estado_calificacion"] == cfg.faltantes["etiqueta_insuficiente"]
    assert diag["_faltantes"]["proyectos_insuficientes"] == 1
    # queda al final y no ocupa puesto en el ranking
    assert res.iloc[-1]["bpin"] == "B0000"
    assert res["ranking"].dropna().max() == len(datos) - 1


def test_cero_contradictorio_se_trata_como_faltante(cfg: ConfigModelo) -> None:
    from colombiainvest.procesamiento.variables import calcular_variables
    base = {
        "bpin": ["A", "B", "C"], "nombreproyecto": ["Construccion x"] * 3,
        "sector": ["Educacion"] * 3, "codigomunicipio": ["25126"] * 3,
        "estadoproyecto": ["En Ejecucion"] * 3, "subestadoproyecto": ["Inactivo"] * 3,
        "horizonte": ["2020-2023"] * 3, "completitud_ficha_v": [1.0] * 3,
        # A: ficha vacia y seguimiento contradictorio. B: ceros coherentes. C: completo.
        "valortotalproyecto": [0, 0, 100], "valorvigenteproyecto": [0, 0, 100],
        "valor_vigente_total": [100, 100, 100], "valor_obligado_total": [50, 0, 60],
        "valor_pagado_total": [40, 0, 60], "avancefisico": [0, 0, 70],
        "avancefinanciero": [0, 0, 60], "totalbeneficiario": [10, 10, 10],
    }
    out = calcular_variables(pd.DataFrame(base), cfg).set_index("bpin")
    assert pd.isna(out.loc["A", "avance_fisico"])            # contradiccion
    assert pd.isna(out.loc["A", "brecha_fisico_financiero"])
    assert out.loc["B", "avance_fisico"] == 0                  # cero coherente
    assert pd.isna(out.loc["A", "consistencia_financiera"])    # ficha vacia
    assert pd.isna(out.loc["B", "consistencia_financiera"])
    assert out.loc["C", "avance_fisico"] == 70


# ---------------------------------------------------------------------------
# agregacion
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("metodo", ["geometrica", "aritmetica"])
def test_dimensiones_iguales_dan_ese_mismo_score(metodo: str) -> None:
    m = np.full((1, 5), 63.0)
    w = np.array([0.25, 0.20, 0.25, 0.20, 0.10])
    assert agregar_dimensiones(m, w, metodo, 1.0)[0] == pytest.approx(63.0)


def test_geometrica_no_supera_a_la_aritmetica() -> None:
    rng = np.random.default_rng(SEMILLA)
    m = rng.uniform(0, 100, (200, 5))
    w = np.array([0.25, 0.20, 0.25, 0.20, 0.10])
    geo = agregar_dimensiones(m, w, "geometrica", 1.0)
    ari = agregar_dimensiones(m, w, "aritmetica", 1.0)
    assert (geo <= ari + 1e-9).all()


def test_geometrica_limita_la_compensacion() -> None:
    """Una dimension en cero no se compensa con las demas en 100."""
    w = np.full(5, 0.2)
    desbalanceado = np.array([[100, 100, 100, 100, 0.0]])
    parejo = np.array([[80.0] * 5])
    assert agregar_dimensiones(desbalanceado, w, "aritmetica", 1.0)[0] == pytest.approx(80)
    assert agregar_dimensiones(desbalanceado, w, "geometrica", 1.0)[0] < \
        agregar_dimensiones(parejo, w, "geometrica", 1.0)[0]
    # el piso evita que un solo cero anule todo el puntaje
    assert agregar_dimensiones(desbalanceado, w, "geometrica", 1.0)[0] > 0


def test_agregacion_vectorizada_coincide(sinteticos, cfg) -> None:
    """Varios esquemas a la vez (Monte Carlo) dan lo mismo que uno por uno."""
    puntajes, _ = calcular_dimensiones(sinteticos, cfg)
    m = puntajes[DIMENSIONES].to_numpy()
    w = np.array([[0.2] * 5, [0.25, 0.20, 0.25, 0.20, 0.10]])
    lote = agregar_dimensiones(m, w, "geometrica", 1.0)
    for k in range(2):
        np.testing.assert_allclose(lote[k], agregar_dimensiones(m, w[k], "geometrica", 1.0))


# ---------------------------------------------------------------------------
# interpretabilidad
# ---------------------------------------------------------------------------
def test_aportes_suman_el_puntaje_de_la_dimension(sinteticos, cfg) -> None:
    datos = sinteticos.copy()
    datos.loc[3, next(iter(cfg.variables_activas("gobernanza")))] = np.nan
    puntajes, _ = calcular_dimensiones(datos, cfg)
    aportes = aportes_por_variable(puntajes, cfg)
    for dim in DIMENSIONES:
        cols = [c for c in aportes.columns if c.startswith(f"{dim}__")]
        np.testing.assert_allclose(aportes[cols].sum(axis=1, min_count=1), puntajes[dim])


def test_percentil_por_sector() -> None:
    score = pd.Series([10, 50, 90, 30, 70])
    sector = pd.Series(["a", "a", "a", "b", "b"])
    p = percentil_en_grupo(score, sector)
    assert p.between(0, 100).all()
    assert p[2] == 100 and p[4] == 100          # el mejor de cada sector


def test_municipio_se_reasigna_por_entidad() -> None:
    from colombiainvest.procesamiento.variables import _asignar_municipio_por_entidad
    base = pd.DataFrame({"bpin": ["X"], "municipio": ["Todo el Depto"],
                         "codigomunicipio": ["25000"],
                         "entidadresponsable": ["CajicáCundinamarca"]})
    out = _asignar_municipio_por_entidad(base)
    assert out.loc[0, "municipio"] == "Cajicá"
    assert out.loc[0, "codigomunicipio"] == "25126"
    assert out.loc[0, "municipio_localizacion"] == "Todo el Depto"


# ---------------------------------------------------------------------------
# AHP y concordancia
# ---------------------------------------------------------------------------
ELEMENTOS = DIMENSIONES


def _matriz_consistente(w: np.ndarray) -> np.ndarray:
    return w[:, None] / w[None, :]


def test_ahp_recupera_pesos_de_matriz_consistente() -> None:
    w = np.array([0.35, 0.25, 0.20, 0.12, 0.08])
    a = _matriz_consistente(w)
    est, lmax = ahp.prioridades(a)
    np.testing.assert_allclose(est, w, atol=1e-9)
    assert lmax == pytest.approx(5.0)
    assert ahp.razon_consistencia(a)[0] == pytest.approx(0.0, abs=1e-9)


def test_ahp_detecta_inconsistencia() -> None:
    """A > B, B > C y C > A de forma fuerte: circular, CR alto."""
    juicios = {(a, b): 1.0 for a, b in ahp.pares(ELEMENTOS)}
    juicios[(ELEMENTOS[0], ELEMENTOS[1])] = 9.0
    juicios[(ELEMENTOS[1], ELEMENTOS[2])] = 9.0
    juicios[(ELEMENTOS[0], ELEMENTOS[2])] = 1 / 9
    a = ahp.matriz_desde_juicios(juicios, ELEMENTOS)
    cr, _, _ = ahp.razon_consistencia(a)
    assert cr > 0.10
    revisar = ahp.juicio_mas_inconsistente(a, ELEMENTOS)
    assert {revisar["dimension_a"], revisar["dimension_b"]} <= set(ELEMENTOS[:3])


def test_valor_juicio_escala_saaty() -> None:
    assert ahp.valor_juicio("A", 5) == 5
    assert ahp.valor_juicio("B", 5) == pytest.approx(0.2)
    assert ahp.valor_juicio("=", 7) == 1
    with pytest.raises(ValueError):
        ahp.valor_juicio("A", 10)


def test_agregacion_geometrica_conserva_reciprocidad() -> None:
    rng = np.random.default_rng(SEMILLA)
    mats = [_matriz_consistente(rng.dirichlet(np.ones(5))) for _ in range(4)]
    g = ahp.agregar_juicios(mats)
    np.testing.assert_allclose(g * g.T, np.ones((5, 5)))


def test_w_kendall_extremos() -> None:
    iguales = np.array([[1, 2, 3, 4, 5]] * 4)
    assert ahp.w_kendall(iguales) == pytest.approx(1.0)
    opuestos = np.array([[1, 2, 3, 4, 5], [5, 4, 3, 2, 1]])
    assert ahp.w_kendall(opuestos) == pytest.approx(0.0)


def test_significancia_kendall_con_acuerdo_perfecto() -> None:
    r = np.array([[1, 2, 3, 4, 5]] * 5)
    s = ahp.significancia_kendall(r, n_permutaciones=500, semilla=SEMILLA)
    assert s["w_kendall"] == pytest.approx(1.0)
    assert s["p_permutacion"] < 0.01


def _escribir_respuestas(ruta: Path, expertos: dict) -> None:
    filas = []
    for exp, w in expertos.items():
        for a, b in ahp.pares(ELEMENTOS):
            i, j = ELEMENTOS.index(a), ELEMENTOS.index(b)
            razon = w[i] / w[j]
            pref, k = ("A", razon) if razon >= 1 else ("B", 1 / razon)
            filas.append([exp, "Financiero", "2026-09-29", a, b, pref,
                          str(min(max(int(round(k)), 1), 9))])
    pd.DataFrame(filas, columns=ahp.COLUMNAS).to_csv(ruta, sep=";", index=False,
                                                     encoding="utf-8-sig")


def test_panel_de_extremo_a_extremo(tmp_path: Path) -> None:
    ruta = tmp_path / "respuestas.csv"
    _escribir_respuestas(ruta, {
        "E01": np.array([0.30, 0.20, 0.25, 0.15, 0.10]),
        "E02": np.array([0.28, 0.22, 0.25, 0.15, 0.10]),
        "E03": np.array([0.32, 0.18, 0.26, 0.14, 0.10]),
    })
    resp = ahp.leer_respuestas(ruta, ELEMENTOS)
    res = ahp.resultado_panel(resp, ELEMENTOS, n_permutaciones=200)
    assert len(res["consistentes"]) == 3
    pesos = res["agregado"]["pesos"]
    assert abs(sum(pesos.values()) - 1) < 1e-9
    assert max(pesos, key=pesos.get) == ELEMENTOS[0]
    assert res["concordancia"]["w_kendall"] > 0.8


def test_respuestas_incompletas_fallan_con_mensaje(tmp_path: Path) -> None:
    ruta = tmp_path / "respuestas.csv"
    _escribir_respuestas(ruta, {"E01": np.array([0.3, 0.2, 0.25, 0.15, 0.1])})
    df = pd.read_csv(ruta, sep=";").iloc[:-1]
    df.to_csv(ruta, sep=";", index=False)
    with pytest.raises(ValueError, match="faltan 1 comparaciones"):
        ahp.leer_respuestas(ruta, ELEMENTOS)


def test_par_escrito_al_reves_se_invierte(tmp_path: Path) -> None:
    ruta = tmp_path / "respuestas.csv"
    _escribir_respuestas(ruta, {"E01": np.array([0.3, 0.2, 0.25, 0.15, 0.1])})
    df = pd.read_csv(ruta, sep=";", dtype=str)
    a, b = df.loc[0, "dimension_a"], df.loc[0, "dimension_b"]
    df.loc[0, ["dimension_a", "dimension_b"]] = [b, a]
    df.loc[0, "preferida"] = {"A": "B", "B": "A"}[df.loc[0, "preferida"]]
    df.to_csv(ruta, sep=";", index=False)
    original = ahp.leer_respuestas(ruta, ELEMENTOS)
    assert (original["dimension_a"].iloc[0], original["dimension_b"].iloc[0]) == (a, b)


def test_indice_validez_contenido() -> None:
    c = pd.DataFrame({"experto": ["E1", "E2", "E3"] * 2,
                      "variable": ["x"] * 3 + ["y"] * 3,
                      "relevancia": [4, 3, 4, 4, 2, 1]})
    por_var, resumen = ahp.indice_validez_contenido(c)
    icvi = por_var.set_index("variable")["i_cvi"]
    assert icvi["x"] == 1.0 and icvi["y"] == pytest.approx(1 / 3, abs=1e-3)
    assert resumen["umbral_i_cvi"] == 1.0          # cinco expertos o menos
    assert resumen["s_cvi_ave"] == pytest.approx((1 + 1 / 3) / 2, abs=1e-3)


# ---------------------------------------------------------------------------
# multivariado
# ---------------------------------------------------------------------------
def test_analisis_multivariado(sinteticos, cfg) -> None:
    from colombiainvest.modelo.multivariado import analisis_multivariado
    datos = sinteticos.copy()
    # dos variables casi identicas deben aparecer como redundantes
    a = next(iter(cfg.variables_activas("impacto_social")))
    b = next(iter(cfg.variables_activas("atractivo_inversor")))
    datos[b] = datos[a] * 1.01
    mv = analisis_multivariado(datos, cfg)
    assert mv["pca_varianza"]["varianza_explicada"].sum() == pytest.approx(1.0, abs=1e-3)
    red = mv["redundantes"]
    assert ((red["variable_a"].str.endswith(a) & red["variable_b"].str.endswith(b))
            | (red["variable_a"].str.endswith(b) & red["variable_b"].str.endswith(a))).any()
    assert set(mv["cronbach"]["dimension"]) == set(DIMENSIONES)


def test_diccionario_cubre_todas_las_variables(cfg: ConfigModelo) -> None:
    """Cada variable del modelo tiene definicion, fuente y lectura documentadas."""
    import yaml
    from colombiainvest.config import DIR_CONFIG
    with open(DIR_CONFIG / "diccionario_variables.yaml", encoding="utf-8") as f:
        dicc = yaml.safe_load(f)
    for dim in DIMENSIONES:
        for var in cfg.variables(dim):
            assert var in dicc["variables"], var
            assert dicc["variables"][var]["dimension"] == dim, var
            for campo in ("nombre", "definicion", "fuente", "lectura"):
                assert dicc["variables"][var].get(campo), f"{var}.{campo}"


# ---------------------------------------------------------------------------
# universo vigente y previo, validez convergente
# ---------------------------------------------------------------------------
def test_previo_no_es_sinonimo_de_terminado(cfg: ConfigModelo) -> None:
    from colombiainvest.procesamiento.variables import clasificar_vigencia
    estado = pd.Series(["Inactivo", "Inactivo", "Inactivo", "Inactivo", "En ejecución"])
    reportado = pd.Series([100.0, 40.0, 0.0, 0.0, 0.0])
    valido = pd.Series([100.0, 40.0, 0.0, np.nan, 0.0])
    grupo, situacion = clasificar_vigencia(estado, reportado, valido, cfg)
    assert list(grupo) == ["Previo"] * 4 + ["Vigente"]
    assert list(situacion[:4]) == ["Terminado", "Avance parcial", "Sin avance reportado",
                                   "Sin dato valido de avance"]


def test_robustez_en_subconjunto(sinteticos, cfg) -> None:
    from colombiainvest.modelo.sensibilidad import comparar_esquemas
    mascara = pd.Series(np.arange(len(sinteticos)) < 20)
    metricas, rankings = comparar_esquemas(sinteticos, cfg, subconjunto=mascara)
    assert len(rankings) == 20
    assert rankings["esquema_base"].max() <= 20


def test_validez_convergente_detecta_relacion() -> None:
    from colombiainvest.modelo.validacion import validez_convergente
    rng = np.random.default_rng(SEMILLA)
    sectores = ["EDUCACION", "CULTURA", "TRANSPORTE", "TRABAJO", "DEPORTE Y RECREACION",
                "SALUD Y PROTECCION SOCIAL"]
    filas = []
    for i, s in enumerate(sectores):
        for j in range(3):
            filas.append({"bpin": f"{i}{j}", "municipio": "Cajicá", "grupo_universo": "Vigente",
                          "sector": s, "score": 20 + 10 * i + rng.normal(0, 1),
                          "puntaje_viabilidad_financiera": 50.0,
                          "puntaje_madurez_ejecucion": 50.0})
    informe = pd.DataFrame({
        "sector_informe": ["EDUCACION", "CULTURA", "TRANSPORTE", "TRABAJO", "DEPORTE",
                           "SALUD Y PROTECCION SOCIAL"],
        "avance_fisico_sector": [10, 20, 30, 40, 50, 60],
        "ejecucion_presupuestal_sector": [60, 50, 40, 30, 20, 10],
    })
    pruebas, por_sector = validez_convergente(pd.DataFrame(filas), informe)
    assert len(por_sector) == 6          # el puente une DEPORTE Y RECREACION con DEPORTE
    fila = pruebas.set_index("contraste").loc["Score total frente a avance fisico del sector"]
    assert fila["spearman"] == pytest.approx(1.0) and fila["cumple"]
    fila = pruebas.set_index("contraste").loc["Score total frente a ejecucion presupuestal"]
    assert not fila["cumple"]            # relacion negativa: no cumple el sentido esperado


def test_sin_redundancia_extrema_en_datos_reales(cfg: ConfigModelo) -> None:
    """Ninguna pareja de variables del score mide lo mismo (Spearman >= 0,9).

    Usa los datos reales si ya fueron construidos; si no, se omite.
    """
    ruta = RAIZ / "datos" / "procesados" / "proyectos_evaluables.parquet"
    if not ruta.exists():
        pytest.skip("datos procesados no construidos")
    from colombiainvest.modelo.multivariado import matriz_variables, pares_redundantes
    x = matriz_variables(pd.read_parquet(ruta), cfg)
    assert pares_redundantes(x, umbral=0.9).empty


# ---------------------------------------------------------------------------
# vinculacion de capital privado por tipo de intervencion
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("nombre, esperado", [
    ("Construcción De Centro Cultural", "Inversion en capital"),
    ("Construccin De Centro Estratgico", "Inversion en capital"),      # tilde corrupta
    ("Actualizacin De La Infraestructura TIC", "Mejoramiento"),
    ("Diseño Y Construcción De Alcantarillado", "Inversion en capital"),  # verbo ambiguo con obra
    ("Diseño De Un Centro Acuático", "Preinversion"),
    ("Administración Operación Reposición Y Expansión Del Alumbrado", "Inversion en capital"),
    ("Administración Del Régimen Subsidiado En Salud", "Fortalecimiento institucional"),
    ("Desarrollo Del Aseguramiento Integral", "Fortalecimiento institucional"),
    ("Prevención Y Atención De Desastres", "Implementacion de programa"),
    ("", "Sin clasificar"),
])
def test_clasificar_intervencion(nombre: str, esperado: str) -> None:
    from colombiainvest.procesamiento.variables import clasificar_intervencion
    assert clasificar_intervencion(nombre) == esperado


def test_mapeo_vinculacion_cubre_todos_los_tipos(cfg: ConfigModelo) -> None:
    from colombiainvest.procesamiento.variables import TIPO_INTERVENCION
    mapeo = cfg.mapeos["vinculacion_privada"]
    assert set(TIPO_INTERVENCION) <= set(mapeo)
    assert "_defecto" in mapeo
    assert all(0 <= v <= 1 for v in mapeo.values())
    # una obra fisica es mas vinculable que un programa de funcionamiento
    assert mapeo["Inversion en capital"] > mapeo["Fortalecimiento institucional"]
