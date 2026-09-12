# -*- coding: utf-8 -*-
"""Paso 3: calificacion compuesta y analisis de sensibilidad de la ponderacion."""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pandas as pd  # noqa: E402

from colombiainvest.config import (  # noqa: E402
    DIMENSIONES, DIR_PROCESADOS, DIR_SALIDAS, cargar_modelo,
)
from colombiainvest.modelo.score import calificar  # noqa: E402
from colombiainvest.modelo.sensibilidad import (  # noqa: E402
    comparar_esquemas, contribucion_dimensiones, perturbacion_montecarlo,
)


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--simulaciones", type=int, default=1000)
    p.add_argument("--ruido", type=float, default=0.15)
    args = p.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)-7s %(message)s")
    pd.set_option("display.width", 170)
    cfg = cargar_modelo()
    DIR_SALIDAS.mkdir(parents=True, exist_ok=True)

    df = pd.read_parquet(DIR_PROCESADOS / "proyectos_evaluables.parquet")

    # ---------------------------------------------------------------- score
    calificados, diag = calificar(df, cfg, nombre_esquema="esquema_base")
    calificados.to_parquet(DIR_SALIDAS / "proyectos_calificados.parquet", index=False)

    cols = ["ranking", "bpin", "municipio", "sector", "score"] + [f"puntaje_{d}" for d in DIMENSIONES]
    calificados[cols + ["nombreproyecto"]].to_csv(
        DIR_SALIDAS / "ranking.csv", index=False, encoding="utf-8-sig"
    )

    print("\n" + "=" * 100)
    print("TOP 15 PROYECTOS, ESQUEMA BASE")
    print("=" * 100)
    top = calificados.head(15)[cols + ["nombreproyecto"]].copy()
    top["nombreproyecto"] = top["nombreproyecto"].str.slice(0, 42)
    print(top.to_string(index=False))

    print("\n--- DISTRIBUCION DEL SCORE ---")
    print(calificados["score"].describe().round(2).to_string())
    print("\n--- PUNTAJE MEDIO POR DIMENSION ---")
    print(calificados[[f"puntaje_{d}" for d in DIMENSIONES]].mean().round(2).to_string())
    print("\n--- SCORE MEDIO POR MUNICIPIO ---")
    print(calificados.groupby("municipio")["score"].agg(["count", "mean", "std"]).round(2).to_string())

    # ------------------------------------------------- contribucion por dim
    contrib = contribucion_dimensiones(df, cfg)
    contrib.to_csv(DIR_SALIDAS / "contribucion_dimensiones.csv", index=False, encoding="utf-8-sig")
    print("\n" + "=" * 100)
    print("CONTRIBUCION DE CADA DIMENSION A LA VARIANZA DEL SCORE")
    print("Si una dimension aporta poco, su peso es decorativo.")
    print("=" * 100)
    print(contrib.round(4).to_string(index=False))

    # ---------------------------------------------------------- sensibilidad
    metricas, rankings = comparar_esquemas(df, cfg)
    metricas.to_csv(DIR_SALIDAS / "sensibilidad_esquemas.csv", index=False, encoding="utf-8-sig")
    rankings.to_csv(DIR_SALIDAS / "rankings_por_esquema.csv", index=False, encoding="utf-8-sig")
    print("\n" + "=" * 100)
    print("SENSIBILIDAD: ESQUEMA BASE CONTRA ESQUEMAS ALTERNATIVOS")
    print("=" * 100)
    print(metricas.drop(columns=["descripcion"]).round(4).to_string(index=False))
    for _, r in metricas.iterrows():
        print(f"  {r['esquema']}: {r['descripcion']}")

    # ---------------------------------------------------------- monte carlo
    resumen_mc, por_proyecto = perturbacion_montecarlo(
        df, cfg, n_simulaciones=args.simulaciones, ruido=args.ruido
    )
    resumen_mc.to_csv(DIR_SALIDAS / "sensibilidad_montecarlo.csv", index=False, encoding="utf-8-sig")
    por_proyecto.to_csv(DIR_SALIDAS / "estabilidad_por_proyecto.csv", index=False, encoding="utf-8-sig")
    print("\n" + "=" * 100)
    print(f"SENSIBILIDAD MONTE CARLO: {args.simulaciones} perturbaciones de los pesos "
          f"con ruido relativo {args.ruido:.0%}")
    print("=" * 100)
    print(resumen_mc.round(4).to_string(index=False))
    print("\n  Estabilidad del top 10 (intervalo de confianza del 90% de la posicion):")
    print(por_proyecto.head(10)[
        ["rank_base", "bpin", "score_base", "rank_medio", "rank_p05", "rank_p95", "amplitud_ic90"]
    ].to_string(index=False))

    print(f"\nSalidas escritas en {DIR_SALIDAS}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
