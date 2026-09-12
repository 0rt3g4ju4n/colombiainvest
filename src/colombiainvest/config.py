# -*- coding: utf-8 -*-
"""Carga de configuracion. Ningun peso ni parametro del modelo vive en codigo."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List

import yaml

RAIZ = Path(__file__).resolve().parents[2]
DIR_CONFIG = RAIZ / "config"
DIR_CRUDOS = RAIZ / "datos" / "crudos"
DIR_PROCESADOS = RAIZ / "datos" / "procesados"
DIR_SALIDAS = RAIZ / "salidas"

DIMENSIONES: List[str] = [
    "viabilidad_financiera",
    "madurez_ejecucion",
    "impacto_social",
    "gobernanza",
    "atractivo_inversor",
]

TOLERANCIA_SUMA = 1e-6


def _leer_yaml(ruta: Path) -> Dict[str, Any]:
    with open(ruta, encoding="utf-8") as f:
        return yaml.safe_load(f)


@dataclass
class ConfigFuentes:
    bruto: Dict[str, Any] = field(repr=False)

    @property
    def socrata(self) -> Dict[str, Any]:
        return self.bruto["socrata"]

    @property
    def municipios(self) -> List[Dict[str, str]]:
        return self.bruto["territorio"]["municipios"]

    @property
    def entidades_suifp(self) -> List[str]:
        return [m["entidad_suifp"] for m in self.municipios]

    @property
    def nombres_fuente(self) -> List[str]:
        return [m["nombre_fuente"] for m in self.municipios]

    def dataset(self, clave: str) -> Dict[str, Any]:
        return self.bruto["datasets"][clave]

    @property
    def secop(self) -> Dict[str, Any]:
        return self.bruto["secop"]


@dataclass
class ConfigModelo:
    """Parametros del modelo. Todo configurable, nada incrustado."""

    bruto: Dict[str, Any] = field(repr=False)

    def __post_init__(self) -> None:
        self.validar()

    # -- pesos entre dimensiones -------------------------------------------
    @property
    def esquema_base(self) -> Dict[str, float]:
        return dict(self.bruto["esquema_base"])

    def esquema(self, nombre: str = "esquema_base") -> Dict[str, float]:
        """Devuelve un esquema de ponderacion por nombre."""
        if nombre in ("esquema_base", "base"):
            return self.esquema_base
        alt = self.bruto["esquemas_alternativos"]
        if nombre not in alt:
            disponibles = ["esquema_base"] + list(alt)
            raise KeyError(f"Esquema '{nombre}' no existe. Disponibles: {disponibles}")
        return {k: v for k, v in alt[nombre].items() if k != "descripcion"}

    @property
    def esquemas_disponibles(self) -> List[str]:
        return ["esquema_base"] + list(self.bruto["esquemas_alternativos"])

    def descripcion_esquema(self, nombre: str) -> str:
        if nombre in ("esquema_base", "base"):
            return self.bruto.get("origen_pesos", "esquema base")
        return self.bruto["esquemas_alternativos"][nombre].get("descripcion", "")

    # -- perfiles de inversionista -----------------------------------------
    @property
    def perfiles_habilitados(self) -> bool:
        return bool(self.bruto["perfiles_inversionista"]["habilitado"])

    def esquema_de_perfil(self, perfil: str) -> Dict[str, float]:
        perfiles = self.bruto["perfiles_inversionista"]["perfiles"]
        if perfil not in perfiles:
            raise KeyError(f"Perfil '{perfil}' no existe. Disponibles: {list(perfiles)}")
        return self.esquema(perfiles[perfil]["usa_esquema"])

    # -- pesos intra dimension ---------------------------------------------
    def variables(self, dimension: str) -> Dict[str, Dict[str, Any]]:
        return self.bruto["variables"][dimension]

    def variables_activas(self, dimension: str) -> Dict[str, Dict[str, Any]]:
        """Variables con peso mayor a cero. Permite apagar una sin borrarla."""
        return {k: v for k, v in self.variables(dimension).items() if v["peso"] > 0}

    # -- otros --------------------------------------------------------------
    @property
    def normalizacion(self) -> Dict[str, Any]:
        return self.bruto["normalizacion"]

    @property
    def mapeos(self) -> Dict[str, Any]:
        return self.bruto["mapeos"]

    @property
    def poblacion(self) -> Dict[str, int]:
        return {k: v for k, v in self.bruto["poblacion"].items() if not k.startswith("_")}

    @property
    def semilla(self) -> int:
        return int(self.bruto.get("semilla_aleatoria", 42))

    # -- validacion ---------------------------------------------------------
    def validar(self) -> None:
        """Falla temprano si la configuracion es incoherente."""
        for nombre in self.esquemas_disponibles:
            esq = self.esquema(nombre)
            faltan = set(DIMENSIONES) - set(esq)
            if faltan:
                raise ValueError(f"Esquema '{nombre}' no cubre las dimensiones {faltan}")
            suma = sum(esq.values())
            if abs(suma - 1.0) > TOLERANCIA_SUMA:
                raise ValueError(f"Esquema '{nombre}' suma {suma:.6f}, debe sumar 1.0")
            for dim, peso in esq.items():
                if peso < 0:
                    raise ValueError(f"Esquema '{nombre}': peso negativo en {dim}")

        for dim in DIMENSIONES:
            if dim not in self.bruto["variables"]:
                raise ValueError(f"Faltan variables para la dimension '{dim}'")
            suma = sum(v["peso"] for v in self.variables(dim).values())
            if abs(suma - 1.0) > TOLERANCIA_SUMA:
                raise ValueError(f"Pesos intra '{dim}' suman {suma:.6f}, deben sumar 1.0")
            for nombre_var, spec in self.variables(dim).items():
                if spec["sentido"] not in (1, -1):
                    raise ValueError(f"'{dim}.{nombre_var}': sentido debe ser 1 o -1")

        metodo = self.normalizacion["metodo"]
        validos = {"minmax", "zscore", "robusta", "rango_percentil"}
        if metodo not in validos:
            raise ValueError(f"Metodo de normalizacion '{metodo}' invalido. Use {validos}")


def cargar_fuentes(ruta: Path | None = None) -> ConfigFuentes:
    return ConfigFuentes(_leer_yaml(ruta or DIR_CONFIG / "fuentes.yaml"))


def cargar_modelo(ruta: Path | None = None) -> ConfigModelo:
    return ConfigModelo(_leer_yaml(ruta or DIR_CONFIG / "pesos.yaml"))
