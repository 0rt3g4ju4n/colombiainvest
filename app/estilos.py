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
    "azul_tenue": "#E4EDFA",      # fondo de la barra lateral
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
  }}

  /* Solo se sube la base. Aplicar font-size a [class*="st-"] aplasta la
     escala tipografica propia de Streamlit y deja las metricas diminutas. */
  html, body {{ font-size: 16.5px; }}
  .stMarkdown p, .stMarkdown li {{ font-size: 1rem; line-height: 1.62; }}
  .stCaption, [data-testid="stCaptionContainer"] p {{
    font-size: .92rem !important; color: var(--gris-texto) !important;
  }}

  /* El contenedor ocupa todo el ancho para que la barra superior pueda
     extenderse de borde a borde. El padding superior deja libre la franja
     de herramientas de Streamlit, que va fija arriba. */
  .block-container {{
    padding: 3.4rem var(--margen) 3rem var(--margen) !important;
    max-width: 100% !important;
  }}

  /* ---------- barra superior, de borde a borde ---------- */
  .ci-barra {{
    background: var(--azul-gov);
    color: #fff;
    padding: 20px var(--margen) 18px var(--margen);
    margin: 0 calc(-1 * var(--margen));
    display: flex; align-items: baseline; gap: 18px; flex-wrap: wrap;
    font-family: Roboto, "Segoe UI", sans-serif;
  }}
  .ci-barra .marca {{ font-size: 1.85rem; font-weight: 800; letter-spacing: -0.4px; }}
  .ci-barra .lema {{ font-size: 1rem; opacity: 0.95; }}
  .ci-franja {{
    height: 7px; margin: 0 calc(-1 * var(--margen)) 4px calc(-1 * var(--margen));
    background: linear-gradient(90deg,
      var(--azul-oscuro) 0 33%, var(--naranja) 33% 66%, var(--azul-claro) 66% 100%);
  }}

  /* ---------- navegacion superior ---------- */
  .st-key-cinav {{
    margin: 0 calc(-1 * var(--margen)) 22px calc(-1 * var(--margen));
    padding: 0 var(--margen);
    background: #fff; border-bottom: 2px solid var(--gris-borde);
  }}
  .st-key-cinav div[role="radiogroup"] {{
    flex-direction: row; gap: 2px; flex-wrap: wrap; margin-bottom: -2px;
  }}
  .st-key-cinav div[role="radiogroup"] > label {{
    background: transparent; border: none;
    border-bottom: 3px solid transparent;
    padding: 12px 20px 13px 20px; margin: 0;
    font-weight: 600; cursor: pointer; transition: all .12s ease;
  }}
  .st-key-cinav div[role="radiogroup"] > label > div:first-child {{
    display: none !important;
  }}
  .st-key-cinav div[role="radiogroup"] > label p {{
    font-size: 1.02rem; font-weight: 600; color: var(--gris-texto);
    transition: color .12s ease;
  }}
  .st-key-cinav div[role="radiogroup"] > label:hover {{ background: rgba(11,78,200,.06); }}
  .st-key-cinav div[role="radiogroup"] > label:hover p {{ color: var(--azul-gov); }}
  .st-key-cinav div[role="radiogroup"] > label:has(input:checked) {{
    border-bottom-color: var(--azul-gov);
  }}
  .st-key-cinav div[role="radiogroup"] > label:has(input:checked) p {{
    color: var(--azul-gov); font-weight: 700;
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
  div[data-testid="stSidebarCollapsedControl"] {display: none !important;}
</style>
"""
