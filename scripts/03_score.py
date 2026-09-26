# -*- coding: utf-8 -*-
"""Paso 3: calificacion compuesta, analisis multivariado y sensibilidad.

Produce en salidas/ todo lo que la especificacion de direccion pide reportar
sobre el indice: ranking, faltantes, correlaciones y componentes
principales, alfa de Cronbach, robustez frente a esquemas y decisiones
metodologicas, Monte Carlo con Dirichlet e indices de primer orden.
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pandas as pd  # noqa: E402

from colombiainvest.config import (  # noqa: E402
    DIMENSIONES, DIR_PROCESADOS, DIR_SALIDAS, cargar_modelo,
)
from colombiainvest.modelo.multivariado import analisis_multivariado  # noqa: E402
from colombiainvest.modelo.score import calificar  # noqa: E402
from colombiainvest.modelo.sensibilidad import (  # noqa: E402
    comparar_esquemas, comparar_variantes, contribucion_dimensiones, perturbacion_montecarlo,
)

LINEA = "=" * 100


def titulo(texto: str) -> None:
    print(f"\n{LINEA}\n{texto}\n{LINEA}")


def guardar(tabla: pd.DataFrame, nombre: str, index: bool = False) -> None:
    tabla.to_csv(DIR_SALIDAS / nombre, index=index, encoding="utf-8-sig")


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--simulaciones", type=int, default=None,
                   help="por defecto, montecarlo.iteraciones de pesos.yaml")
    args = p.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)-7s %(message)s")
    pd.set_option("display.width", 170)
    pd.set_option("display.max_columns", 30)
    cfg = cargar_modelo()
    DIR_SALIDAS.mkdir(parents=True, exist_ok=True)

    df = pd.read_parquet(DIR_PROCESADOS / "proyectos_evaluables.parquet")

    # ---------------------------------------------------------------- score
    calificados, diag = calificar(df, cfg, nombre_esquema="esquema_base")
    calificados.to_parquet(DIR_SALIDAS / "proyectos_calificados.parquet", index=False)
    con_score = calificados.dropna(subset=["score"])
    # Sensibilidad y diagnosticos se corren sobre los proyectos calificables.
    base = df[df["bpin"].isin(con_score["bpin"])].reset_index(drop=True)

    cols = (["ranking", "bpin", "municipio", "sector", "score", "percentil_sector"]
            + [f"puntaje_{d}" for d in DIMENSIONES])
    guardar(calificados[cols + ["estado_calificacion", "completitud_ficha",
                                "pct_faltantes_modelo", "nombreproyecto"]], "ranking.csv")

    titulo(f"CALIFICACION. Agregacion {cfg.agregacion['metodo']}, "
           f"imputacion {cfg.normalizacion['imputacion_faltantes']}")
    f = diag["_faltantes"]
    print(f"  variables descartadas por faltantes (> {cfg.faltantes['max_por_variable']:.0%}): "
          f"{f['variables_descartadas'] or 'ninguna'}")
    print(f"  proyectos con informacion insuficiente (> {cfg.faltantes['max_por_proyecto']:.0%}): "
          f"{f['proyectos_insuficientes']}")
    print(f"  proyectos calificados con algun faltante (dimension reponderada): "
          f"{f['proyectos_con_algun_faltante']}")

    top = con_score.head(15)[cols + ["nombreproyecto"]].copy()
    top["nombreproyecto"] = top["nombreproyecto"].str.slice(0, 40)
    print("\nTOP 15")
    print(top.to_string(index=False))
    print("\n--- DISTRIBUCION DEL SCORE ---")
    print(con_score["score"].describe().round(2).to_string())
    print("\n--- SCORE MEDIO POR MUNICIPIO ---")
    print(con_score.groupby("municipio")["score"].agg(["count", "mean", "std"]).round(2).to_string())
    print("\n--- SCORE MEDIO POR COMPLETITUD DE FICHA (metadato, fuera del score) ---")
    print(con_score.groupby((con_score["completitud_ficha"] * 14).round().astype(int))["score"]
          .agg(["count", "mean"]).round(1).rename_axis("campos de 14").to_string())

    # ------------------------------------------------------- multivariado
    mv = analisis_multivariado(base, cfg)
    guardar(mv["correlaciones"], "multivariado_correlaciones.csv", index=True)
    guardar(mv["redundantes"], "multivariado_redundantes.csv")
    guardar(mv["pca_varianza"], "multivariado_pca_varianza.csv")
    guardar(mv["pca_cargas"], "multivariado_pca_cargas.csv", index=True)
    guardar(mv["cronbach"], "multivariado_cronbach.csv")
    titulo("ANALISIS MULTIVARIADO EXPLORATORIO")
    print("Pares con |Spearman| >= 0,8 (redundancia):")
    print(mv["redundantes"].to_string(index=False) if len(mv["redundantes"]) else "  ninguno")
    print("\nComponentes principales:")
    print(mv["pca_varianza"].head(8).to_string(index=False))
    print(f"\nCargas (componentes con autovalor > 1):")
    print(mv["pca_cargas"].to_string())
    print("\nAlfa de Cronbach por dimension:")
    print(mv["cronbach"].to_string(index=False))

    # ------------------------------------------------- contribucion por dim
    contrib = contribucion_dimensiones(base, cfg)
    guardar(contrib, "contribucion_dimensiones.csv")
    titulo("CONTRIBUCION DE CADA DIMENSION A LA VARIANZA DEL SCORE")
    print(contrib.round(4).to_string(index=False))

    # ---------------------------------------------------------- esquemas
    metricas, rankings = comparar_esquemas(base, cfg)
    guardar(metricas, "sensibilidad_esquemas.csv")
    guardar(rankings, "rankings_por_esquema.csv")
    umbral = cfg.montecarlo["umbral_spearman"]
    titulo(f"ROBUSTEZ FRENTE A ESQUEMAS DE PONDERACION (criterio Spearman > {umbral})")
    print(metricas[["esquema", "spearman", "kendall_tau", "cumple_umbral", "desplaz_medio",
                    "desplaz_max", "top10_estable", "top20_estable"]].round(4).to_string(index=False))
    ent = metricas.loc[metricas["esquema"] == "entropia"]
    if len(ent):
        print("  pesos por entropia: " + ", ".join(
            f"{d} {ent.iloc[0][f'w_{d}']:.3f}" for d in DIMENSIONES))

    # ---------------------------------------------------------- variantes
    variantes = comparar_variantes(df, cfg)
    guardar(variantes, "sensibilidad_variantes.csv")
    titulo("ROBUSTEZ FRENTE A DECISIONES METODOLOGICAS (mismos pesos)")
    print(variantes[["variante", "spearman", "cumple_umbral", "desplaz_medio",
                     "desplaz_max", "top10_estable", "top20_estable"]].round(4).to_string(index=False))

    # ------------------------------------- robustez de lo que ve el usuario
    # El score usa los 491 evaluables, pero la vista de oportunidades muestra
    # solo los vigentes. Se mide la estabilidad del orden dentro de ese grupo.
    vig = base["grupo_universo"] == "Vigente"
    met_vig, _ = comparar_esquemas(base, cfg, subconjunto=vig)
    var_vig = comparar_variantes(df, cfg, bpins=set(base.loc[vig, "bpin"]))
    guardar(met_vig, "sensibilidad_esquemas_vigentes.csv")
    guardar(var_vig, "sensibilidad_variantes_vigentes.csv")
    titulo(f"ROBUSTEZ DENTRO DE LOS PROYECTOS VIGENTES ({int(vig.sum())})")
    print(met_vig[["esquema", "spearman", "cumple_umbral", "desplaz_medio",
                   "top10_estable", "top20_estable"]].round(4).to_string(index=False))
    print(var_vig[["variante", "spearman", "cumple_umbral", "desplaz_medio",
                   "top10_estable", "top20_estable"]].round(4).to_string(index=False))

    # ---------------------------------------------------------- monte carlo
    resumen_mc, por_proyecto, primer_orden = perturbacion_montecarlo(
        base, cfg, n_simulaciones=args.simulaciones)
    guardar(resumen_mc, "sensibilidad_montecarlo.csv")
    guardar(por_proyecto, "estabilidad_por_proyecto.csv")
    guardar(primer_orden, "sensibilidad_primer_orden.csv")
    titulo("INCERTIDUMBRE SOBRE LOS PESOS: MONTE CARLO")
    print(resumen_mc.round(4).to_string(index=False))
    print("\nIndices de sensibilidad de primer orden (salida: desplazamiento medio del ranking):")
    print(primer_orden.to_string(index=False))
    print(f"  suma de indices: {primer_orden['indice_primer_orden'].sum():.3f} "
          "(la diferencia con 1 corresponde a interacciones)")
    print("\nIntervalo de posiciones del top 10 (percentiles 5 y 95):")
    print(por_proyecto.head(10)[["rank_base", "bpin", "score_base", "rank_medio",
                                 "rank_p05", "rank_p95", "amplitud_ic90"]].to_string(index=False))

    resumen = {
        "agregacion": cfg.agregacion, "normalizacion": cfg.normalizacion,
        "faltantes": {**cfg.faltantes, **diag["_faltantes"]},
        "calificados": int(len(con_score)),
        "montecarlo": resumen_mc.iloc[0].to_dict(),
        "spearman_min_esquemas": float(metricas["spearman"].min()),
        "spearman_min_variantes": float(variantes["spearman"].min()),
        "spearman_min_vigentes": float(min(met_vig["spearman"].min(), var_vig["spearman"].min())),
    }
    with open(DIR_SALIDAS / "resumen_modelo.json", "w", encoding="utf-8") as fh:
        json.dump(resumen, fh, ensure_ascii=False, indent=2, default=str)

    print(f"\nSalidas escritas en {DIR_SALIDAS}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
