# -*- coding: utf-8 -*-
"""Prototipo funcional de ColombiaInvest.

Alcance deliberadamente acotado, segun lo acordado por el grupo:
carga de un conjunto depurado de proyectos, calculo del score, tablero de
comparacion, visualizacion por dimension y ponderacion configurable.

Fuera de alcance: integracion en tiempo real, pipeline automatizado,
autenticacion, despliegue productivo y escalamiento a otros municipios.

Ejecutar con:
    streamlit run app/tablero.py
"""
from __future__ import annotations

import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "src"))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
import streamlit as st  # noqa: E402

from colombiainvest.config import DIMENSIONES, DIR_PROCESADOS, cargar_modelo  # noqa: E402
from colombiainvest.modelo.score import calcular_dimensiones, aplicar_esquema  # noqa: E402
from colombiainvest.modelo.sensibilidad import comparar_esquemas  # noqa: E402

ETIQUETAS = {
    "viabilidad_financiera": "Viabilidad financiera",
    "madurez_ejecucion": "Madurez de ejecucion",
    "impacto_social": "Impacto social",
    "gobernanza": "Gobernanza",
    "atractivo_inversor": "Atractivo inversor",
}

st.set_page_config(page_title="ColombiaInvest", page_icon="CI", layout="wide")


@st.cache_data
def cargar_datos() -> pd.DataFrame:
    """Prefiere el dataset enriquecido con documentos municipales si existe.

    El enriquecimiento es asimetrico (solo Cajica 2024), por eso solo alimenta
    la ficha del proyecto y nunca el score.
    """
    enriquecido = DIR_PROCESADOS / "proyectos_enriquecidos.parquet"
    base = DIR_PROCESADOS / "proyectos_evaluables.parquet"
    ruta = enriquecido if enriquecido.exists() else base
    if not ruta.exists():
        st.error(
            "No existe el dataset procesado. Ejecute primero:\n\n"
            "python scripts/01_ingesta.py\npython scripts/02_dataset.py"
        )
        st.stop()
    return pd.read_parquet(ruta)


@st.cache_data
def cargar_contexto_municipal() -> pd.DataFrame | None:
    """Avance por sector del informe de gestion de Cajica 2024."""
    ruta = DIR_PROCESADOS / "informe_gestion_cajica_2024.json"
    if not ruta.exists():
        return None
    import json

    with open(ruta, encoding="utf-8") as f:
        datos = json.load(f)
    return pd.DataFrame(datos["sectores"])


@st.cache_resource
def cargar_cfg():
    return cargar_modelo()


@st.cache_data
def puntajes_dimension(_cfg, n_filas: int) -> pd.DataFrame:
    df = cargar_datos()
    puntajes, _ = calcular_dimensiones(df, _cfg)
    return puntajes[DIMENSIONES]


cfg = cargar_cfg()
df = cargar_datos()
puntajes = puntajes_dimension(cfg, len(df))

# ---------------------------------------------------------------------------
# Barra lateral: ponderacion configurable
# ---------------------------------------------------------------------------
st.sidebar.title("ColombiaInvest")
st.sidebar.caption("Modelo de calificacion compuesta de proyectos de inversion publica")

st.sidebar.subheader("Ponderacion")
modo = st.sidebar.radio(
    "Esquema de pesos",
    ["Esquema base", "Esquema predefinido", "Ajuste manual"],
    help="Los pesos provienen de juicio experto y son configurables. "
         "Seran validados con entrevistas a expertos.",
)

if modo == "Esquema base":
    esquema = cfg.esquema_base
    nombre_esquema = "esquema_base"
elif modo == "Esquema predefinido":
    alternativos = [e for e in cfg.esquemas_disponibles if e != "esquema_base"]
    nombre_esquema = st.sidebar.selectbox("Perfil", alternativos)
    esquema = cfg.esquema(nombre_esquema)
    st.sidebar.info(cfg.descripcion_esquema(nombre_esquema))
else:
    nombre_esquema = "manual"
    crudos = {}
    for d in DIMENSIONES:
        crudos[d] = st.sidebar.slider(
            ETIQUETAS[d], 0.0, 1.0, float(cfg.esquema_base[d]), 0.05
        )
    total = sum(crudos.values())
    if total == 0:
        st.sidebar.error("Al menos un peso debe ser mayor que cero.")
        st.stop()
    esquema = {d: v / total for d, v in crudos.items()}
    st.sidebar.caption(f"Pesos renormalizados (sumaban {total:.2f})")

with st.sidebar.expander("Pesos aplicados"):
    st.dataframe(
        pd.DataFrame({"dimension": [ETIQUETAS[d] for d in DIMENSIONES],
                      "peso": [round(esquema[d], 3) for d in DIMENSIONES]}),
        hide_index=True, use_container_width=True,
    )

# ---------------------------------------------------------------------------
# Calculo del score con el esquema activo
# ---------------------------------------------------------------------------
base = df.copy()
for d in DIMENSIONES:
    base[f"p_{d}"] = puntajes[d].round(2)
base["score"] = aplicar_esquema(puntajes, esquema).round(2)
base["ranking"] = base["score"].rank(ascending=False, method="min").astype(int)
base = base.sort_values("score", ascending=False).reset_index(drop=True)

# ---------------------------------------------------------------------------
# Filtros
# ---------------------------------------------------------------------------
st.sidebar.subheader("Filtros")
municipios = sorted(base["municipio"].dropna().unique())
sel_mun = st.sidebar.multiselect("Municipio", municipios, default=municipios)
sectores = sorted(base["sector"].dropna().unique())
sel_sec = st.sidebar.multiselect("Sector", sectores, default=[])
rango_score = st.sidebar.slider("Score minimo", 0, 100, 0, 5)

vista = base[base["municipio"].isin(sel_mun) & (base["score"] >= rango_score)]
if sel_sec:
    vista = vista[vista["sector"].isin(sel_sec)]

# ---------------------------------------------------------------------------
# Cuerpo
# ---------------------------------------------------------------------------
st.title("Calificacion de proyectos de inversion publica")
st.caption(
    "Caso de aplicacion: Chia y Cajica. Fuente: SUIFP del DNP via datos.gov.co. "
    "La calificacion es un instrumento de analisis, no una recomendacion de "
    "inversion ni una certificacion de riesgo."
)

c1, c2, c3, c4 = st.columns(4)
c1.metric("Proyectos", f"{len(vista):,}")
c2.metric("Score medio", f"{vista['score'].mean():.1f}" if len(vista) else "n/a")
c3.metric("Score maximo", f"{vista['score'].max():.1f}" if len(vista) else "n/a")
valor_total = vista["valor_vigente_total"].sum() / 1e9 if len(vista) else 0
c4.metric("Valor vigente", f"${valor_total:,.1f} mm")

tab1, tab2, tab3, tab4, tab5 = st.tabs(
    ["Ranking", "Comparar proyectos", "Perfil por dimension", "Sensibilidad",
     "Contexto municipal"]
)

# --- Ranking ---------------------------------------------------------------
with tab1:
    cols = ["ranking", "bpin", "municipio", "sector", "score"] + [f"p_{d}" for d in DIMENSIONES]
    extra = ["nombreproyecto", "valor_vigente_total"]
    if "responsable_pdm" in vista.columns:
        extra.append("responsable_pdm")
    tabla = vista[cols + extra].copy()
    tabla = tabla.rename(columns={**{f"p_{d}": ETIQUETAS[d] for d in DIMENSIONES},
                                  "nombreproyecto": "proyecto",
                                  "valor_vigente_total": "valor vigente",
                                  "responsable_pdm": "dependencia responsable"})
    st.dataframe(
        tabla, hide_index=True, use_container_width=True, height=520,
        column_config={
            "score": st.column_config.ProgressColumn("Score", min_value=0, max_value=100, format="%.1f"),
            "valor vigente": st.column_config.NumberColumn("Valor vigente", format="$ %.0f"),
        },
    )
    st.download_button(
        "Descargar ranking en CSV",
        tabla.to_csv(index=False).encode("utf-8-sig"),
        file_name="ranking_colombiainvest.csv",
        mime="text/csv",
    )

# --- Comparacion -----------------------------------------------------------
with tab2:
    st.subheader("Comparacion entre proyectos")
    if len(vista) < 2:
        st.info("Se requieren al menos dos proyectos en el filtro.")
    else:
        etiqueta = vista["bpin"] + "  |  " + vista["nombreproyecto"].str.slice(0, 60)
        opciones = dict(zip(etiqueta, vista["bpin"]))
        sel = st.multiselect(
            "Seleccione entre dos y cinco proyectos",
            list(opciones), default=list(opciones)[:3], max_selections=5,
        )
        if len(sel) >= 2:
            bpins = [opciones[s] for s in sel]
            comp = vista[vista["bpin"].isin(bpins)].set_index("bpin")
            perfil = comp[[f"p_{d}" for d in DIMENSIONES]].T
            perfil.index = [ETIQUETAS[d] for d in DIMENSIONES]
            # stack=False: barras agrupadas. Apiladas darian a entender que
            # las dimensiones se suman entre proyectos, que es falso.
            st.bar_chart(perfil, height=380, stack=False)
            st.dataframe(
                comp[["nombreproyecto", "municipio", "sector", "score"]
                     + [f"p_{d}" for d in DIMENSIONES]].rename(
                    columns={f"p_{d}": ETIQUETAS[d] for d in DIMENSIONES}),
                use_container_width=True,
            )

# --- Perfil por dimension --------------------------------------------------
with tab3:
    st.subheader("Indicadores por dimension")
    ca, cb = st.columns(2)
    with ca:
        st.caption("Puntaje medio por dimension")
        medias = pd.DataFrame({
            "dimension": [ETIQUETAS[d] for d in DIMENSIONES],
            "puntaje": [vista[f"p_{d}"].mean() for d in DIMENSIONES],
        }).set_index("dimension")
        st.bar_chart(medias, height=320)
    with cb:
        st.caption("Distribucion del score")
        hist = np.histogram(vista["score"], bins=20, range=(0, 100))
        st.bar_chart(
            pd.DataFrame({"frecuencia": hist[0]},
                         index=[f"{int(b)}" for b in hist[1][:-1]]),
            height=320,
        )

    st.caption("Diagnostico por municipio: en que dimensiones esta mas debil cada territorio")
    por_mun = vista.groupby("municipio")[[f"p_{d}" for d in DIMENSIONES]].mean().round(1)
    por_mun.columns = [ETIQUETAS[d] for d in DIMENSIONES]
    st.dataframe(por_mun, use_container_width=True)

    st.caption("Puntaje medio por sector")
    por_sec = vista.groupby("sector")[["score"]].agg(["count", "mean"]).round(1)
    por_sec.columns = ["proyectos", "score medio"]
    st.dataframe(por_sec.sort_values("score medio", ascending=False), use_container_width=True)

# --- Sensibilidad ----------------------------------------------------------
with tab4:
    st.subheader("Estabilidad del ranking frente a la ponderacion")
    st.caption(
        "Los pesos provienen de juicio experto. Este ejercicio mide cuanto "
        "cambia el ranking si el juicio fuera distinto. Correlaciones de "
        "Spearman cercanas a 1 indican que el orden es robusto."
    )
    with st.spinner("Recalculando el score bajo cada esquema..."):
        metricas, _ = comparar_esquemas(df, cfg)
    st.dataframe(
        metricas[["esquema", "spearman", "kendall_tau", "desplaz_medio",
                  "desplaz_max", "top10_estable", "top20_estable"]].round(4),
        hide_index=True, use_container_width=True,
    )
    for _, r in metricas.iterrows():
        st.caption(f"**{r['esquema']}**: {r['descripcion']}")

# --- Contexto municipal ----------------------------------------------------
with tab5:
    st.subheader("Contexto del Plan de Desarrollo, Cajica 2024")
    st.caption(
        "Fuente: Informe de Gestion 2024 del municipio de Cajica. Esta "
        "informacion NO alimenta el score: solo existe para Cajica y solo "
        "para 2024, de modo que incluirla premiaria a unos proyectos por "
        "disponibilidad documental y no por merito. Se muestra como contexto."
    )
    ctx = cargar_contexto_municipal()
    if ctx is None:
        st.info("Ejecute `python scripts/04_documentos.py` para generar este contexto.")
    else:
        st.markdown(
            "**Brecha entre avance fisico y ejecucion presupuestal, por sector.** "
            "Es el fenomeno que el anteproyecto describe con la cifra agregada "
            "de 92,5 % contra 58,1 %, aqui desagregado en 18 sectores."
        )
        ctx_v = ctx.sort_values("brecha_sector", ascending=False)
        st.dataframe(
            ctx_v[["sector_informe", "avance_fisico_sector",
                   "ejecucion_presupuestal_sector", "brecha_sector",
                   "recursos_programados", "recursos_ejecutados"]].rename(columns={
                "sector_informe": "sector",
                "avance_fisico_sector": "avance fisico %",
                "ejecucion_presupuestal_sector": "ejecucion presupuestal %",
                "brecha_sector": "brecha (puntos)",
                "recursos_programados": "programado",
                "recursos_ejecutados": "ejecutado",
            }),
            hide_index=True, use_container_width=True, height=460,
            column_config={
                "programado": st.column_config.NumberColumn(format="$ %.0f"),
                "ejecutado": st.column_config.NumberColumn(format="$ %.0f"),
            },
        )
        st.bar_chart(
            ctx_v.set_index("sector_informe")[
                ["avance_fisico_sector", "ejecucion_presupuestal_sector"]
            ], height=380, stack=False,
        )
        peor = ctx_v.iloc[0]
        st.warning(
            f"Sector con mayor brecha: **{peor['sector_informe']}**, con "
            f"{peor['avance_fisico_sector']:.1f} % de avance fisico frente a "
            f"{peor['ejecucion_presupuestal_sector']:.1f} % de ejecucion "
            "presupuestal. Es justamente el tipo de senal que ninguna "
            "plataforma publica interpreta hoy."
        )

st.divider()
st.caption(
    "Prototipo academico. Trabajo de grado, Maestria en Ciencia de Datos, "
    "Universidad EAN. Los datos provienen de fuentes publicas oficiales y "
    "pueden contener inconsistencias de origen documentadas en docs/."
)
