# -*- coding: utf-8 -*-
"""Paso 4: procesamiento de documentos municipales y contraste con el SUIFP.

Los documentos son asimetricos (solo Cajica 2024), asi que no alimentan el
score. Este script produce el enriquecimiento de ficha para el prototipo y
el contraste de avance entre el SUIFP y el informe de gestion municipal.
"""
from __future__ import annotations

import logging
import sys
import unicodedata
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pandas as pd  # noqa: E402

from colombiainvest.config import DIR_PROCESADOS, DIR_SALIDAS  # noqa: E402
from colombiainvest.ingesta.documentos import (  # noqa: E402
    guardar, parsear_informe_gestion, parsear_proyectos_pdm,
)

# Los documentos viajan dentro del repositorio para que cualquiera pueda
# reproducir el resultado sin depender de rutas locales. Si no estuvieran,
# se busca en la carpeta padre, que es donde los recibio el equipo.
DOCS = Path(__file__).resolve().parents[1] / "datos" / "documentos"
ALTERNA = Path(__file__).resolve().parents[2]
NOMBRE_PROYECTOS = "PROYECTOS DE INVERSION 2024-202 PMD CAJICA IDEAL.pdf"
NOMBRE_INFORME = "INFORME DE GESTIÓN CAJICÁ 2024 FINAL.pdf"


def _ubicar(nombre: str) -> Path | None:
    for base in (DOCS, ALTERNA):
        ruta = base / nombre
        if ruta.exists():
            return ruta
    return None


RUTA_PROYECTOS = _ubicar(NOMBRE_PROYECTOS)
RUTA_INFORME = _ubicar(NOMBRE_INFORME)


def norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", str(s))
    s = "".join(c for c in s if not unicodedata.combining(c))
    return " ".join(s.upper().split()).strip(" .")


# Puente entre el sector del SUIFP y el nombre del sector en el informe.
PUENTE_SECTOR = {
    "AMBIENTE Y DESARROLLO SOSTENIBLE": "AMBIENTE Y DESARROLLO SOSTENIBLE",
    "VIVIENDA, CIUDAD Y TERRITORIO": "VIVIENDA CIUDAD Y TERRITORIO",
    "MINAS Y ENERGIA": "MINAS Y ENERGIA",
    "INCLUSION SOCIAL Y RECONCILIACION": "INCLUSION SOCIAL",
    "EDUCACION": "EDUCACION",
    "SALUD Y PROTECCION SOCIAL": "SALUD Y PROTECCION SOCIAL",
    "CULTURA": "CULTURA",
    "DEPORTE Y RECREACION": "DEPORTE",
    "COMERCIO, INDUSTRIA Y TURISMO": "COMERCIO INDUSTRIA Y TURISMO",
    "TRABAJO": "TRABAJO",
    "CIENCIA, TECNOLOGIA E INNOVACION": "CIENCIA TECNOLOGIA E INNOVACION",
    "AGRICULTURA Y DESARROLLO RURAL": "AGRICULTURA Y DESARROLLO RURAL",
    "TRANSPORTE": "TRANSPORTE",
    "GOBIERNO TERRITORIAL": "GOBIERNO TERRITORIAL",
    "INFORMACION ESTADISTICA": "INFORMACION ESTADISTICA",
    "TECNOLOGIAS DE LA INFORMACION Y LAS COMUNICACIONES":
        "TECNOLOGIA DE LA INFORMACION Y LA COMUNICACION",
    "JUSTICIA Y DEL DERECHO": "JUSTICIA Y DEL DERECHO",
    "ORGANISMOS DE CONTROL": "ORGANISMOS DE CONTROL",
}


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)-7s %(message)s")
    pd.set_option("display.width", 170)
    DIR_SALIDAS.mkdir(parents=True, exist_ok=True)

    faltan = [n for n, r in ((NOMBRE_PROYECTOS, RUTA_PROYECTOS),
                             (NOMBRE_INFORME, RUTA_INFORME)) if r is None]
    if faltan:
        print("No se hallaron los documentos municipales:")
        for n in faltan:
            print("  -", n)
        print(f"Colocarlos en {DOCS} y volver a ejecutar.")
        print("El resto del tablero funciona sin ellos; solo se pierde la "
              "seccion de contexto municipal.")
        return 1

    # ------------------------------------------------------------ proyectos
    proyectos = parsear_proyectos_pdm(RUTA_PROYECTOS)
    guardar(proyectos, DIR_PROCESADOS / "pdm_cajica_proyectos.json")
    pdm = pd.DataFrame(proyectos)

    # ------------------------------------------------------------- informe
    informe = parsear_informe_gestion(RUTA_INFORME)
    guardar(informe, DIR_PROCESADOS / "informe_gestion_cajica_2024.json")
    sectores = pd.DataFrame(informe["sectores"])
    sectores.to_csv(DIR_SALIDAS / "informe_sectores_cajica.csv",
                    index=False, encoding="utf-8-sig")

    print("\n=== INFORME DE GESTION CAJICA 2024, GLOBAL ===")
    for k, v in informe["global"].items():
        print(f"  {k:<32} {v:,.1f}")

    print(f"\n=== AVANCE POR SECTOR ({len(sectores)} sectores) ===")
    print(sectores[["sector_informe", "avance_fisico_sector",
                    "ejecucion_presupuestal_sector", "brecha_sector"]]
          .sort_values("brecha_sector", ascending=False).to_string(index=False))

    # -------------------------------------------------- cobertura del PDM
    df = pd.read_parquet(DIR_PROCESADOS / "proyectos_evaluables.parquet")
    df["en_pdm"] = df["bpin"].isin(set(pdm["bpin"]))
    print("\n=== COBERTURA DEL DOCUMENTO SOBRE EL UNIVERSO EVALUABLE ===")
    print(df.groupby("municipio")["en_pdm"].agg(["count", "sum"]).to_string())
    print(f"  TOTAL cubierto: {int(df['en_pdm'].sum())} de {len(df)} "
          f"({100*df['en_pdm'].mean():.1f} %)")
    print("  Por esta asimetria, estas fuentes NO alimentan el score.")

    # ------------------------------------------- enriquecimiento de ficha
    enriquecido = df.merge(
        pdm[["bpin", "responsable_pdm", "dimension_pdm", "nombre_pdm"]],
        on="bpin", how="left",
    )
    enriquecido.to_parquet(DIR_PROCESADOS / "proyectos_enriquecidos.parquet", index=False)
    print(f"\n  Ficha enriquecida para {int(enriquecido['responsable_pdm'].notna().sum())} proyectos.")
    if pdm["responsable_pdm"].ne("").any():
        print("\n=== DEPENDENCIAS RESPONSABLES (top 8) ===")
        print(pdm[pdm["responsable_pdm"] != ""]["responsable_pdm"]
              .value_counts().head(8).to_string())

    # ------------------------------- contraste SUIFP contra informe municipal
    df["sector_norm"] = df["sector"].map(norm).map(lambda s: PUENTE_SECTOR.get(s, s))
    sectores["sector_norm"] = sectores["sector_informe"].map(norm)
    caj = df[df["municipio"] == "Cajicá"]
    resumen_suifp = (caj.groupby("sector_norm")
                     .agg(n_proyectos=("bpin", "size"),
                          avance_suifp=("avancefisico", "mean"))
                     .reset_index())
    contraste = resumen_suifp.merge(
        sectores[["sector_norm", "avance_fisico_sector",
                  "ejecucion_presupuestal_sector"]],
        on="sector_norm", how="inner",
    )
    contraste["discrepancia"] = (
        contraste["avance_fisico_sector"] - contraste["avance_suifp"]
    ).round(1)
    contraste = contraste.sort_values("discrepancia", ascending=False)
    contraste.to_csv(DIR_SALIDAS / "contraste_suifp_informe.csv",
                     index=False, encoding="utf-8-sig")

    print("\n=== CONTRASTE ENTRE FUENTES (Cajica) ===")
    print("ADVERTENCIA METODOLOGICA: las dos cifras no miden lo mismo.")
    print("  El SUIFP reporta avance ACUMULADO del proyecto sobre su horizonte.")
    print("  El informe reporta avance de la VIGENCIA 2024.")
    print("  El propio informe da ambas para el plan completo, y la cifra")
    print("  comparable con el SUIFP es la del cuatrienio, no la de la vigencia.")
    g = informe["global"]
    v24 = g.get("avance_fisico_vigencia_2024")
    cuat = g.get("avance_fisico_cuatrienio")
    suifp_caj = caj["avancefisico"].mean()
    print(f"\n  Informe, avance vigencia 2024      : {v24:.1f} %" if v24 else "")
    print(f"  Informe, avance del cuatrienio     : {cuat:.1f} %" if cuat else "")
    print(f"  SUIFP, avance medio de Cajica      : {suifp_caj:.1f} %")
    if cuat:
        print(f"  Diferencia contra el cuatrienio    : {suifp_caj - cuat:+.1f} puntos")
        print("  => Contra la base temporal correcta, las fuentes son coherentes.")

    print("\n  Tabla por sector (base temporal distinta, leer como contexto):")
    print(contraste.round(1).to_string(index=False))

    print(f"\nSalidas escritas en {DIR_SALIDAS}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
