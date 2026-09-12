# -*- coding: utf-8 -*-
"""Ingesta del SUIFP del DNP para los municipios del caso de aplicacion.

Unidad de analisis: el proyecto BPIN.
El universo se define por entidad responsable, no por localizacion, para
quedarnos con proyectos DEL municipio y no con proyectos nacionales
ejecutados EN el municipio.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, List

from ..config import DIR_CRUDOS, ConfigFuentes
from .socrata import ClienteSocrata, lista_soql

log = logging.getLogger(__name__)


def cliente_desde_config(cfg: ConfigFuentes) -> ClienteSocrata:
    s = cfg.socrata
    return ClienteSocrata(
        base_recurso=s["base_recurso"],
        base_metadatos=s["base_metadatos"],
        paginacion=int(s["paginacion"]),
        espera_s=float(s["espera_entre_lotes_s"]),
        reintentos=int(s["reintentos"]),
    )


def universo_bpin(cli: ClienteSocrata, cfg: ConfigFuentes) -> List[Dict[str, Any]]:
    """Proyectos cuya entidad responsable es una de las alcaldias del caso."""
    ds = cfg.dataset("localizacion")
    where = f"entidadresponsable in({lista_soql(cfg.entidades_suifp)})"
    filas = cli.descargar(ds["id"], where=where, order="bpin")
    log.info("Universo BPIN: %d registros de localizacion", len(filas))
    return filas


def ingesta_completa(cfg: ConfigFuentes, dir_salida: Path | None = None) -> Dict[str, int]:
    """Descarga todas las tablas del SUIFP para el universo y las guarda crudas."""
    dir_salida = dir_salida or DIR_CRUDOS
    dir_salida.mkdir(parents=True, exist_ok=True)
    cli = cliente_desde_config(cfg)
    resumen: Dict[str, int] = {}

    localizacion = universo_bpin(cli, cfg)
    _guardar(dir_salida / "localizacion.json", localizacion)
    resumen["localizacion"] = len(localizacion)

    bpins = sorted({f["bpin"] for f in localizacion if f.get("bpin")})
    log.info("BPIN unicos en el universo: %d", len(bpins))
    _guardar(dir_salida / "universo_bpin.json", bpins)
    resumen["bpin_unicos"] = len(bpins)

    for clave in ("seguimiento", "ejecucion", "datos_basicos", "beneficiarios"):
        ds = cfg.dataset(clave)
        try:
            filas = cli.descargar_por_llaves(ds["id"], ds["llave"], bpins)
        except Exception as e:  # una tabla caida no debe tumbar la ingesta
            log.error("Fallo la descarga de '%s' (%s): %s", clave, ds["id"], e)
            filas = []
        _guardar(dir_salida / f"{clave}.json", filas)
        resumen[clave] = len(filas)

    return resumen


def ingesta_secop(cfg: ConfigFuentes, dir_salida: Path | None = None) -> int:
    """Evidencia contractual complementaria. NO es la unidad de analisis.

    Verificado el 2026-09-11: SECOP II Contratos no expone BPIN y la tabla
    DNP-ProyectosContratos no cubre estos municipios. El unico cruce posible
    es por similitud de texto, con tasa de emparejamiento reportada.
    """
    dir_salida = dir_salida or DIR_CRUDOS
    dir_salida.mkdir(parents=True, exist_ok=True)
    cli = cliente_desde_config(cfg)
    s = cfg.secop
    where = (
        f"departamento='{s['filtro_departamento']}' "
        f"AND ciudad in({lista_soql(cfg.nombres_fuente)}) "
        f"AND nombre_entidad not in({lista_soql(s['entidades_excluidas'])})"
    )
    filas = cli.descargar(s["id"], where=where, order="id_contrato")
    _guardar(dir_salida / "secop_contratos.json", filas)
    log.info("SECOP: %d contratos municipales", len(filas))
    return len(filas)


def _guardar(ruta: Path, obj: Any) -> None:
    with open(ruta, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False)
    log.info("Guardado %s", ruta.name)
