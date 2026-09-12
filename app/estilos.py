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
    "gris_fondo": "#F4F4F4",
    "gris_borde": "#DDE1E6",
    "gris_texto": "#5E5E5E",
    "blanco": "#FFFFFF",
    "texto": "#1A1A1A",
    "verde": "#069169",
    "amarillo": "#E8B000",
    "rojo": "#A80521",
}

# Color del score segun tramo. Verde alto, amarillo medio, rojo bajo.
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
    # coma de miles a punto, punto decimal a coma
    return s.replace(",", "␟").replace(".", ",").replace("␟", ".")


CSS = f"""
<style>
  :root {{
    --azul-gov: {PALETA['azul_gov']};
    --azul-oscuro: {PALETA['azul_oscuro']};
    --naranja: {PALETA['naranja']};
    --azul-claro: {PALETA['azul_claro']};
    --gris-fondo: {PALETA['gris_fondo']};
    --gris-borde: {PALETA['gris_borde']};
    --gris-texto: {PALETA['gris_texto']};
    --texto: {PALETA['texto']};
  }}

  .block-container {{ padding-top: 1.2rem; max-width: 1500px; }}

  /* ---------- barra superior ---------- */
  .ci-barra {{
    background: var(--azul-gov);
    color: #fff;
    padding: 10px 20px;
    border-radius: 6px 6px 0 0;
    display: flex; align-items: baseline; gap: 14px;
    font-family: Roboto, "Segoe UI", sans-serif;
  }}
  .ci-barra .marca {{ font-size: 1.35rem; font-weight: 800; letter-spacing: -0.3px; }}
  .ci-barra .lema {{ font-size: 0.82rem; opacity: 0.92; }}
  .ci-franja {{
    height: 5px; border-radius: 0 0 6px 6px; margin-bottom: 14px;
    background: linear-gradient(90deg,
      var(--azul-oscuro) 0 33%, var(--naranja) 33% 66%, var(--azul-claro) 66% 100%);
  }}

  /* ---------- navegacion superior ----------
     Se estila solo el contenedor con key "cinav", para no afectar los
     demas radios de la aplicacion. */
  .st-key-cinav div[role="radiogroup"] {{
    flex-direction: row; gap: 2px; flex-wrap: wrap;
    border-bottom: 2px solid var(--gris-borde);
    margin-bottom: 16px;
  }}
  .st-key-cinav div[role="radiogroup"] > label {{
    background: transparent; border: none;
    border-bottom: 3px solid transparent;
    padding: 9px 18px 10px 18px; margin: 0 0 -2px 0;
    font-weight: 600; cursor: pointer; transition: all .12s ease;
  }}
  .st-key-cinav div[role="radiogroup"] > label > div:first-child {{
    display: none !important;   /* oculta el circulo del radio */
  }}
  .st-key-cinav div[role="radiogroup"] > label p {{
    font-size: .93rem; font-weight: 600; color: var(--gris-texto);
    transition: color .12s ease;
  }}
  .st-key-cinav div[role="radiogroup"] > label:hover {{
    background: rgba(11,78,200,.06);
  }}
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
    padding: 14px 16px 12px 16px;
    /* altura fija para que la cuadricula quede pareja, como en una vitrina */
    min-height: 400px; display: flex; flex-direction: column;
    box-shadow: 0 1px 3px rgba(0,0,0,.06);
    transition: box-shadow .15s ease, border-color .15s ease;
    font-family: Roboto, "Segoe UI", sans-serif;
  }}
  .ci-card .ci-barras {{ margin-top: auto; padding-top: 10px; }}
  .ci-card:hover {{ box-shadow: 0 4px 14px rgba(0,0,0,.12); border-color: var(--azul-claro); }}
  .ci-card-top {{ display: flex; justify-content: space-between; align-items: flex-start; gap: 8px; }}
  .ci-sector {{
    background: var(--gris-fondo); color: var(--gris-texto);
    font-size: .68rem; font-weight: 700; letter-spacing: .3px;
    padding: 3px 8px; border-radius: 3px; text-transform: uppercase;
  }}
  .ci-score {{
    color: #fff; font-weight: 800; font-size: 1.05rem;
    padding: 4px 10px; border-radius: 4px; white-space: nowrap;
  }}
  .ci-titulo {{
    font-size: .95rem; font-weight: 600; line-height: 1.32; color: var(--texto);
    margin: 10px 0 6px 0; min-height: 2.6em;
  }}
  .ci-meta {{ font-size: .74rem; color: var(--gris-texto); margin-bottom: 8px; }}
  .ci-precio {{
    font-size: 1.32rem; font-weight: 300; color: var(--texto); line-height: 1.1;
  }}
  .ci-precio-nota {{ font-size: .7rem; color: var(--gris-texto); margin-bottom: 10px; }}
  .ci-datos {{ font-size: .78rem; color: var(--texto); line-height: 1.6; }}
  .ci-datos b {{ font-weight: 600; }}
  .ci-barras {{ margin-top: 10px; }}
  .ci-fila {{ display: flex; align-items: center; gap: 6px; margin-bottom: 3px; }}
  .ci-fila .et {{ font-size: .66rem; color: var(--gris-texto); width: 74px; flex: none; }}
  .ci-fila .pista {{ flex: 1; height: 6px; background: var(--gris-fondo); border-radius: 3px; overflow: hidden; }}
  .ci-fila .relleno {{ height: 100%; border-radius: 3px; }}
  .ci-fila .val {{ font-size: .66rem; color: var(--gris-texto); width: 24px; text-align: right; flex: none; }}

  /* ---------- resumen de resultados ---------- */
  .ci-resultados {{
    display: flex; justify-content: space-between; align-items: center;
    padding: 6px 2px 12px 2px; border-bottom: 1px solid var(--gris-borde);
    margin-bottom: 14px; font-family: Roboto, "Segoe UI", sans-serif;
  }}
  .ci-resultados .conteo {{ font-size: .95rem; color: var(--texto); }}
  .ci-resultados .conteo b {{ font-weight: 700; }}

  /* ---------- chips de filtro aplicado ---------- */
  .ci-chip {{
    display: inline-block; background: rgba(11,78,200,.08); color: var(--azul-gov);
    border: 1px solid rgba(11,78,200,.25); border-radius: 14px;
    padding: 2px 10px; font-size: .74rem; font-weight: 600; margin: 0 5px 5px 0;
  }}

  /* ---------- bloque de contenido institucional ---------- */
  .ci-hero {{
    background: linear-gradient(110deg, var(--azul-oscuro), var(--azul-gov));
    color: #fff; padding: 30px 34px; border-radius: 8px; margin-bottom: 20px;
    font-family: Roboto, "Segoe UI", sans-serif;
  }}
  .ci-hero h1 {{ font-size: 1.9rem; margin: 0 0 10px 0; font-weight: 800; line-height: 1.2; }}
  .ci-hero p {{ font-size: 1rem; opacity: .95; margin: 0; line-height: 1.55; max-width: 70ch; }}
  .ci-panel {{
    background: #fff; border: 1px solid var(--gris-borde); border-left: 4px solid var(--naranja);
    border-radius: 6px; padding: 16px 18px; margin-bottom: 12px;
  }}
  .ci-panel h3 {{ margin: 0 0 8px 0; font-size: 1.02rem; color: var(--azul-oscuro); }}
  .ci-panel p {{ margin: 0; font-size: .88rem; line-height: 1.6; color: var(--texto); }}

  /* ---------- barra lateral ---------- */
  section[data-testid="stSidebar"] {{ background: #fff; border-right: 1px solid var(--gris-borde); }}
  section[data-testid="stSidebar"] h2 {{ font-size: 1rem; }}
  .ci-filtro-tit {{
    font-size: .78rem; font-weight: 700; text-transform: uppercase;
    letter-spacing: .4px; color: var(--gris-texto);
    margin: 14px 0 4px 0; padding-bottom: 4px; border-bottom: 1px solid var(--gris-borde);
  }}
</style>
"""
