# -*- coding: utf-8 -*-
"""Cliente minimo para la API Socrata de datos.gov.co.

Incluye paginacion, reintentos y consulta por lotes de llaves, porque la
clausula IN de SoQL tiene limite practico de longitud de URL.
"""
from __future__ import annotations

import json
import logging
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Dict, Iterable, List, Sequence

log = logging.getLogger(__name__)

TAM_LOTE_LLAVES = 120
AGENTE = "colombiainvest-tesis-ean/0.1"


class ErrorSocrata(RuntimeError):
    pass


class ClienteSocrata:
    def __init__(
        self,
        base_recurso: str = "https://www.datos.gov.co/resource/",
        base_metadatos: str = "https://www.datos.gov.co/api/views/",
        paginacion: int = 5000,
        espera_s: float = 0.4,
        reintentos: int = 3,
        timeout: int = 120,
    ) -> None:
        self.base_recurso = base_recurso
        self.base_metadatos = base_metadatos
        self.paginacion = paginacion
        self.espera_s = espera_s
        self.reintentos = reintentos
        self.timeout = timeout

    # -- bajo nivel ---------------------------------------------------------
    def _pedir(self, url: str) -> Any:
        ultimo: Exception | None = None
        for intento in range(1, self.reintentos + 1):
            try:
                req = urllib.request.Request(url, headers={"User-Agent": AGENTE})
                with urllib.request.urlopen(req, timeout=self.timeout) as r:
                    return json.loads(r.read().decode("utf-8"))
            except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as e:
                ultimo = e
                espera = self.espera_s * (2 ** (intento - 1))
                log.warning("Intento %d/%d fallo (%s). Reintento en %.1fs",
                            intento, self.reintentos, e, espera)
                time.sleep(espera)
        raise ErrorSocrata(f"No se pudo consultar {url}: {ultimo}")

    def consultar(self, recurso: str, **params: Any) -> List[Dict[str, Any]]:
        """Una consulta SoQL. Los parametros van con el prefijo $ de Socrata."""
        url = self.base_recurso + recurso + ".json?" + urllib.parse.urlencode(params)
        datos = self._pedir(url)
        if isinstance(datos, dict) and datos.get("error"):
            raise ErrorSocrata(f"{recurso}: {datos.get('message')}")
        return datos

    def metadatos(self, recurso: str) -> Dict[str, Any]:
        return self._pedir(self.base_metadatos + recurso + ".json")

    def campos(self, recurso: str) -> List[Dict[str, str]]:
        """Nombres de campo REALES del dataset. Nunca asumirlos, verificarlos."""
        meta = self.metadatos(recurso)
        return [
            {"campo": c["fieldName"], "tipo": c["dataTypeName"], "etiqueta": c.get("name", "")}
            for c in meta["columns"]
        ]

    # -- alto nivel ---------------------------------------------------------
    def descargar(
        self,
        recurso: str,
        where: str | None = None,
        select: str | None = None,
        order: str | None = None,
    ) -> List[Dict[str, Any]]:
        """Descarga completa con paginacion por offset."""
        filas: List[Dict[str, Any]] = []
        offset = 0
        while True:
            params: Dict[str, Any] = {"$limit": self.paginacion, "$offset": offset}
            if where:
                params["$where"] = where
            if select:
                params["$select"] = select
            if order:
                params["$order"] = order
            lote = self.consultar(recurso, **params)
            filas.extend(lote)
            log.info("%s: lote offset=%d filas=%d acumulado=%d",
                     recurso, offset, len(lote), len(filas))
            if len(lote) < self.paginacion:
                break
            offset += self.paginacion
            time.sleep(self.espera_s)
        return filas

    def descargar_por_llaves(
        self,
        recurso: str,
        campo_llave: str,
        llaves: Sequence[str],
        select: str | None = None,
        tam_lote: int = TAM_LOTE_LLAVES,
    ) -> List[Dict[str, Any]]:
        """Consulta filtrando por una lista de llaves, en lotes."""
        llaves = list(dict.fromkeys(llaves))
        filas: List[Dict[str, Any]] = []
        for i in range(0, len(llaves), tam_lote):
            trozo = llaves[i : i + tam_lote]
            lista = ",".join("'" + str(v).replace("'", "''") + "'" for v in trozo)
            where = f"{campo_llave} in({lista})"
            params: Dict[str, Any] = {"$where": where, "$limit": 50000}
            if select:
                params["$select"] = select
            filas.extend(self.consultar(recurso, **params))
            time.sleep(self.espera_s)
        log.info("%s: %d filas para %d llaves", recurso, len(filas), len(llaves))
        return filas


def lista_soql(valores: Iterable[str]) -> str:
    """Construye un literal de lista para la clausula IN de SoQL."""
    return ",".join("'" + str(v).replace("'", "''") + "'" for v in valores)
