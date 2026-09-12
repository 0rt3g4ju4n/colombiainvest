# -*- coding: utf-8 -*-
"""Paso 2: construccion del dataset de proyectos y calculo de variables."""
from __future__ import annotations

import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pandas as pd  # noqa: E402

from colombiainvest.config import DIR_PROCESADOS, cargar_modelo  # noqa: E402
from colombiainvest.procesamiento.variables import (  # noqa: E402
    cargar_crudos,
    calcular_variables,
    construir_tabla_proyectos,
    filtrar_universo_evaluable,
    variables_requeridas,
)


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
    evaluable.to_csv(DIR_PROCESADOS / "proyectos_evaluables.csv", index=False, encoding="utf-8-sig")

    print("\n=== DATASET CONSTRUIDO ===")
    print(f"  universo total    : {len(tabla)} proyectos")
    print(f"  universo evaluable: {len(evaluable)} proyectos (con apropiacion > 0)")
    print(f"  municipios        : {evaluable['municipio'].value_counts().to_dict()}")

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
