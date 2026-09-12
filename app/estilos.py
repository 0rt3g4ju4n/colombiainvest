# -*- coding: utf-8 -*-
"""Paleta y estilos de ColombiaInvest.

La paleta se tomo del portal de Datos Abiertos de Colombia (datos.gov.co),
que sigue el sistema de diseno GOV.CO. Se muestrearon los colores del sitio
el 12 de septiembre de 2026.

Usar el mismo lenguaje visual del portal oficial no es solo estetica: el
usuario objetivo, sea funcionario o inversionista, ya reconoce ese codigo
de color como informacion publica confiable.
"""
from __future__ import annotations

PALETA = {
    "azul_gov": "#0B4EC8",        # barra superior de GOV.CO
    "azul_oscuro": "#2E4A8F",     # tarjeta DESCUBRE
    "azul_profundo": "#06357A",
    "naranja": "#DE8B34",         # tarjeta PUBLICA
    "azul_claro": "#93B2C6",      # tarjeta CONOCE
    "azul_tenue": "#E4EDFA",      # fondo de la barra lateral y encabezados
    "azul_hover": "#D2E0F5",      # realce de encabezado de tabla
    "borde_azul": "#C3D4EC",      # lineas de tabla
    "gris_fondo": "#F4F4F4",
    "gris_borde": "#D7DCE2",
    "gris_texto": "#4A4A4A",      # gris legible, no claro
    "blanco": "#FFFFFF",
    "texto": "#1A1A1A",
    "verde": "#069169",
    "amarillo": "#C98A00",
    "rojo": "#A80521",
}

# Margen lateral del area principal. Se usa tambien en negativo para que la
# barra superior se extienda de borde a borde.
MARGEN = "2.5rem"

# Altos de la cabecera fija. Se usan para reservar espacio en el contenido
# y en el panel lateral, de modo que la barra superior nunca los tape.
ALTO_BARRA = "133px"      # barra azul mas la franja (medido en navegador)
ALTO_CABECERA = "202px"   # barra azul, franja y navegacion (medido)


def color_score(valor: float) -> str:
    if valor >= 70:
        return PALETA["verde"]
    if valor >= 50:
        return PALETA["azul_gov"]
    if valor >= 35:
        return PALETA["amarillo"]
    return PALETA["rojo"]


def moneda(valor: float, corto: bool = False) -> str:
    """Formato colombiano: punto como separador de miles."""
    try:
        v = float(valor)
    except (TypeError, ValueError):
        return "n/d"
    if corto:
        if abs(v) >= 1e12:
            return f"${v/1e12:,.1f} billones".replace(",", ".")
        if abs(v) >= 1e9:
            return f"${v/1e9:,.1f} mil millones".replace(",", ".")
        if abs(v) >= 1e6:
            return f"${v/1e6:,.1f} millones".replace(",", ".")
    return "$" + f"{v:,.0f}".replace(",", ".")


def numero(valor: float, decimales: int = 0) -> str:
    try:
        v = float(valor)
    except (TypeError, ValueError):
        return "n/d"
    s = f"{v:,.{decimales}f}"
    return s.replace(",", "␟").replace(".", ",").replace("␟", ".")


def barra_peso(etiqueta: str, peso: float, ancho: bool = False) -> str:
    """Barra azul de 0 a 100 para mostrar cuanto pesa una dimension.

    ancho=True usa una etiqueta larga sin recorte, para donde sobra espacio.
    """
    pct = max(0.0, min(peso * 100, 100.0))
    clase = "ci-peso ci-peso-ancho" if ancho else "ci-peso"
    return (
        f'<div class="{clase}"><span class="et">{etiqueta}</span>'
        f'<span class="pista"><span class="relleno" style="width:{pct:.0f}%"></span></span>'
        f'<span class="val">{pct:.0f}</span></div>'
    )


CSS = f"""
<style>
  :root {{
    --azul-gov: {PALETA['azul_gov']};
    --azul-oscuro: {PALETA['azul_oscuro']};
    --azul-profundo: {PALETA['azul_profundo']};
    --naranja: {PALETA['naranja']};
    --azul-claro: {PALETA['azul_claro']};
    --azul-tenue: {PALETA['azul_tenue']};
    --gris-fondo: {PALETA['gris_fondo']};
    --gris-borde: {PALETA['gris_borde']};
    --gris-texto: {PALETA['gris_texto']};
    --texto: {PALETA['texto']};
    --margen: {MARGEN};
    --alto-barra: {ALTO_BARRA};
    --alto-cabecera: {ALTO_CABECERA};
  }}

  /* Solo se sube la base. Aplicar font-size a [class*="st-"] aplasta la
     escala tipografica propia de Streamlit y deja las metricas diminutas. */
  html, body {{ font-size: 16.5px; }}
  .stMarkdown p, .stMarkdown li {{ font-size: 1rem; line-height: 1.62; }}
  .stCaption, [data-testid="stCaptionContainer"] p {{
    font-size: .92rem !important; color: var(--gris-texto) !important;
  }}

  /* La franja de herramientas propia de Streamlit estorba, pero NO se puede
     ocultar entera: el boton que vuelve a abrir el panel lateral vive dentro
     de ella. Si se oculta, al cerrar el panel no hay forma de recuperarlo.
     Se deja el contenedor sin alto ni eventos, y se ocultan solo la barra de
     herramientas y la decoracion. */
  [data-testid="stHeader"] {{
    background: transparent !important;
    height: 0 !important; min-height: 0 !important;
    pointer-events: none !important;
    z-index: 999998 !important;
  }}
  /* stToolbar NO se puede ocultar: el boton de reapertura del panel es
     descendiente suyo, y un ancestro en display:none anula el position
     fixed del descendiente. Se ocultan solo Deploy, menu y acciones. */
  [data-testid="stToolbar"] {{
    display: flex !important; background: transparent !important;
    pointer-events: none !important;
  }}
  [data-testid="stToolbarActions"], [data-testid="stAppDeployButton"],
  [data-testid="stMainMenu"], [data-testid="stDecoration"],
  [data-testid="stStatusWidget"] {{ display: none !important; }}

  /* ---------- cabecera fija, por encima de la barra lateral ----------
     Va fija arriba y ocupa todo el ancho de la ventana. Lo unico que se
     desplaza cuando aparece el panel de filtros es el contenido de abajo,
     nunca la cabecera. */
  .st-key-cihead {{
    position: fixed; top: 0; left: 0; right: 0; z-index: 999995;
  }}
  .st-key-cinav {{
    position: fixed; top: var(--alto-barra); left: 0; right: 0; z-index: 999995;
    padding: 0 var(--margen);
    background: #fff; border-bottom: 2px solid var(--gris-borde);
  }}

  /* Se reserva el alto de la cabecera en el area principal y en el panel
     lateral, para que nada quede tapado. */
  .block-container {{
    padding: calc(var(--alto-cabecera) + 1.4rem) var(--margen) 3rem var(--margen) !important;
    max-width: 100% !important;
  }}
  section[data-testid="stSidebar"] [data-testid="stSidebarContent"] {{
    padding-top: calc(var(--alto-cabecera) + 0.6rem);
  }}
  /* El boton para cerrar el panel va dentro del panel, bajo la cabecera. */
  [data-testid="stSidebarCollapseButton"] {{
    top: calc(var(--alto-cabecera) - 2.4rem) !important;
    z-index: 999996 !important;
  }}
  /* Boton para volver a abrir el panel. En esta version de Streamlit se
     llama stExpandSidebarButton y el elemento con ese testid ES el boton,
     no un contenedor: por eso hay que darle tamano y color a el mismo. */
  [data-testid="stExpandSidebarButton"] {{
    position: fixed !important;
    top: calc(var(--alto-cabecera) + 0.6rem) !important;
    left: 0.9rem !important;
    z-index: 999999 !important;
    pointer-events: auto !important;
    display: flex !important;
    align-items: center !important; justify-content: center !important;
    width: 38px !important; height: 38px !important;
    background: var(--azul-gov) !important;
    border: 1px solid var(--azul-profundo) !important;
    border-radius: 6px !important;
    box-shadow: 0 2px 8px rgba(0,0,0,.22) !important;
  }}
  [data-testid="stExpandSidebarButton"]:hover {{
    background: var(--azul-profundo) !important;
  }}
  [data-testid="stExpandSidebarButton"] span {{
    color: #fff !important; fill: #fff !important;
  }}

  /* --- selector desplegable: elegir, no escribir ---
     BaseWeb deja el campo editable y el usuario puede teclear texto que no
     corresponde a ninguna opcion. Se anula el puntero sobre el campo: el
     clic pasa al control, que abre la lista, pero el campo no recibe foco. */
  div[data-baseweb="select"] input {{
    pointer-events: none !important;
    caret-color: transparent !important;
  }}
  div[data-baseweb="select"] > div {{ cursor: pointer; }}

  .ci-barra {{
    background: var(--azul-gov);
    color: #fff;
    padding: 34px var(--margen) 32px var(--margen);
    display: flex; align-items: baseline; gap: 18px; flex-wrap: wrap;
    font-family: Roboto, "Segoe UI", sans-serif;
  }}
  .ci-barra .marca {{ font-size: 2.3rem; font-weight: 800; letter-spacing: -0.5px; }}
  .ci-barra .lema {{ font-size: 1.1rem; opacity: 0.95; }}
  /* Franja en azules. Se retiro el naranja: era el unico color calido del
     tablero y quedaba suelto frente al resto de la paleta. */
  .ci-franja {{
    height: 6px;
    background: linear-gradient(90deg,
      var(--azul-profundo) 0 34%, var(--azul-gov) 34% 67%, var(--azul-claro) 67% 100%);
  }}
  /* ---------- navegacion superior ----------
     Se estila por el data-testid del propio boton y no por la clase del
     contenedor (st-key-cinav). Esa clase depende de la version de Streamlit
     y si falta, el control aparece con su aspecto por defecto: recuadros
     con borde en lugar de pestanas. El testid del boton es estable y es el
     unico control segmentado de la aplicacion. */
  [data-testid="stButtonGroup"] {{
    gap: 2px; flex-wrap: wrap; margin-bottom: -2px;
    background: transparent !important; border: none !important;
    box-shadow: none !important; padding: 0 !important;
  }}
  [data-testid="stButtonGroup"] [data-baseweb="button-group"] {{
    gap: 2px; background: transparent !important; border: none !important;
  }}
  button[data-testid="stBaseButton-segmented_control"],
  button[data-testid="stBaseButton-segmented_controlActive"] {{
    background: transparent !important;
    border: none !important;
    border-bottom: 4px solid transparent !important;
    border-radius: 0 !important;
    padding: 17px 28px 18px 28px !important;
    /* Streamlit fija el alto del boton y recorta con overflow hidden, de
       modo que el relleno vertical no surtia efecto. Se libera el alto. */
    height: auto !important; min-height: 0 !important;
    overflow: visible !important;
    color: var(--gris-texto) !important;
    box-shadow: none !important;
    transition: all .12s ease;
  }}
  button[data-testid="stBaseButton-segmented_control"] p,
  button[data-testid="stBaseButton-segmented_controlActive"] p {{
    font-size: 1.12rem !important; font-weight: 600 !important;
    color: inherit !important; margin: 0 !important;
  }}
  button[data-testid="stBaseButton-segmented_control"]:hover {{
    background: rgba(11,78,200,.06) !important;
    color: var(--azul-gov) !important;
  }}
  button[data-testid="stBaseButton-segmented_controlActive"] {{
    color: var(--azul-gov) !important;
    border-bottom-color: var(--azul-gov) !important;
  }}
  button[data-testid="stBaseButton-segmented_controlActive"] p {{
    color: var(--azul-gov) !important; font-weight: 700 !important;
  }}

  /* ---------- tarjeta de proyecto ---------- */
  .ci-card {{
    background: #fff; border: 1px solid var(--gris-borde); border-radius: 8px;
    padding: 15px 17px 13px 17px;
    min-height: 410px; display: flex; flex-direction: column;
    box-shadow: 0 1px 3px rgba(0,0,0,.06);
    transition: box-shadow .15s ease, border-color .15s ease;
    font-family: Roboto, "Segoe UI", sans-serif;
  }}
  .ci-card:hover {{ box-shadow: 0 4px 14px rgba(0,0,0,.12); border-color: var(--azul-gov); }}
  .ci-card .ci-barras {{ margin-top: auto; padding-top: 12px; }}
  .ci-card-top {{ display: flex; justify-content: space-between; align-items: flex-start; gap: 8px; }}
  .ci-sector {{
    background: var(--gris-fondo); color: var(--gris-texto);
    font-size: .72rem; font-weight: 700; letter-spacing: .3px;
    padding: 4px 9px; border-radius: 3px; text-transform: uppercase;
  }}
  .ci-score {{
    color: #fff; font-weight: 800; font-size: 1.18rem;
    padding: 5px 12px; border-radius: 4px; white-space: nowrap;
  }}
  .ci-titulo {{
    font-size: 1.02rem; font-weight: 600; line-height: 1.34; color: var(--texto);
    margin: 11px 0 7px 0; min-height: 2.7em;
  }}
  .ci-meta {{ font-size: .84rem; color: var(--gris-texto); margin-bottom: 9px; }}
  .ci-precio {{ font-size: 1.5rem; font-weight: 300; color: var(--texto); line-height: 1.1; }}
  .ci-precio-nota {{ font-size: .78rem; color: var(--gris-texto); margin-bottom: 11px; }}
  .ci-datos {{ font-size: .88rem; color: var(--texto); line-height: 1.62; }}
  .ci-datos b {{ font-weight: 600; }}
  .ci-fila {{ display: flex; align-items: center; gap: 7px; margin-bottom: 4px; }}
  .ci-fila .et {{ font-size: .76rem; color: var(--gris-texto); width: 84px; flex: none; }}
  .ci-fila .pista {{
    display: block; flex: 1; height: 7px; background: var(--gris-fondo);
    border-radius: 4px; overflow: hidden;
  }}
  .ci-fila .relleno {{ display: block; height: 100%; border-radius: 4px; }}
  .ci-fila .val {{ font-size: .76rem; color: var(--gris-texto); width: 26px; text-align: right; flex: none; }}

  /* ---------- resumen de resultados ---------- */
  .ci-resultados {{
    display: flex; justify-content: space-between; align-items: center;
    padding: 4px 2px 12px 2px; border-bottom: 1px solid var(--gris-borde);
    margin-bottom: 16px; font-family: Roboto, "Segoe UI", sans-serif;
  }}
  .ci-resultados .conteo {{ font-size: 1.05rem; color: var(--texto); }}
  .ci-resultados .conteo b {{ font-weight: 700; }}

  .ci-chip {{
    display: inline-block; background: rgba(11,78,200,.08); color: var(--azul-gov);
    border: 1px solid rgba(11,78,200,.28); border-radius: 14px;
    padding: 3px 11px; font-size: .82rem; font-weight: 600; margin: 0 5px 5px 0;
  }}

  /* ---------- bloques institucionales ---------- */
  .ci-hero {{
    background: linear-gradient(110deg, var(--azul-oscuro), var(--azul-gov));
    color: #fff; padding: 36px 40px; border-radius: 8px; margin-bottom: 24px;
    font-family: Roboto, "Segoe UI", sans-serif;
  }}
  .ci-hero h1 {{ font-size: 2.15rem; margin: 0 0 12px 0; font-weight: 800; line-height: 1.22; }}
  .ci-hero p {{ font-size: 1.08rem; opacity: .96; margin: 0; line-height: 1.6; max-width: 78ch; }}
  .ci-panel {{
    background: #fff; border: 1px solid var(--gris-borde);
    border-left: 4px solid var(--azul-gov);
    border-radius: 6px; padding: 17px 19px; margin-bottom: 12px; height: 100%;
  }}
  .ci-panel h3 {{ margin: 0 0 9px 0; font-size: 1.1rem; color: var(--azul-oscuro); }}
  .ci-panel p {{ margin: 0; font-size: .95rem; line-height: 1.62; color: var(--texto); }}
  .ci-nota {{
    font-size: .92rem; color: var(--gris-texto); line-height: 1.6;
    border-top: 1px solid var(--gris-borde); padding-top: 12px; margin-top: 6px;
  }}

  /* ---------- tablas legibles ----------
     Streamlit pinta los encabezados y el indice en un gris muy claro que
     se pierde, sobre todo en las tablas anchas. */
  [data-testid="stDataFrame"] {{ font-size: .95rem; }}
  [data-testid="stDataFrame"] [role="columnheader"],
  [data-testid="stDataFrame"] [data-testid="stDataFrameResizable"] [role="columnheader"] {{
    color: var(--texto) !important; font-weight: 700 !important;
    background: var(--gris-fondo) !important;
  }}
  [data-testid="stDataFrame"] [role="rowheader"],
  [data-testid="stDataFrame"] .row-header {{
    color: var(--texto) !important; font-weight: 600 !important;
  }}
  /* El color de encabezados e indices de la rejilla NO se controla desde
     aqui: se dibuja en un canvas cuyo tema arma Streamlit. Se configura en
     .streamlit/config.toml con dataframeHeaderBackgroundColor. */

  /* ---------- barra lateral, en azules ---------- */
  section[data-testid="stSidebar"] {{
    background: var(--azul-tenue);
    border-right: 1px solid var(--gris-borde);
  }}
  section[data-testid="stSidebar"] * {{ color: var(--texto); }}
  .ci-filtro-tit {{
    font-size: .86rem; font-weight: 700; text-transform: uppercase;
    letter-spacing: .4px; color: var(--azul-oscuro);
    margin: 18px 0 6px 0; padding-bottom: 5px;
    border-bottom: 2px solid var(--azul-claro);
  }}
  section[data-testid="stSidebar"] label p {{ font-size: .94rem; }}
  section[data-testid="stSidebar"] details {{
    background: #fff; border: 1px solid var(--gris-borde); border-radius: 6px;
  }}

  /* barra azul de peso por dimension */
  .ci-peso {{ display: flex; align-items: center; gap: 9px; margin-bottom: 9px; }}
  .ci-peso .et {{
    font-size: .86rem; color: var(--texto); width: 84px; flex: none;
    white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
  }}
  .ci-peso .pista {{
    display: block; flex: 1; height: 13px; background: #fff;
    border: 1px solid var(--azul-claro); border-radius: 7px; overflow: hidden;
  }}
  .ci-peso .relleno {{
    display: block; height: 100%; background: var(--azul-gov);
    border-radius: 6px 0 0 6px; min-width: 3px;
  }}
  .ci-peso .val {{
    font-size: .88rem; font-weight: 800; color: var(--azul-oscuro);
    width: 26px; text-align: right; flex: none;
  }}
  .ci-peso-ancho {{ max-width: 520px; }}
  .ci-peso-ancho .et {{ width: 190px; font-size: .95rem; }}
  .ci-peso-ancho .pista {{ height: 15px; }}
</style>
"""

# Se inyecta solo en las secciones que no usan filtros.
OCULTAR_LATERAL = """
<style>
  section[data-testid="stSidebar"] {display: none !important;}
  [data-testid="stExpandSidebarButton"] {display: none !important;}
</style>
"""
