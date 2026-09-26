# -*- coding: utf-8 -*-
"""Paso 2: construccion del dataset de proyectos y calculo de variables.

Ademas del dataset, escribe datos/procesados/universo.json con el conteo de
proyectos por municipio, su nivel de completitud y la fecha de corte. Es la
condicion de aprobacion 2 de la direccion: "el universo de datos esta
cuantificado".
"""
from __future__ import annotations

import json
import logging
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pandas as pd  # noqa: E402

from colombiainvest.config import DIR_CRUDOS, DIR_PROCESADOS, cargar_modelo  # noqa: E402
from colombiainvest.modelo.score import evaluar_faltantes  # noqa: E402
from colombiainvest.procesamiento.variables import (  # noqa: E402
    cargar_crudos,
    calcular_variables,
    construir_tabla_proyectos,
    filtrar_universo_evaluable,
    variables_requeridas,
)


def fecha_corte() -> dict:
    """Lee la fecha registrada en la ingesta; si no existe, la deriva.

    Las descargas anteriores a la version 0.2.0 no registraban la fecha. En
    ese caso se toma la fecha de modificacion de los archivos crudos, que es
    la fecha en que se descargaron, y se declara que es derivada.
    """
    ruta = DIR_CRUDOS / "corte.json"
    if ruta.exists():
        with open(ruta, encoding="utf-8") as f:
            return {**json.load(f), "origen": "registrada en la ingesta"}
    archivos = list(DIR_CRUDOS.glob("*.json"))
    fecha = max(datetime.fromtimestamp(p.stat().st_mtime) for p in archivos) if archivos else None
    return {"fecha_corte": fecha.strftime("%Y-%m-%d") if fecha else None,
            "fuente": "SUIFP, DNP, via datos.gov.co",
            "origen": "derivada de la fecha de los archivos descargados"}


def _conteo(serie: pd.Series) -> dict:
    return {str(k): int(v) for k, v in serie.value_counts().sort_index().items()}


def informe_universo(tabla: pd.DataFrame, evaluable: pd.DataFrame, cfg) -> dict:
    falt = evaluar_faltantes(evaluable, cfg)
    subestado = evaluable["subestadoproyecto"].astype(str).str.replace("\xa0", " ").str.split().str.join(" ")
    completitud = (evaluable["completitud_ficha"] * 14).round().astype(int).astype(str) + " de 14"
    por_mun = {}
    for mun, g in evaluable.groupby("municipio"):
        idx = g.index
        por_mun[str(mun)] = {
            "evaluables": int(len(g)),
            "ficha_completa": int((g["completitud_ficha"] >= 0.999).sum()),
            "ficha_financiera_vacia": int(g["dato_ficha_financiera_vacia"].sum()),
            "seguimiento_contradictorio": int(g["dato_seguimiento_contradictorio"].sum()),
            "con_algun_faltante": int((falt["pct_faltantes"].loc[idx] > 0).sum()),
            "informacion_insuficiente": int(falt["insuficiente"].loc[idx].sum()),
            "vigentes": int((g["grupo_universo"] == "Vigente").sum()),
            "previos": int((g["grupo_universo"] == "Previo").sum()),
            "subestado": _conteo(subestado.loc[idx]),
        }
    return {
        "corte": fecha_corte(),
        "identificados": int(len(tabla)),
        "identificados_por_municipio": _conteo(tabla["municipio"]),
        "evaluables": int(len(evaluable)),
        "regla_evaluable": "apropiacion vigente acumulada mayor que cero",
        "por_municipio": por_mun,
        "completitud_ficha": _conteo(completitud),
        "vigentes": int((evaluable["grupo_universo"] == "Vigente").sum()),
        "previos": int((evaluable["grupo_universo"] == "Previo").sum()),
        "situacion_previos": _conteo(
            evaluable.loc[evaluable["grupo_universo"] == "Previo", "situacion"]),
        "variables_descartadas": falt["descartadas"],
        "informacion_insuficiente": int(falt["insuficiente"].sum()),
        "faltantes_por_variable": {
            v: int(evaluable[v].isna().sum())
            for v in variables_requeridas(cfg) if evaluable[v].isna().any()
        },
        "municipio_reasignado_por_entidad": int(
            (evaluable["municipio_localizacion"] != evaluable["municipio"]).sum()),
    }


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)-7s %(message)s")
    cfg = cargar_modelo()
    DIR_PROCESADOS.mkdir(parents=True, exist_ok=True)

    crudos = cargar_crudos()
    tabla = construir_tabla_proyectos(crudos, cfg)
    tabla = calcular_variables(tabla, cfg)

    evaluable = filtrar_universo_evaluable(tabla, exigir_ejecucion=True)

    tabla.to_parquet(DIR_PROCESADOS / "proyectos_completo.parquet", index=False)
    evaluable.to_parquet(DIR_PROCESADOS / "proyectos_evaluables.parquet", index=False)

    universo = informe_universo(tabla, evaluable, cfg)
    with open(DIR_PROCESADOS / "universo.json", "w", encoding="utf-8") as f:
        json.dump(universo, f, ensure_ascii=False, indent=2)

    print("\n=== UNIVERSO DE DATOS ===")
    print(f"  fecha de corte    : {universo['corte']['fecha_corte']} "
          f"({universo['corte']['origen']})")
    print(f"  identificados     : {universo['identificados']} proyectos BPIN "
          f"{universo['identificados_por_municipio']}")
    print(f"  evaluables        : {universo['evaluables']} ({universo['regla_evaluable']})")
    for mun, d in universo["por_municipio"].items():
        print(f"    {mun:<8} {d['evaluables']:>4} evaluables | ficha completa {d['ficha_completa']:>4}"
              f" | ficha financiera vacia {d['ficha_financiera_vacia']:>4}"
              f" | seguimiento contradictorio {d['seguimiento_contradictorio']:>4}"
              f" | informacion insuficiente {d['informacion_insuficiente']}")
    print(f"  vigentes / previos: {universo['vigentes']} / {universo['previos']}"
          f" | situacion de los previos: {universo['situacion_previos']}")
    print(f"  completitud ficha : {universo['completitud_ficha']}")
    print(f"  faltantes por var : {universo['faltantes_por_variable']}")
    print(f"  municipio reasignado por entidad responsable: "
          f"{universo['municipio_reasignado_por_entidad']}")

    print("\n=== VARIABLES DEL MODELO (universo evaluable) ===")
    req = variables_requeridas(cfg)
    resumen = evaluable[req].describe().T[["count", "mean", "std", "min", "50%", "max"]]
    resumen["nulos"] = evaluable[req].isna().sum()
    resumen["varianza_cero"] = evaluable[req].std(ddof=0) == 0
    pd.set_option("display.width", 160)
    print(resumen.round(3).to_string())

    sin_varianza = [c for c in req if evaluable[c].std(ddof=0) == 0]
    if sin_varianza:
        print("\n  ADVERTENCIA: variables sin varianza (no discriminan): ", sin_varianza)

    n_excede = int(evaluable["excede_poblacion"].sum())
    print(f"\n  Proyectos que declaran mas beneficiarios que habitantes: {n_excede}"
          f" ({100*n_excede/len(evaluable):.1f}%). Tratados con tope de cobertura 1.0.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
