# -*- coding: utf-8 -*-
"""Extraccion de documentos municipales en PDF.

Estas fuentes son ASIMETRICAS: solo existen para Cajica y solo para la
vigencia 2024. Cubren 79 de los 491 proyectos evaluables y ninguno de los
221 de Chia.

Por esa razon NO alimentan variables del score. Si lo hicieran, un
subconjunto de proyectos se calificaria con informacion que el resto no
tiene, lo que sesgaria el ranking por disponibilidad documental y no por
merito del proyecto.

Se usan para tres cosas legitimas:
  1. Enriquecer la ficha del proyecto en el prototipo.
  2. Contrastar el avance reportado en el SUIFP contra el que reporta el
     municipio en su informe de gestion. Ese contraste es un hallazgo de
     gobernanza, no una variable de calificacion.
  3. Servir de muestra real documentada para la demostracion.
"""
from __future__ import annotations

import json
import logging
import re
import unicodedata
from pathlib import Path
from typing import Any, Dict, List

log = logging.getLogger(__name__)

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


RE_BPIN = re.compile(r"20\d{2}2512[26]0\d{3}")

# Sectores del informe de gestion. La frase es estable en todo el documento.
RE_SECTOR = re.compile(
    r"SECTOR\s+([A-ZÁÉÍÓÚÑ][A-ZÁÉÍÓÚÑ,\s]{3,55}?)\s*\.?\s*"
    r"El avance f[ií]sico del sector fue de\s*([\d.,]+)\s*%\.?\s*"
    r"Los recursos programados fueron de:?\s*\$?\s*([\d.,]+),?\s*"
    r"de los cuales se ejecutaron\s*\$?\s*([\d.,]+),?\s*"
    r"lo que equivale a un\s*([\d.,]+)\s*%",
    re.IGNORECASE,
)


def _texto_pdf(ruta: Path) -> str:
    import pypdf

    lector = pypdf.PdfReader(str(ruta))
    partes = [(p.extract_text() or "") for p in lector.pages]
    texto = "\n".join(partes)
    if not texto.strip():
        raise ValueError(
            f"{ruta.name} no tiene texto extraible. Es un documento escaneado "
            "y requiere OCR antes de poder procesarse."
        )
    return texto


def _pct(s: str) -> float:
    """Convierte un porcentaje escrito en el documento a float.

    El informe mezcla separadores: escribe 92,5% en unos sectores y 86.7%
    en otros. Tratar el punto siempre como separador de miles convertia
    86.7 en 867, un error que se detecto al ver un avance fisico de 867 %.
    """
    t = s.strip()
    if "," in t:                      # coma decimal, punto de miles
        return float(t.replace(".", "").replace(",", "."))
    if t.count(".") == 1 and len(t.split(".")[1]) <= 2:
        return float(t)               # punto decimal
    return float(t.replace(".", ""))  # solo separadores de miles


def _monto(s: str) -> float:
    limpio = re.sub(r"[^\d]", "", s)
    return float(limpio) if limpio else 0.0


# ---------------------------------------------------------------------------
# 1. Listado de proyectos del PDM
# ---------------------------------------------------------------------------
def parsear_proyectos_pdm(ruta: Path) -> List[Dict[str, Any]]:
    """Extrae la tabla de proyectos del PDM de Cajica.

    La extraccion de PDF rompe las celdas en varias lineas, asi que se
    segmenta por codigo BPIN y se interpreta el bloque de texto asociado.
    """
    texto = _texto_pdf(ruta)
    posiciones = [(m.group(0), m.start(), m.end()) for m in RE_BPIN.finditer(texto)]
    if not posiciones:
        log.warning("No se hallaron codigos BPIN en %s", ruta.name)
        return []

    registros: List[Dict[str, Any]] = []
    for i, (bpin, ini, fin) in enumerate(posiciones):
        # el nombre viene antes del codigo, los atributos despues
        ini_nombre = posiciones[i - 1][2] if i else 0
        nombre = _limpiar(texto[ini_nombre:ini])
        nombre = re.sub(r"^\d+\s+", "", nombre)
        sig = posiciones[i + 1][1] if i + 1 < len(posiciones) else len(texto)
        cola = _limpiar(texto[fin:sig])
        cola = re.sub(r"\d+\s*$", "", cola).strip()

        registros.append(
            {
                "bpin": bpin,
                "nombre_pdm": nombre,
                "responsable_pdm": _extraer_responsable(cola),
                "dimension_pdm": _extraer_etiqueta(cola, r"\d+\.\s*(?:CAJIC[ÁA]|IDEAL)[^|]*?(?=\d+\.\s|$)"),
                "sector_pdm": _extraer_etiqueta(cola, r"\b(\d{2})\.\s*([A-ZÁÉÍÓÚÑa-záéíóúñ][^0-9]{4,45})"),
                "bloque_crudo": cola[:400],
            }
        )
    log.info("PDM: %d proyectos extraidos de %s", len(registros), ruta.name)
    return registros


def _limpiar(s: str) -> str:
    return " ".join(s.replace("\n", " ").split()).strip()


def _extraer_responsable(cola: str) -> str:
    m = re.search(
        r"(Secretar[ií]a[^0-9]{0,60}|EPC\b|Direcci[oó]n[^0-9]{0,50}|"
        r"Oficina[^0-9]{0,50}|Instituto[^0-9]{0,50}|Personer[ií]a\b|Concejo\b)",
        cola,
    )
    return _limpiar(m.group(1)) if m else ""


def _extraer_etiqueta(cola: str, patron: str) -> str:
    m = re.search(patron, cola)
    if not m:
        return ""
    return _limpiar(m.group(0))


# ---------------------------------------------------------------------------
# 2. Informe de gestion: avance por sector
# ---------------------------------------------------------------------------
def parsear_informe_gestion(ruta: Path) -> Dict[str, Any]:
    """Extrae el avance fisico y presupuestal por sector y el global."""
    texto = re.sub(r"\s+", " ", _texto_pdf(ruta))

    sectores = []
    for m in RE_SECTOR.finditer(texto):
        programado = _monto(m.group(3))
        ejecutado = _monto(m.group(4))
        sectores.append(
            {
                "sector_informe": _limpiar(m.group(1)).rstrip("."),
                "avance_fisico_sector": _pct(m.group(2)),
                "recursos_programados": programado,
                "recursos_ejecutados": ejecutado,
                "ejecucion_presupuestal_sector": _pct(m.group(5)),
                "brecha_sector": _pct(m.group(2)) - _pct(m.group(5)),
            }
        )

    global_: Dict[str, Any] = {}
    m = re.search(r"ejecuci[oó]n f[ií]sica para la vigencia 2024[^%]{0,120}?fue del\s*([\d,.]+)\s*%", texto, re.I)
    if m:
        global_["avance_fisico_vigencia_2024"] = _pct(m.group(1))
    # El avance del cuatrienio es la cifra comparable con el SUIFP, que
    # reporta avance acumulado del proyecto y no de una vigencia.
    m = re.search(r"avance del cuatrienio fue de\s*([\d,.]+)\s*%", texto, re.I)
    if m:
        global_["avance_fisico_cuatrienio"] = _pct(m.group(1))
    m = re.search(r"ejecuci[oó]n de recursos de\s*\$?\s*([\d.]+),?\s*correspondiente al\s*([\d,]+)\s*%", texto, re.I)
    if m:
        global_["recursos_ejecutados_plan"] = _monto(m.group(1))
        global_["ejecucion_presupuestal_plan"] = _pct(m.group(2))

    log.info("Informe de gestion: %d sectores, global %s", len(sectores), global_)
    return {"global": global_, "sectores": sectores}


# ---------------------------------------------------------------------------
def guardar(obj: Any, ruta: Path) -> None:
    ruta.parent.mkdir(parents=True, exist_ok=True)
    with open(ruta, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)
    log.info("Guardado %s", ruta.name)
