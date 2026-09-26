# -*- coding: utf-8 -*-
"""Paso 1: descarga de fuentes oficiales.

Uso:
    python scripts/01_ingesta.py            # solo SUIFP (rapido)
    python scripts/01_ingesta.py --secop    # incluye SECOP (16k filas, lento)
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from colombiainvest.config import DIR_CRUDOS, cargar_fuentes  # noqa: E402
from colombiainvest.ingesta.dnp import ingesta_completa, ingesta_secop  # noqa: E402


def main() -> int:
    p = argparse.ArgumentParser(description="Ingesta de fuentes oficiales")
    p.add_argument("--secop", action="store_true", help="descargar tambien SECOP II")
    args = p.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)-7s %(message)s",
        datefmt="%H:%M:%S",
    )

    cfg = cargar_fuentes()
    print("Municipios del caso:", ", ".join(m["nombre_fuente"] for m in cfg.municipios))

    resumen = ingesta_completa(cfg)
    print("\n=== RESUMEN DE INGESTA SUIFP ===")
    for k, v in resumen.items():
        print(f"  {k:<16} {v:>8,} registros")

    if args.secop:
        n = ingesta_secop(cfg)
        print(f"  {'secop':<16} {n:>8,} contratos")

    # Fecha de corte: la direccion exige que cada calificacion exponga la
    # fecha de los datos que la producen. Se registra al descargar.
    corte = {"fecha_corte": datetime.now().strftime("%Y-%m-%d"),
             "fuente": "SUIFP, DNP, via datos.gov.co", "registros": resumen}
    with open(DIR_CRUDOS / "corte.json", "w", encoding="utf-8") as f:
        json.dump(corte, f, ensure_ascii=False, indent=2)
    print(f"\n  Fecha de corte registrada: {corte['fecha_corte']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
