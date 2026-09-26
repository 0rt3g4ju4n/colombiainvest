# -*- coding: utf-8 -*-
"""Construccion del dataset de proyectos y calculo de variables por dimension.

Unidad de analisis: el proyecto BPIN.
Toda variable declara de que fuente sale, para poder sustentar trazabilidad.

Nota sobre fugas de informacion: este modulo NO construye ningun modelo
predictivo, es un score compuesto. No hay variable objetivo ni particion
temporal, de modo que no aplica el riesgo de leakage. Si mas adelante se
agrega el componente supervisado de retraso o sobrecosto, ese modulo debe
restringirse a variables conocidas al momento de la decision.
"""
from __future__ import annotations

import json
import logging
import unicodedata
from pathlib import Path
from typing import Any, Dict, List

import numpy as np
import pandas as pd

from ..config import DIR_CRUDOS, ConfigModelo

log = logging.getLogger(__name__)

# Campos de la ficha usados para medir completitud (dimension Gobernanza).
# El conjunto se amplio tras verificar que con nueve campos la variable era
# casi constante (minimo 0,889). Se incluyen los campos financieros, que son
# los que realmente distinguen una ficha bien diligenciada de una incompleta.
CAMPOS_FICHA = [
    "nombreproyecto",
    "objetivogeneral",
    "estadoproyecto",
    "subestadoproyecto",
    "horizonte",
    "sector",
    "programapresupuestal",
    "plandesarrollonacional",
    "tipoproyecto",
    "totalbeneficiario",
    "valortotalproyecto",
    "valorvigenteproyecto",
    "valorobligacionproyecto",
    "valorpagoproyecto",
]

TABLAS_CRUCE = ["localizacion", "seguimiento", "ejecucion", "datos_basicos"]


# ---------------------------------------------------------------------------
# utilidades
# ---------------------------------------------------------------------------
def sin_tildes(texto: Any) -> str:
    """Normaliza texto para que los mapeos no dependan de la acentuacion."""
    if texto is None or (isinstance(texto, float) and np.isnan(texto)):
        return ""
    s = unicodedata.normalize("NFKD", str(texto))
    s = "".join(c for c in s if not unicodedata.combining(c))
    return " ".join(s.replace("\xa0", " ").split()).strip()


def mapear(valor: Any, tabla: Dict[str, float]) -> float:
    """Busca un valor en un mapeo de juicio experto, ignorando tildes y caja."""
    clave = sin_tildes(valor).lower()
    indice = {sin_tildes(k).lower(): v for k, v in tabla.items() if k != "_defecto"}
    return float(indice.get(clave, tabla.get("_defecto", 0.0)))


def _num(valor: Any) -> float:
    try:
        x = float(valor)
        return 0.0 if not np.isfinite(x) else x
    except (TypeError, ValueError):
        return 0.0


def _div(a: float, b: float, defecto: float = 0.0) -> float:
    return a / b if b not in (0, 0.0) else defecto


# Tipo de intervencion derivado del verbo que encabeza el nombre del proyecto.
# Es la unica senal de texto con distribucion util: el campo objetivogeneral
# viene truncado a 249 caracteres, sin mencion de ODS y con solo 18 de 491
# objetivos que contienen alguna cifra.
#
# Se compara por RAIZ de la palabra y no por palabra exacta, porque el SUIFP
# trae tildes corruptas ("CONSTRUCCIN", "ACTUALIZACIN"): con la palabra
# exacta, 68 proyectos quedaban como "Otro". Desde la version 0.2.0 alimenta
# la variable 'vinculacion_privada' del atractivo inversor.
TIPO_INTERVENCION = {
    "Inversion en capital": ("CONSTRUC", "AMPLIAC", "ADECUAC", "ADQUISIC", "DOTAC",
                             "REPOSIC", "INSTALAC"),
    "Mejoramiento": ("MEJORAM", "OPTIMIZ", "ACTUALIZ", "MODERNIZ", "INCREMENT", "DEMARCAC"),
    "Mantenimiento": ("MANTENIM", "CONSERVAC", "PROTECC", "RESTAURAC", "RECUPERAC"),
    "Fortalecimiento institucional": ("FORTALEC", "APOYO", "DESARROLL", "GENERAC",
                                      "CONSOLIDAC", "ADMINISTRAC", "CONTROL", "PRODUCC",
                                      "CONFORMAC", "CONTRIBUC", "INCORPORAC"),
    "Implementacion de programa": ("IMPLEMENT", "PRESTAC", "SERVICIO", "ASISTENC", "PREVENC",
                                   "DIFUS", "FORMAC", "IMPLANTAC", "SUBSIDIO", "TRANSFORMAC",
                                   "INNOVAC", "APROVECHAM", "COMPROMISO"),
    "Preinversion": ("ESTUDIO", "FORMULAC", "DIAGNOST", "DISENO", "REVISION", "IDENTIFICAC"),
}

# Verbos iniciales que no deciden solos: "Diseno y construccion de
# alcantarillado" es una obra y "Administracion, operacion, reposicion y
# expansion del alumbrado publico" incluye obra. Si el nombre menciona obra
# fisica, se clasifica como inversion en capital.
VERBOS_AMBIGUOS = ("DISENO", "APORTES", "ADMINISTRAC", "INCREMENT")
RAICES_OBRA = ("CONSTRUC", "AMPLIAC", "REPOSIC", "EXPANSI", "DOTAC")


def clasificar_intervencion(nombre: Any) -> str:
    """Clasifica el proyecto por el verbo que encabeza su nombre.

    Atributo descriptivo y, desde la version 0.2.0, insumo de la variable
    'vinculacion_privada' (atractivo inversor), cuyo mapeo por tipo vive en
    pesos.yaml y lo valida el panel de expertos.
    """
    palabras = sin_tildes(nombre).upper().split()
    if not palabras:
        return "Sin clasificar"
    primera = palabras[0]
    if primera.startswith(VERBOS_AMBIGUOS) and any(
            p.startswith(RAICES_OBRA) for p in palabras[1:]):
        return "Inversion en capital"
    for tipo, raices in TIPO_INTERVENCION.items():
        if primera.startswith(raices):
            return tipo
    return "Otro"


def _anios_horizonte(valor: Any) -> float:
    """Extrae la duracion en anios de un horizonte con formato '2020-2024'."""
    texto = sin_tildes(valor)
    partes = [p for p in texto.replace("/", "-").split("-") if p.strip().isdigit()]
    if len(partes) < 2:
        return 0.0
    inicio, fin = int(partes[0]), int(partes[-1])
    if not (1990 < inicio <= fin < 2100):
        return 0.0
    return float(fin - inicio + 1)


def cargar_crudos(dir_crudos: Path | None = None) -> Dict[str, List[Dict[str, Any]]]:
    dir_crudos = dir_crudos or DIR_CRUDOS
    crudos: Dict[str, List[Dict[str, Any]]] = {}
    for nombre in TABLAS_CRUCE + ["beneficiarios"]:
        ruta = dir_crudos / f"{nombre}.json"
        if ruta.exists():
            with open(ruta, encoding="utf-8") as f:
                crudos[nombre] = json.load(f)
        else:
            log.warning("No existe %s, se continua sin esa tabla", ruta.name)
            crudos[nombre] = []
    return crudos


# ---------------------------------------------------------------------------
# agregaciones por proyecto
# ---------------------------------------------------------------------------
def _agregar_ejecucion(filas: List[Dict[str, Any]]) -> pd.DataFrame:
    """Colapsa ejecucion (bpin x vigencia x fuente) a una fila por bpin."""
    if not filas:
        return pd.DataFrame(columns=["bpin"])
    df = pd.DataFrame(filas)
    for c in ("valorvigente", "valorcomprometido", "valorobligado", "valorpagado"):
        df[c] = df.get(c, 0).map(_num)
    df["vigencia"] = pd.to_numeric(df.get("vigencia"), errors="coerce")
    df["es_externa"] = ~df["fuentefinanciacion"].map(sin_tildes).str.lower().str.contains(
        "propios de las entidades territoriales", na=False
    )

    filas_out = []
    for bpin, g in df.groupby("bpin"):
        vigente = g["valorvigente"].sum()
        obligado = g["valorobligado"].sum()
        pagado = g["valorpagado"].sum()
        por_vigencia = g.groupby("vigencia")["valorvigente"].sum()
        apropiadas = por_vigencia[por_vigencia > 0]
        cv = (
            float(apropiadas.std(ddof=0) / apropiadas.mean())
            if len(apropiadas) > 1 and apropiadas.mean() > 0
            else 0.0
        )
        externo = g.loc[g["es_externa"], "valorvigente"].sum()
        filas_out.append(
            {
                "bpin": bpin,
                "valor_vigente_total": vigente,
                "valor_obligado_total": obligado,
                "valor_pagado_total": pagado,
                "n_vigencias_apropiadas": int(len(apropiadas)),
                "n_vigencias_ejecutadas": int((g.groupby("vigencia")["valorobligado"].sum() > 0).sum()),
                "n_fuentes": int(g["fuentefinanciacion"].nunique()),
                "cv_apropiacion": cv,
                "valor_fuente_externa": externo,
                "municipio_ejec": g["municipio"].mode().iat[0] if "municipio" in g and not g["municipio"].isna().all() else None,
            }
        )
    return pd.DataFrame(filas_out)


def construir_tabla_proyectos(
    crudos: Dict[str, List[Dict[str, Any]]], cfg: ConfigModelo
) -> pd.DataFrame:
    """Une las tablas del SUIFP en una fila por proyecto BPIN."""
    loc = pd.DataFrame(crudos["localizacion"])
    seg = pd.DataFrame(crudos["seguimiento"])
    db = pd.DataFrame(crudos["datos_basicos"])
    eje = _agregar_ejecucion(crudos["ejecucion"])

    base = loc.drop_duplicates(subset="bpin")[
        ["bpin", "nombreproyecto", "sector", "entidadresponsable",
         "codigomunicipio", "municipio", "codigoentidadresponsable"]
    ].copy()

    if not seg.empty:
        seg = seg.drop_duplicates(subset="bpin")
        base = base.merge(
            seg[["bpin", "avancefisico", "avancefinanciero", "horizonte"]],
            on="bpin", how="left",
        )
    if not db.empty:
        db = db.drop_duplicates(subset="bpin")
        cols = [c for c in ["bpin", "objetivogeneral", "estadoproyecto", "subestadoproyecto",
                            "programapresupuestal", "plandesarrollonacional", "tipoproyecto",
                            "valortotalproyecto", "valorvigenteproyecto",
                            "valorobligacionproyecto", "valorpagoproyecto",
                            "totalbeneficiario"] if c in db.columns]
        base = base.merge(db[cols], on="bpin", how="left")
    if not eje.empty:
        base = base.merge(eje, on="bpin", how="left")

    # presencia en fuentes cruzadas, insumo de Gobernanza
    presentes = {}
    for nombre in TABLAS_CRUCE:
        ids = {r.get("bpin") for r in crudos.get(nombre, []) if r.get("bpin")}
        presentes[nombre] = ids
    base["presencia_cruzada_n"] = base["bpin"].map(
        lambda b: sum(1 for s in presentes.values() if b in s)
    )

    # completitud de ficha, insumo de Gobernanza
    idx_db = {r["bpin"]: r for r in crudos.get("datos_basicos", []) if r.get("bpin")}

    def _completitud(bpin: str) -> float:
        reg = idx_db.get(bpin)
        if not reg:
            return 0.0
        llenos = 0
        for c in CAMPOS_FICHA:
            v = reg.get(c)
            if v is None or str(v).strip() == "":
                continue
            try:
                if float(v) == 0.0:
                    continue
            except (TypeError, ValueError):
                pass
            llenos += 1
        return llenos / len(CAMPOS_FICHA)

    base["completitud_ficha_v"] = base["bpin"].map(_completitud)

    base["municipio"] = base["municipio"].fillna(base.get("municipio_ejec"))
    base = _asignar_municipio_por_entidad(base)
    log.info("Tabla de proyectos: %d filas, %d columnas", len(base), base.shape[1])
    return base


def _asignar_municipio_por_entidad(base: pd.DataFrame) -> pd.DataFrame:
    """Usa la entidad responsable cuando la localizacion no es municipal.

    La tabla de localizacion del SUIFP marca dos proyectos de Cajica con el
    codigo 25000 ('Todo el Depto'). La entidad que los formula y ejecuta es
    la alcaldia de Cajica, y asi lo dice el nombre del proyecto. Sin esta
    correccion quedaban fuera del conteo por municipio y tomaban una
    poblacion promedio en lugar de la de Cajica.
    """
    from ..config import cargar_fuentes

    municipios = cargar_fuentes().municipios
    por_entidad = {m["entidad_suifp"]: m for m in municipios}
    validos = {m["divipola"] for m in municipios}

    base = base.copy()
    base["municipio_localizacion"] = base["municipio"]
    fuera = ~base["codigomunicipio"].astype(str).isin(validos)
    for i in base.index[fuera]:
        m = por_entidad.get(base.at[i, "entidadresponsable"])
        if m:
            base.at[i, "municipio"] = m["nombre_fuente"]
            base.at[i, "codigomunicipio"] = m["divipola"]
    if fuera.any():
        log.info("Municipio reasignado por entidad responsable en %d proyectos",
                 int(fuera.sum()))
    return base


# ---------------------------------------------------------------------------
# variables por dimension
# ---------------------------------------------------------------------------
def calcular_variables(df: pd.DataFrame, cfg: ConfigModelo) -> pd.DataFrame:
    """Calcula las variables crudas de cada dimension. Sin normalizar todavia."""
    m = cfg.mapeos
    poblacion = {str(k): float(v) for k, v in cfg.poblacion.items()}
    out = df.copy()

    for c in ["avancefisico", "avancefinanciero", "valor_vigente_total",
              "valor_obligado_total", "valor_pagado_total", "valor_fuente_externa",
              "totalbeneficiario", "valortotalproyecto", "valorvigenteproyecto",
              "n_vigencias_apropiadas", "n_vigencias_ejecutadas", "n_fuentes",
              "cv_apropiacion"]:
        out[c] = out.get(c, 0)
        out[c] = out[c].map(_num)

    pob = out["codigomunicipio"].astype(str).map(poblacion)
    pob = pob.fillna(float(np.mean(list(poblacion.values()))) if poblacion else 1.0)
    out["poblacion_municipal"] = pob

    # --- cero real frente a dato ausente -----------------------------------
    # El SUIFP no deja campos vacios: escribe cero. Tratar todo cero como
    # dato real castiga al proyecto por un reporte incompleto; tratarlo todo
    # como faltante premia al que no reporta. La regla es intermedia y
    # verificable: un cero es faltante solo si es imposible o si otra tabla
    # del propio SUIFP lo contradice.
    #   - Ficha financiera vacia: valor total del proyecto en cero. Ningun
    #     proyecto cuesta cero, asi que los montos de la ficha no se usan.
    #   - Seguimiento contradictorio: avance financiero en cero mientras la
    #     tabla de ejecucion registra obligaciones. El seguimiento no esta
    #     actualizado, y si ademas el avance fisico es cero, tampoco se usa.
    out["dato_ficha_financiera_vacia"] = out["valortotalproyecto"] <= 0
    out["dato_seguimiento_contradictorio"] = (
        (out["avancefinanciero"] == 0) & (out["valor_obligado_total"] > 0)
    )
    fisico_ausente = out["dato_seguimiento_contradictorio"] & (out["avancefisico"] == 0)

    # --- viabilidad financiera -------------------------------------------
    out["ratio_obligacion"] = [
        _div(o, v) for o, v in zip(out["valor_obligado_total"], out["valor_vigente_total"])
    ]
    # Se acota a 1: cinco proyectos reportan pagado por encima de obligado,
    # lo cual es inconsistencia de la fuente, no mejor desempeno.
    out["ratio_pago"] = [
        min(_div(p, o), 1.0)
        for p, o in zip(out["valor_pagado_total"], out["valor_obligado_total"])
    ]
    out["continuidad_presupuestal"] = out["n_vigencias_apropiadas"]
    out["diversificacion_fuentes"] = out["n_fuentes"]
    out["brecha_fisico_financiero"] = (
        (out["avancefisico"] - out["avancefinanciero"]).abs()
        .where(~out["dato_seguimiento_contradictorio"])
    )

    # --- madurez de ejecucion --------------------------------------------
    out["avance_fisico"] = out["avancefisico"].clip(0, 100).where(~fisico_ausente)
    # Se prefiere el subestado porque el estado es constante en el universo
    # evaluable. Si el subestado falta, se cae al estado como respaldo.
    estado_fuente = out.get("subestadoproyecto")
    if estado_fuente is None:
        estado_fuente = out["estadoproyecto"]
    else:
        estado_fuente = estado_fuente.fillna(out["estadoproyecto"])
    out["estado_proyecto"] = estado_fuente.map(lambda v: mapear(v, m["estado_proyecto"]))
    out["vigencias_ejecutadas"] = out["n_vigencias_ejecutadas"]
    out["estabilidad_apropiacion"] = out["cv_apropiacion"]

    # --- impacto social ---------------------------------------------------
    # Cobertura poblacional declarada, con tope en 1.0. El tope evita que un
    # proyecto que reporta mas beneficiarios que habitantes domine la escala.
    out["cobertura_declarada"] = [
        min(_div(b, p), 1.0) for b, p in zip(out["totalbeneficiario"], out["poblacion_municipal"])
    ]
    # Cero beneficiarios declarados es ficha sin diligenciar, no impacto nulo.
    out["beneficiarios_directos"] = out["cobertura_declarada"].where(
        out["totalbeneficiario"] > 0
    )
    out["excede_poblacion"] = out["totalbeneficiario"] > out["poblacion_municipal"]
    out["prioridad_sectorial"] = out["sector"].map(
        lambda v: mapear(v, m["prioridad_sectorial"])
    )
    out["inversion_relativa"] = [
        _div(v, p) for v, p in zip(out["valor_vigente_total"], out["poblacion_municipal"])
    ]

    # --- gobernanza -------------------------------------------------------
    # Metadato de calidad del dato. Se calcula y se muestra, pero no entra
    # al score (peso 0 en pesos.yaml, por exigencia de la direccion).
    out["completitud_ficha"] = out["completitud_ficha_v"]
    # Cobertura del reporte: proporcion de los anios del horizonte declarado
    # en los que el proyecto efectivamente reporto apropiacion. Reemplaza a
    # 'presencia_cruzada', que resulto constante. Sin horizonte legible el
    # dato es faltante, no cero.
    anios = out["horizonte"].map(_anios_horizonte)
    out["anios_horizonte"] = anios
    out["cobertura_reporte"] = [
        min(_div(v, a, defecto=0.0), 1.0) if a > 0 else np.nan
        for v, a in zip(out["n_vigencias_apropiadas"], anios)
    ]
    # Conducta de reporte de la entidad (si registra avance en el SUIFP).
    # Es un atributo de gobernanza del proyecto, no de la disponibilidad del
    # dato en esta plataforma, por eso se mantiene en el score.
    out["reporta_seguimiento"] = (out["avancefisico"] > 0).astype(float)
    # Consistencia: que el valor reportado en la ficha coincida con la suma
    # de la ejecucion anual. 1 = coherente, 0 = discrepancia total. Con la
    # ficha financiera vacia no hay con que comparar: es faltante.
    out["consistencia_financiera"] = [
        1.0 - min(abs(a - b) / max(a, b), 1.0) if max(a, b) > 0 else 0.0
        for a, b in zip(out["valorvigenteproyecto"], out["valor_vigente_total"])
    ]
    out["consistencia_financiera"] = out["consistencia_financiera"].where(
        ~out["dato_ficha_financiera_vacia"]
    )

    # --- atractivo inversor -----------------------------------------------
    out["escala_proyecto"] = np.log1p(out["valor_vigente_total"].clip(lower=0))
    out["sector_financiable"] = out["sector"].map(
        lambda v: mapear(v, m["sector_financiable"])
    )
    out["cofinanciacion_externa"] = [
        _div(e, v) for e, v in zip(out["valor_fuente_externa"], out["valor_vigente_total"])
    ]
    # Si el proyecto admite capital privado segun su tipo de intervencion:
    # una obra fisica se puede cofinanciar; un programa de funcionamiento no.
    out["tipo_intervencion"] = out["nombreproyecto"].map(clasificar_intervencion)
    out["vinculacion_privada"] = out["tipo_intervencion"].map(
        lambda v: mapear(v, m["vinculacion_privada"])
    )

    # --- atributos descriptivos, fuera del score ---------------------------
    out["beneficiarios_declarados"] = out["totalbeneficiario"]
    out["estado"] = estado_legible(estado_fuente)
    out["grupo_universo"], out["situacion"] = clasificar_vigencia(
        out["estado"], out["avancefisico"], out["avance_fisico"], cfg)

    return out


def estado_legible(serie: pd.Series) -> pd.Series:
    """Quita el espacio duro y el sufijo: 'Inactivo (PGN, Territorio)' -> 'Inactivo'."""
    return (serie.astype(str).str.replace("\xa0", " ")
            .str.replace(r"\s*\(PGN, Territorio\)", "", regex=True)
            .str.split().str.join(" "))


def clasificar_vigencia(estado: pd.Series, avance_reportado: pd.Series,
                        avance_valido: pd.Series, cfg: ConfigModelo):
    """Separa oportunidades vigentes de proyectos previos.

    Un proyecto previo NO es un proyecto completado: de los inactivos del
    corte 2026-09-11 solo 12 de 319 reportan el 100 % de avance. Por eso la
    situacion se informa tal como la reporta el SUIFP.
    """
    previos = {sin_tildes(s).lower() for s in cfg.universo["subestados_previos"]}
    es_previo = estado.map(lambda s: sin_tildes(s).lower() in previos)
    grupo = np.where(es_previo, "Previo", "Vigente")
    umbral = cfg.universo["avance_terminado"]
    situacion = np.select(
        [avance_valido.isna(), avance_reportado >= umbral, avance_reportado > 0],
        ["Sin dato valido de avance", "Terminado", "Avance parcial"],
        default="Sin avance reportado",
    )
    return pd.Series(grupo, index=estado.index), pd.Series(situacion, index=estado.index)


def variables_requeridas(cfg: ConfigModelo) -> List[str]:
    nombres: List[str] = []
    for dim in cfg.bruto["variables"]:
        nombres.extend(cfg.variables_activas(dim).keys())
    return nombres


def filtrar_universo_evaluable(
    df: pd.DataFrame, exigir_ejecucion: bool = True, exigir_avance: bool = False
) -> pd.DataFrame:
    """Recorta al subconjunto con informacion suficiente para ser calificado.

    La regla es explicita y se reporta, porque el recorte cambia el universo.
    """
    antes = len(df)
    d = df.copy()
    if exigir_ejecucion:
        d = d[d["valor_vigente_total"] > 0]
    if exigir_avance:
        d = d[d["avancefisico"] > 0]
    log.info("Universo evaluable: %d de %d proyectos (%.1f%%)",
             len(d), antes, 100 * len(d) / antes if antes else 0)
    return d.reset_index(drop=True)
