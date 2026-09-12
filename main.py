# -*- coding: utf-8 -*-
"""Punto de entrada unico de ColombiaInvest.

Ejecutar con F5 en Visual Studio Code, o desde la consola:

    python main.py

Hace tres cosas, en orden:
  1. Verifica que las dependencias esten instaladas.
  2. Construye los datos si faltan (descarga el SUIFP del DNP y procesa
     los documentos municipales). Solo la primera vez.
  3. Levanta el servidor del tablero y abre el navegador.

Opciones:
    python main.py --reconstruir   fuerza rehacer los datos desde cero
    python main.py --solo-datos    construye los datos y no abre el tablero
    python main.py --puerto 8600   usa otro puerto
"""
from __future__ import annotations

import argparse
import importlib
import runpy
import subprocess
import sys
import threading
import time
import webbrowser
from pathlib import Path

RAIZ = Path(__file__).resolve().parent
SRC = RAIZ / "src"
APP = RAIZ / "app" / "tablero.py"
SCRIPTS = RAIZ / "scripts"
MARCA_DATOS = RAIZ / "datos" / "procesados" / "proyectos_evaluables.parquet"
MARCA_DOCS = RAIZ / "datos" / "procesados" / "informe_gestion_cajica_2024.json"

PUERTO_POR_DEFECTO = 8501

# modulo a importar -> nombre en requirements.txt
DEPENDENCIAS = {
    "pandas": "pandas",
    "numpy": "numpy",
    "scipy": "scipy",
    "yaml": "PyYAML",
    "streamlit": "streamlit",
    "pyarrow": "pyarrow",
    "pypdf": "pypdf",
}


def aviso(texto: str) -> None:
    print(f"\n{'=' * 70}\n{texto}\n{'=' * 70}", flush=True)


# ---------------------------------------------------------------------------
def verificar_dependencias(instalar: bool) -> bool:
    faltan = []
    for modulo, paquete in DEPENDENCIAS.items():
        try:
            importlib.import_module(modulo)
        except ImportError:
            faltan.append(paquete)

    if not faltan:
        return True

    aviso("Faltan dependencias: " + ", ".join(faltan))
    if not instalar:
        print("Instalelas con:\n")
        print(f"    {Path(sys.executable).name} -m pip install -r requirements.txt\n")
        return False

    print("Instalando desde requirements.txt ...", flush=True)
    codigo = subprocess.call(
        [sys.executable, "-m", "pip", "install", "-r", str(RAIZ / "requirements.txt")]
    )
    if codigo != 0:
        print("La instalacion fallo. Revise el mensaje de pip.")
        return False
    return True


# ---------------------------------------------------------------------------
def ejecutar_script(nombre: str, argumentos: list[str] | None = None) -> None:
    """Corre un script de scripts/ dentro de este mismo proceso."""
    ruta = SCRIPTS / nombre
    print(f"\n>>> {nombre}", flush=True)
    argv_original = sys.argv[:]
    sys.argv = [str(ruta)] + (argumentos or [])
    try:
        runpy.run_path(str(ruta), run_name="__main__")
    except SystemExit as e:
        if e.code not in (0, None):
            raise RuntimeError(f"{nombre} termino con codigo {e.code}") from e
    finally:
        sys.argv = argv_original


def preparar_datos(reconstruir: bool) -> None:
    if MARCA_DATOS.exists() and not reconstruir:
        print(f"Datos listos en {MARCA_DATOS.parent}")
        if not MARCA_DOCS.exists():
            print("Falta el contexto municipal. Procesando documentos ...")
            try:
                ejecutar_script("04_documentos.py")
            except Exception as e:
                print(f"No se pudo procesar los documentos: {e}")
                print("El tablero funciona igual, sin la seccion de contexto.")
        return

    aviso("Construyendo los datos. Solo ocurre la primera vez.\n"
          "Requiere conexion a internet: se descarga el SUIFP del DNP\n"
          "desde datos.gov.co. Toma alrededor de dos minutos.")
    ejecutar_script("01_ingesta.py")
    ejecutar_script("02_dataset.py")
    ejecutar_script("03_score.py")
    try:
        ejecutar_script("04_documentos.py")
    except Exception as e:
        print(f"No se pudo procesar los documentos municipales: {e}")
        print("El tablero funciona igual, sin la seccion de contexto municipal.")


# ---------------------------------------------------------------------------
def abrir_navegador(puerto: int, demora: float = 3.5) -> None:
    def _abrir() -> None:
        time.sleep(demora)
        webbrowser.open_new_tab(f"http://localhost:{puerto}")

    threading.Thread(target=_abrir, daemon=True).start()


def lanzar_tablero(puerto: int) -> int:
    aviso(f"Abriendo el tablero en http://localhost:{puerto}\n"
          "Para detenerlo, presione Ctrl+C en esta consola.")
    abrir_navegador(puerto)
    sys.argv = [
        "streamlit", "run", str(APP),
        "--server.port", str(puerto),
        "--server.headless", "true",
    ]
    from streamlit.web import cli as stcli

    try:
        return int(stcli.main() or 0)
    except SystemExit as e:
        return int(e.code or 0)
    except KeyboardInterrupt:
        print("\nServidor detenido.")
        return 0


# ---------------------------------------------------------------------------
def main() -> int:
    p = argparse.ArgumentParser(
        description="ColombiaInvest: modelo de calificacion de proyectos de "
                    "inversion publica de Chia y Cajica."
    )
    p.add_argument("--reconstruir", action="store_true",
                   help="rehace los datos desde las fuentes")
    p.add_argument("--solo-datos", action="store_true",
                   help="construye los datos y no abre el tablero")
    p.add_argument("--puerto", type=int, default=PUERTO_POR_DEFECTO)
    p.add_argument("--sin-instalar", action="store_true",
                   help="no instala dependencias faltantes, solo avisa")
    args = p.parse_args()

    print("ColombiaInvest")
    print("Trabajo de grado, Maestria en Ciencia de Datos, Universidad EAN")
    print(f"Python    {sys.version.split()[0]}")
    # Se imprime el interprete porque Visual Studio Code puede estar usando
    # uno distinto al de la consola, con otra version de Streamlit. Eso
    # explica diferencias de apariencia entre una ejecucion y otra.
    print(f"Ejecutable {sys.executable}")
    print(f"Proyecto   {RAIZ}")

    if sys.version_info < (3, 10):
        aviso("Se requiere Python 3.10 o superior. "
              f"Esta corriendo {sys.version.split()[0]}.")
        return 1

    if str(SRC) not in sys.path:
        sys.path.insert(0, str(SRC))

    if not verificar_dependencias(instalar=not args.sin_instalar):
        return 1

    import streamlit as _st
    print(f"Streamlit  {_st.__version__}")
    if tuple(int(x) for x in _st.__version__.split(".")[:2]) < (1, 40):
        aviso(f"Streamlit {_st.__version__} es anterior a 1.40 y la barra de "
              "navegacion no se vera como pestanas.\n"
              f"Actualice con: {Path(sys.executable).name} "
              "-m pip install -U streamlit")

    try:
        preparar_datos(args.reconstruir)
    except Exception as e:
        aviso(f"No se pudieron construir los datos:\n{e}\n\n"
              "Si el problema es de red, verifique el acceso a "
              "https://www.datos.gov.co")
        return 1

    if args.solo_datos:
        print("\nDatos construidos. Tablero no abierto por --solo-datos.")
        return 0

    return lanzar_tablero(args.puerto)


if __name__ == "__main__":
    raise SystemExit(main())
