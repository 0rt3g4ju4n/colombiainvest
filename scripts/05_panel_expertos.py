# -*- coding: utf-8 -*-
"""Paso 5: pesos del panel de expertos por proceso analitico jerarquico.

Uso:
    python scripts/05_panel_expertos.py --plantilla
        Crea en datos/entrevistas/ las plantillas para registrar respuestas.

    python scripts/05_panel_expertos.py
        Lee datos/entrevistas/respuestas_ahp.csv (y, si existe,
        relevancia_variables.csv), reporta consistencia por experto, pesos
        agregados y concordancia, y escribe config/pesos_panel.yaml.

    python scripts/05_panel_expertos.py --experto E03
        Revisa solo un experto. Util DURANTE la entrevista: si su razon de
        consistencia supera 0,10, indica que comparacion volver a preguntar.

El archivo de respuestas lleva un codigo por experto (E01, E02, ...), nunca
el nombre. La correspondencia entre codigo y nombre se guarda fuera del
repositorio.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pandas as pd  # noqa: E402
import yaml  # noqa: E402

from colombiainvest.config import (  # noqa: E402
    DIMENSIONES, DIR_CONFIG, DIR_SALIDAS, RAIZ, RUTA_PESOS_PANEL, cargar_modelo,
)
from colombiainvest.modelo import ahp  # noqa: E402

DIR_ENTREVISTAS = RAIZ / "datos" / "entrevistas"
RESPUESTAS = DIR_ENTREVISTAS / "respuestas_ahp.csv"
RELEVANCIA = DIR_ENTREVISTAS / "relevancia_variables.csv"
VINCULACION = DIR_ENTREVISTAS / "vinculacion_tipos.csv"
UMBRAL_CR = 0.10


def escribir_plantillas() -> None:
    DIR_ENTREVISTAS.mkdir(parents=True, exist_ok=True)
    cfg = cargar_modelo()
    with open(DIR_CONFIG / "diccionario_variables.yaml", encoding="utf-8") as f:
        dicc = yaml.safe_load(f)

    plantilla = ahp.plantilla_respuestas(DIMENSIONES)
    plantilla.insert(0, "comparacion", range(1, len(plantilla) + 1))
    plantilla.to_csv(DIR_ENTREVISTAS / "plantilla_respuestas_ahp.csv", sep=";",
                     index=False, encoding="utf-8-sig")

    # Solo las variables que entran al score: si los datos ya existen, se
    # excluyen las que la regla de faltantes descarta en el corte actual.
    descartadas = set()
    evaluables = RAIZ / "datos" / "procesados" / "proyectos_evaluables.parquet"
    if evaluables.exists():
        from colombiainvest.modelo.score import evaluar_faltantes
        descartadas = set(evaluar_faltantes(pd.read_parquet(evaluables), cfg)["descartadas"])
    filas = [{"experto": "E01", "dimension": dim, "variable": var,
              "nombre": dicc["variables"][var]["nombre"], "relevancia": ""}
             for dim in DIMENSIONES for var in cfg.variables_activas(dim)
             if var not in descartadas]
    pd.DataFrame(filas).to_csv(DIR_ENTREVISTAS / "plantilla_relevancia_variables.csv",
                               sep=";", index=False, encoding="utf-8-sig")

    tipos = [k for k in cfg.mapeos["vinculacion_privada"] if not k.startswith("_")]
    pd.DataFrame([{"experto": "E01", "tipo_intervencion": k, "viabilidad": ""} for k in tipos]).to_csv(
        DIR_ENTREVISTAS / "plantilla_vinculacion_tipos.csv", sep=";", index=False,
        encoding="utf-8-sig")
    print(f"Plantillas escritas en {DIR_ENTREVISTAS}")
    print("  Copie plantilla_respuestas_ahp.csv como respuestas_ahp.csv y agregue")
    print("  diez filas por experto. preferida: A, B o = ; intensidad: 1 a 9.")


def imprimir_expertos(tabla: pd.DataFrame) -> None:
    cols = ["experto", "perfil", "fecha"] + DIMENSIONES + ["cr", "consistente"]
    print(tabla[cols].to_string(index=False))
    for _, fila in tabla[~tabla["consistente"]].iterrows():
        r = fila["revisar"]
        print(f"\n  {fila['experto']}: razon de consistencia {fila['cr']:.3f} "
              f"(debe ser menor que {UMBRAL_CR}).")
        print(f"    Volver a preguntar: {r['dimension_a']} frente a {r['dimension_b']}.")
        print(f"    Respondio {r['juicio_actual']}; lo coherente con sus demas "
              f"respuestas seria {r['valor_coherente']}.")
        print("    El experto decide si lo cambia. No se corrige sin consultarlo.")


def main() -> int:
    p = argparse.ArgumentParser(description="Pesos del panel de expertos (AHP)")
    p.add_argument("--plantilla", action="store_true", help="crea las plantillas y termina")
    p.add_argument("--respuestas", type=Path, default=RESPUESTAS)
    p.add_argument("--experto", help="revisa solo este experto")
    p.add_argument("--no-escribir", action="store_true",
                   help="no escribe config/pesos_panel.yaml")
    args = p.parse_args()

    if args.plantilla:
        escribir_plantillas()
        return 0

    if not args.respuestas.exists():
        print(f"No existe {args.respuestas}.")
        print("Cree las plantillas con: python scripts/05_panel_expertos.py --plantilla")
        return 1

    respuestas = ahp.leer_respuestas(args.respuestas, DIMENSIONES)
    if args.experto:
        respuestas = respuestas[respuestas["experto"] == args.experto]
        if respuestas.empty:
            print(f"No hay respuestas del experto {args.experto}")
            return 1

    res = ahp.resultado_panel(respuestas, DIMENSIONES, umbral_cr=UMBRAL_CR)
    tabla = res["por_experto"]
    print("\n=== PESOS Y CONSISTENCIA POR EXPERTO ===")
    imprimir_expertos(tabla)
    if args.experto:
        return 0

    DIR_SALIDAS.mkdir(parents=True, exist_ok=True)
    tabla.drop(columns=["revisar"], errors="ignore").to_csv(
        DIR_SALIDAS / "panel_por_experto.csv", index=False, encoding="utf-8-sig")

    if not res["agregado"]:
        print("\nNingun experto tiene razon de consistencia aceptable. No hay pesos del panel.")
        return 1

    agr = res["agregado"]
    print(f"\n=== PESOS DEL PANEL ({agr['n_expertos']} expertos consistentes de {len(tabla)}) ===")
    for d in DIMENSIONES:
        print(f"  {d:<24} {agr['pesos'][d]:.4f}")
    print(f"  razon de consistencia de la matriz agregada: {agr['cr']:.4f}")

    conc = res["concordancia"]
    if conc:
        print(f"\n=== CONCORDANCIA ENTRE EXPERTOS ===")
        print(f"  W de Kendall {conc['w_kendall']:.3f} | chi cuadrado {conc['chi2']:.2f} "
              f"con {conc['gl']} gl, p = {conc['p_chi2']:.4f} | p por permutacion "
              f"{conc['p_permutacion']:.4f}")
        if conc["evaluadores"] < 3:
            print("  ADVERTENCIA: con menos de tres expertos la W no es interpretable.")
    if res["concentracion_sugerida"]:
        print(f"\n  Concentracion de Dirichlet coherente con la dispersion del panel: "
              f"{res['concentracion_sugerida']:.0f} (montecarlo.concentracion en pesos.yaml)")

    relevancia = None
    if RELEVANCIA.exists():
        calif = pd.read_csv(RELEVANCIA, sep=None, engine="python", encoding="utf-8-sig")
        por_var, resumen_cvi = ahp.indice_validez_contenido(calif)
        por_var.to_csv(DIR_SALIDAS / "panel_validez_contenido.csv", index=False,
                       encoding="utf-8-sig")
        relevancia = resumen_cvi
        print("\n=== VALIDEZ DE CONTENIDO DE LAS VARIABLES ===")
        print(por_var.to_string(index=False))
        print(f"  S-CVI/Ave {resumen_cvi['s_cvi_ave']:.3f} | umbral I-CVI "
              f"{resumen_cvi['umbral_i_cvi']} con {resumen_cvi['n_expertos']} expertos")

    vinculacion = None
    if VINCULACION.exists():
        # Parte C del instrumento: viabilidad de vincular capital privado por
        # tipo de intervencion, de 1 (nula) a 4 (alta). La mediana del panel
        # llevada a [0, 1] es la escala sugerida para mapeos.vinculacion_privada.
        v = pd.read_csv(VINCULACION, sep=None, engine="python", encoding="utf-8-sig")
        v["viabilidad"] = pd.to_numeric(v["viabilidad"], errors="coerce")
        med = v.dropna(subset=["viabilidad"]).groupby("tipo_intervencion")["viabilidad"].median()
        actual = cargar_modelo().mapeos["vinculacion_privada"]
        tabla_v = pd.DataFrame({"mediana_panel": med, "sugerido": ((med - 1) / 3).round(2),
                                "vigente": [actual.get(k) for k in med.index]})
        tabla_v.to_csv(DIR_SALIDAS / "panel_vinculacion_tipos.csv", encoding="utf-8-sig")
        vinculacion = tabla_v["sugerido"].to_dict()
        print("\n=== VINCULACION DE CAPITAL PRIVADO POR TIPO (escala sugerida por el panel) ===")
        print(tabla_v.to_string())
        print("  Si el grupo la adopta, copie 'sugerido' en mapeos.vinculacion_privada de pesos.yaml.")

    resultado = {
        "fecha": date.today().isoformat(),
        "expertos": int(len(tabla)),
        "consistentes": res["consistentes"],
        "pesos": agr["pesos"], "cr_agregado": agr["cr"],
        "concordancia": conc, "concentracion_sugerida": res["concentracion_sugerida"],
        "validez_contenido": relevancia,
        "vinculacion_sugerida": vinculacion,
    }
    with open(DIR_SALIDAS / "panel_resultado.json", "w", encoding="utf-8") as f:
        json.dump(resultado, f, ensure_ascii=False, indent=2, default=float)

    if not args.no_escribir:
        panel = {
            "descripcion": (f"Pesos del panel de expertos por AHP, {agr['n_expertos']} "
                            f"expertos consistentes, {date.today().isoformat()}"),
            "esquema": {d: round(agr["pesos"][d], 4) for d in DIMENSIONES},
        }
        # El redondeo puede dejar la suma en 0,9999: se ajusta la mayor.
        dif = round(1 - sum(panel["esquema"].values()), 4)
        mayor = max(panel["esquema"], key=panel["esquema"].get)
        panel["esquema"][mayor] = round(panel["esquema"][mayor] + dif, 4)
        with open(RUTA_PESOS_PANEL, "w", encoding="utf-8") as f:
            f.write("# Generado por scripts/05_panel_expertos.py. No editar a mano.\n")
            yaml.safe_dump(panel, f, allow_unicode=True, sort_keys=False)
        print(f"\nEsquema 'panel_expertos' escrito en {RUTA_PESOS_PANEL}.")
        print("Aparece como esquema alternativo. Para volverlo el esquema base,")
        print("copie sus pesos a esquema_base en config/pesos.yaml (decision del grupo).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
