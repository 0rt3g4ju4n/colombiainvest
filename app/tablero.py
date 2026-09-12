# -*- coding: utf-8 -*-
"""Prototipo funcional de ColombiaInvest.

Alcance acordado con el grupo: carga de un conjunto acotado de proyectos
depurados, calculo del score, tablero de comparacion, visualizacion por
dimension y ponderacion configurable.

Fuera de alcance: integracion en tiempo real, pipeline automatizado,
autenticacion, despliegue productivo y escalamiento a otros municipios.

Ejecutar con:
    python -m streamlit run app/tablero.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "src"))
sys.path.insert(0, str(RAIZ / "app"))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
import streamlit as st  # noqa: E402

from colombiainvest.config import DIMENSIONES, DIR_PROCESADOS, cargar_modelo  # noqa: E402
from colombiainvest.modelo.score import aplicar_esquema, calcular_dimensiones  # noqa: E402
from colombiainvest.modelo.sensibilidad import (  # noqa: E402
    comparar_esquemas, contribucion_dimensiones,
)
from estilos import (  # noqa: E402
    CSS, OCULTAR_LATERAL, barra_peso, color_score, moneda, numero,
)

ETIQUETAS = {
    "viabilidad_financiera": "Viabilidad",
    "madurez_ejecucion": "Madurez",
    "impacto_social": "Impacto",
    "gobernanza": "Gobernanza",
    "atractivo_inversor": "Atractivo",
}
ETIQUETAS_LARGAS = {
    "viabilidad_financiera": "Viabilidad financiera",
    "madurez_ejecucion": "Madurez de ejecucion",
    "impacto_social": "Impacto social",
    "gobernanza": "Gobernanza",
    "atractivo_inversor": "Atractivo inversor",
}

SECCIONES = [
    "Quienes somos",
    "Proyectos",
    "Comparar",
    "Indicadores",
    "Contexto municipal",
    "Metodologia",
]

st.set_page_config(page_title="ColombiaInvest", page_icon="CI", layout="wide")
st.markdown(CSS, unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# Carga
# ---------------------------------------------------------------------------
@st.cache_data
def cargar_datos() -> pd.DataFrame:
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


@st.cache_resource
def cargar_cfg():
    return cargar_modelo()


@st.cache_data
def puntajes_dimension(_cfg, n: int) -> pd.DataFrame:
    puntajes, _ = calcular_dimensiones(cargar_datos(), _cfg)
    return puntajes[DIMENSIONES]


@st.cache_data
def contexto_cajica() -> pd.DataFrame | None:
    ruta = DIR_PROCESADOS / "informe_gestion_cajica_2024.json"
    if not ruta.exists():
        return None
    with open(ruta, encoding="utf-8") as f:
        return pd.DataFrame(json.load(f)["sectores"])


cfg = cargar_cfg()
df = cargar_datos()
puntajes = puntajes_dimension(cfg, len(df))

# ---------------------------------------------------------------------------
# Encabezado y navegacion
# ---------------------------------------------------------------------------
with st.container(key="cihead"):
    st.markdown(
        '<div class="ci-barra"><span class="marca">ColombiaInvest</span>'
        '<span class="lema">Analitica de proyectos de inversion publica</span>'
        '</div><div class="ci-franja"></div>',
        unsafe_allow_html=True,
    )
# Se usa segmented_control y no radio: el radio dibuja un circulo por opcion
# que habia que esconder con CSS apuntando a un hijo interno del widget, un
# parche fragil que cualquier cambio de Streamlit podia romper. El control
# segmentado no tiene circulo, es el widget pensado para elegir una seccion.
# required=True impide que el usuario deseleccione y quede sin seccion.
with st.container(key="cinav"):
    seccion = st.segmented_control(
        "Navegacion", SECCIONES, default=SECCIONES[0],
        selection_mode="single", required=True,
        label_visibility="collapsed",
    ) or SECCIONES[0]

# ---------------------------------------------------------------------------
# Ponderacion. La barra lateral solo existe donde hay algo que filtrar o
# ponderar; en las secciones de lectura se oculta por completo.
# ---------------------------------------------------------------------------
CON_LATERAL = ("Proyectos", "Comparar", "Indicadores")

if seccion not in CON_LATERAL:
    st.markdown(OCULTAR_LATERAL, unsafe_allow_html=True)
    esquema = st.session_state.get("esquema_activo", cfg.esquema_base)
    nombre_esquema = st.session_state.get("nombre_esquema", "esquema_base")
else:
    st.sidebar.markdown('<div class="ci-filtro-tit">Ponderacion del modelo</div>',
                        unsafe_allow_html=True)
    modo = st.sidebar.radio(
        "Esquema", ["Recomendado", "Por perfil", "Personalizado"],
        label_visibility="collapsed",
        help="Los pesos provienen de juicio experto y seran validados con entrevistas.",
    )
    if modo == "Recomendado":
        esquema, nombre_esquema = cfg.esquema_base, "esquema_base"
    elif modo == "Por perfil":
        alternativos = [e for e in cfg.esquemas_disponibles if e != "esquema_base"]
        nombre_esquema = st.sidebar.selectbox("Perfil de inversionista", alternativos)
        esquema = cfg.esquema(nombre_esquema)
        st.sidebar.caption(cfg.descripcion_esquema(nombre_esquema))
    else:
        nombre_esquema = "personalizado"
        crudos = {
            d: st.sidebar.slider(ETIQUETAS_LARGAS[d], 0.0, 1.0,
                                 float(cfg.esquema_base[d]), 0.05)
            for d in DIMENSIONES
        }
        total = sum(crudos.values())
        if total == 0:
            st.sidebar.error("Al menos un peso debe ser mayor que cero.")
            st.stop()
        esquema = {d: v / total for d, v in crudos.items()}

    st.session_state["esquema_activo"] = esquema
    st.session_state["nombre_esquema"] = nombre_esquema

# ---------------------------------------------------------------------------
# Score
# ---------------------------------------------------------------------------
base = df.copy()
for d in DIMENSIONES:
    base[f"p_{d}"] = puntajes[d].round(1)
base["score"] = aplicar_esquema(puntajes, esquema).round(1)
base["ranking"] = base["score"].rank(ascending=False, method="min").astype(int)
base = base.sort_values("score", ascending=False).reset_index(drop=True)


# ---------------------------------------------------------------------------
# Filtros tipo mercado, con conteo por faceta
# ---------------------------------------------------------------------------
def facetas(col: str, etiqueta: str, datos: pd.DataFrame) -> list[str]:
    """Casilla por valor, con el numero de proyectos al lado."""
    conteo = datos[col].dropna().value_counts()
    if conteo.empty:
        return []
    st.sidebar.markdown(f'<div class="ci-filtro-tit">{etiqueta}</div>',
                        unsafe_allow_html=True)
    escogidos = []
    largo = len(conteo) > 6
    caja = st.sidebar.expander(f"Ver {len(conteo)} opciones", expanded=not largo) \
        if largo else st.sidebar.container()
    with caja:
        for valor, n in conteo.items():
            if st.checkbox(f"{valor}  ({n})", value=False, key=f"f_{col}_{valor}"):
                escogidos.append(valor)
    return escogidos


if seccion in CON_LATERAL:
    sel_mun = facetas("municipio", "Municipio", base)
    sel_sec = facetas("sector", "Sector", base)
    if "tipo_intervencion" in base.columns:
        sel_tipo = facetas("tipo_intervencion", "Tipo de intervencion", base)
    else:
        sel_tipo = []

    st.sidebar.markdown('<div class="ci-filtro-tit">Calificacion</div>',
                        unsafe_allow_html=True)
    rango_score = st.sidebar.slider("Score", 0, 100, (0, 100), 5,
                                    label_visibility="collapsed")

    vista = base[base["score"].between(*rango_score)]
    if sel_mun:
        vista = vista[vista["municipio"].isin(sel_mun)]
    if sel_sec:
        vista = vista[vista["sector"].isin(sel_sec)]
    if sel_tipo:
        vista = vista[vista["tipo_intervencion"].isin(sel_tipo)]
else:
    sel_mun = sel_sec = sel_tipo = []
    rango_score = (0, 100)
    vista = base


def chips() -> None:
    aplicados = list(sel_mun) + list(sel_sec) + list(sel_tipo)
    if rango_score != (0, 100):
        aplicados.append(f"Score {rango_score[0]} a {rango_score[1]}")
    if aplicados:
        st.markdown(
            "".join(f'<span class="ci-chip">{a}</span>' for a in aplicados),
            unsafe_allow_html=True,
        )


def tarjeta(fila: pd.Series) -> str:
    col = color_score(fila["score"])
    barras = "".join(
        f'<div class="ci-fila"><span class="et">{ETIQUETAS[d]}</span>'
        f'<span class="pista"><span class="relleno" style="width:{fila[f"p_{d}"]:.0f}%;'
        f'background:{color_score(fila[f"p_{d}"])}"></span></span>'
        f'<span class="val">{fila[f"p_{d}"]:.0f}</span></div>'
        for d in DIMENSIONES
    )
    benef = fila.get("beneficiarios_declarados", 0) or 0
    tipo = fila.get("tipo_intervencion", "")
    nombre = str(fila["nombreproyecto"])[:105]
    return f"""
    <div class="ci-card">
      <div class="ci-card-top">
        <span class="ci-sector">{fila['sector']}</span>
        <span class="ci-score" style="background:{col}">{fila['score']:.0f}</span>
      </div>
      <div class="ci-titulo">{nombre}</div>
      <div class="ci-meta">{fila['municipio']} &middot; BPIN {fila['bpin']}
        {('&middot; ' + tipo) if tipo else ''}</div>
      <div class="ci-precio">{moneda(fila['valor_vigente_total'])}</div>
      <div class="ci-precio-nota">apropiacion vigente acumulada</div>
      <div class="ci-datos">
        <b>{numero(benef)}</b> beneficiarios declarados<br>
        <b>{fila['avancefisico']:.0f}%</b> de avance fisico &middot;
        puesto <b>{fila['ranking']}</b> de {len(base)}
      </div>
      <div class="ci-barras">{barras}</div>
    </div>"""


# ===========================================================================
# QUIENES SOMOS
# ===========================================================================
if seccion == "Quienes somos":
    st.markdown(
        '<div class="ci-hero"><h1>Existe oferta de datos publicos.<br>'
        "No existe oferta de analitica aplicada a la inversion publica "
        "territorial.</h1>"
        "<p>ColombiaInvest evalua, califica y compara proyectos de inversion "
        "publica de Chia y Cajica, para reducir la asimetria de informacion "
        "entre las entidades territoriales que estructuran los proyectos y el "
        "capital privado que podria financiarlos.</p></div>",
        unsafe_allow_html=True,
    )

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Proyectos calificados", numero(len(base)))
    c2.metric("Municipios", "2")
    c3.metric("Dimensiones de evaluacion", "5")
    c4.metric("Variables del modelo", "19")

    st.markdown("### El problema")
    a, b = st.columns(2)
    with a:
        st.markdown(
            '<div class="ci-panel"><h3>Para el inversionista privado</h3>'
            "<p>Revisar diez proyectos de Chia exige descargar informacion de "
            "tres fuentes distintas, construir por cuenta propia un criterio de "
            "comparacion y aplicarlo a mano. No hay calificacion, no hay "
            "ranking, no hay comparabilidad. El costo de busqueda y evaluacion "
            "es tan alto que el capital termina en alternativas ya "
            "consolidadas.</p></div>",
            unsafe_allow_html=True,
        )
    with b:
        st.markdown(
            '<div class="ci-panel"><h3>Para la entidad territorial</h3>'
            "<p>El municipio no sabe como se califican sus proyectos ni en que "
            "dimensiones falla su estructuracion. Cajica cerro 2024 con 92,5 % "
            "de avance fisico y 58,1 % de ejecucion presupuestal: una senal "
            "clara que hoy ninguna plataforma publica interpreta.</p></div>",
            unsafe_allow_html=True,
        )

    st.markdown("### Que hace la plataforma")
    cols = st.columns(5)
    textos = [
        ("Viabilidad financiera", "Si el proyecto tiene respaldo presupuestal real."),
        ("Madurez de ejecucion", "Que tan avanzado y estable esta."),
        ("Impacto social", "A cuantos beneficia y en que sectores."),
        ("Gobernanza", "Que tan confiable es la informacion del proyecto."),
        ("Atractivo inversor", "Senales de interes privado potencial."),
    ]
    for col, (tit, txt) in zip(cols, textos):
        col.markdown(f'<div class="ci-panel"><h3>{tit}</h3><p>{txt}</p></div>',
                     unsafe_allow_html=True)

    st.markdown(
        '<p class="ci-nota">Fuente: Sistema Unificado de Inversion y Finanzas '
        "Publicas del Departamento Nacional de Planeacion, con informacion "
        "complementaria de los municipios de Chia y Cajica.</p>",
        unsafe_allow_html=True,
    )
    st.markdown(
        '<p class="ci-nota">La calificacion es un instrumento de analisis. '
        "No es una recomendacion de inversion ni una certificacion de riesgo, "
        "y la plataforma no interviene en la captacion, custodia ni "
        "canalizacion de recursos.</p>",
        unsafe_allow_html=True,
    )

# ===========================================================================
# PROYECTOS
# ===========================================================================
elif seccion == "Proyectos":
    orden = {
        "Mayor calificacion": ("score", False),
        "Menor calificacion": ("score", True),
        "Mayor monto": ("valor_vigente_total", False),
        "Menor monto": ("valor_vigente_total", True),
        "Mayor avance fisico": ("avancefisico", False),
        "Mas beneficiarios": ("beneficiarios_declarados", False),
    }
    izq, der = st.columns([3, 1])
    with der:
        criterio = st.selectbox("Ordenar por", list(orden), label_visibility="collapsed")
    campo, asc = orden[criterio]
    if campo in vista.columns:
        vista = vista.sort_values(campo, ascending=asc)

    with izq:
        st.markdown(
            f'<div class="ci-resultados"><span class="conteo">'
            f"<b>{numero(len(vista))}</b> proyectos</span></div>",
            unsafe_allow_html=True,
        )
    chips()

    if vista.empty:
        st.markdown('<p class="ci-nota">Ningun proyecto cumple los filtros '
                    "aplicados. Ajuste la seleccion en el panel de la "
                    "izquierda.</p>", unsafe_allow_html=True)
    else:
        por_pagina = 24
        paginas = int(np.ceil(len(vista) / por_pagina))
        if paginas > 1:
            nav, _ = st.columns([1, 4])
            pag = nav.number_input(f"Pagina (de {paginas})", 1, paginas, 1)
        else:
            pag = 1
        trozo = vista.iloc[(pag - 1) * por_pagina: pag * por_pagina]

        for i in range(0, len(trozo), 4):
            for col, (_, fila) in zip(st.columns(4), trozo.iloc[i:i + 4].iterrows()):
                col.markdown(tarjeta(fila), unsafe_allow_html=True)
            st.write("")

        if paginas > 1:
            st.caption(f"Pagina {pag} de {paginas}")

        st.divider()
        with st.expander("Ver como tabla y descargar"):
            cols = (["ranking", "bpin", "municipio", "sector", "score"]
                    + [f"p_{d}" for d in DIMENSIONES]
                    + ["nombreproyecto", "valor_vigente_total", "beneficiarios_declarados"])
            cols = [c for c in cols if c in vista.columns]
            tabla = vista[cols].rename(
                columns={**{f"p_{d}": ETIQUETAS[d] for d in DIMENSIONES},
                         "nombreproyecto": "proyecto",
                         "valor_vigente_total": "apropiacion vigente",
                         "beneficiarios_declarados": "beneficiarios"})
            st.dataframe(
                tabla, hide_index=True, use_container_width=True, height=420,
                column_config={
                    "score": st.column_config.ProgressColumn(
                        "Score", min_value=0, max_value=100, format="%.1f"),
                    "apropiacion vigente": st.column_config.NumberColumn(
                        format="localized"),
                    "beneficiarios": st.column_config.NumberColumn(format="localized"),
                },
            )
            st.download_button(
                "Descargar CSV", tabla.to_csv(index=False).encode("utf-8-sig"),
                file_name="proyectos_colombiainvest.csv", mime="text/csv",
            )

# ===========================================================================
# COMPARAR
# ===========================================================================
elif seccion == "Comparar":
    st.subheader("Comparacion entre proyectos")
    if len(vista) < 2:
        st.markdown('<p class="ci-nota">Se requieren al menos dos proyectos. '
                    "Amplie los filtros.</p>", unsafe_allow_html=True)
    else:
        etiqueta = vista["bpin"] + "  |  " + vista["nombreproyecto"].str.slice(0, 70)
        opciones = dict(zip(etiqueta, vista["bpin"]))
        sel = st.multiselect("Seleccione entre dos y cuatro proyectos",
                             list(opciones), default=list(opciones)[:3],
                             max_selections=4)
        if len(sel) >= 2:
            bpins = [opciones[s] for s in sel]
            comp = vista[vista["bpin"].isin(bpins)].reset_index(drop=True)

            # Ficha en columnas: el texto queda horizontal y legible.
            for col, (_, fila) in zip(st.columns(len(comp)), comp.iterrows()):
                col.markdown(tarjeta(fila), unsafe_allow_html=True)

            st.markdown("#### Puntaje por dimension")
            st.caption("Una fila por dimension. Las barras crecen hacia la derecha, "
                       "de modo que las etiquetas se leen en horizontal.")
            for d in DIMENSIONES:
                st.markdown(f"**{ETIQUETAS_LARGAS[d]}**")
                for _, fila in comp.iterrows():
                    izq, med, der = st.columns([2.2, 5, 0.8])
                    izq.caption(f"{fila['bpin']}")
                    med.progress(min(float(fila[f"p_{d}"]) / 100, 1.0))
                    der.caption(f"{fila[f'p_{d}']:.0f}")
                st.write("")

            st.markdown("#### Cifras comparadas")
            filas = {
                "Score": [f"{r['score']:.1f}" for _, r in comp.iterrows()],
                "Puesto": [f"{r['ranking']} de {len(base)}" for _, r in comp.iterrows()],
                "Municipio": list(comp["municipio"]),
                "Sector": list(comp["sector"]),
                "Apropiacion vigente": [moneda(r["valor_vigente_total"]) for _, r in comp.iterrows()],
                "Ejecutado (pagado)": [moneda(r["valor_pagado_total"]) for _, r in comp.iterrows()],
                "Beneficiarios declarados": [numero(r.get("beneficiarios_declarados", 0)) for _, r in comp.iterrows()],
                "Avance fisico": [f"{r['avancefisico']:.1f} %" for _, r in comp.iterrows()],
                "Vigencias con apropiacion": [numero(r["n_vigencias_apropiadas"]) for _, r in comp.iterrows()],
                "Fuentes de financiacion": [numero(r["n_fuentes"]) for _, r in comp.iterrows()],
            }
            st.dataframe(pd.DataFrame(filas, index=list(comp["bpin"])).T,
                         use_container_width=True)

# ===========================================================================
# INDICADORES
# ===========================================================================
elif seccion == "Indicadores":
    st.subheader("Indicadores por dimension")
    chips()
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Proyectos", numero(len(vista)))
    c2.metric("Score medio", f"{vista['score'].mean():.1f}" if len(vista) else "n/d")
    c3.metric("Score maximo", f"{vista['score'].max():.1f}" if len(vista) else "n/d")
    c4.metric("Beneficiarios declarados",
              numero(vista["beneficiarios_declarados"].sum()) if len(vista) else "n/d")

    if len(vista):
        a, b = st.columns(2)
        with a:
            st.caption("Puntaje medio por dimension")
            medias = pd.DataFrame(
                {"puntaje": [vista[f"p_{d}"].mean() for d in DIMENSIONES]},
                index=[ETIQUETAS_LARGAS[d] for d in DIMENSIONES])
            st.bar_chart(medias, height=330, horizontal=True)
        with b:
            st.caption("Distribucion del score")
            h = np.histogram(vista["score"], bins=20, range=(0, 100))
            st.bar_chart(pd.DataFrame({"proyectos": h[0]},
                                      index=[f"{int(x)}" for x in h[1][:-1]]), height=330)

        st.markdown("#### Diagnostico por municipio")
        st.caption("En que dimensiones es mas debil cada territorio. "
                   "Es la lectura que le sirve a la entidad territorial.")
        por_mun = vista.groupby("municipio")[[f"p_{d}" for d in DIMENSIONES]].mean().round(1)
        por_mun.columns = [ETIQUETAS_LARGAS[d] for d in DIMENSIONES]
        st.dataframe(por_mun, use_container_width=True)

        st.markdown("#### Desempeno por sector")
        por_sec = vista.groupby("sector").agg(
            proyectos=("bpin", "size"), score_medio=("score", "mean"),
            avance_medio=("avancefisico", "mean"),
            apropiacion=("valor_vigente_total", "sum")).round(1)
        por_sec = por_sec.sort_values("score_medio", ascending=False)
        por_sec["apropiacion"] = por_sec["apropiacion"].map(moneda)
        st.dataframe(por_sec, use_container_width=True)

# ===========================================================================
# CONTEXTO MUNICIPAL
# ===========================================================================
elif seccion == "Contexto municipal":
    st.subheader("Estado de la inversion por municipio")
    st.caption(
        "Ejecucion presupuestal calculada desde el SUIFP del DNP, disponible "
        "para los dos municipios y por tanto comparable entre ellos. Las "
        "cifras son apropiacion ACUMULADA sobre todas las vigencias de cada "
        "proyecto, no presupuesto de un solo ano."
    )

    resumen = base.groupby("municipio").agg(
        proyectos=("bpin", "size"),
        programado=("valor_vigente_total", "sum"),
        obligado=("valor_obligado_total", "sum"),
        ejecutado=("valor_pagado_total", "sum"),
        avance_fisico=("avancefisico", "mean"),
        score_medio=("score", "mean"),
    )
    resumen["% ejecutado sobre programado"] = (
        100 * resumen["ejecutado"] / resumen["programado"]).round(1)
    resumen["% obligado sobre programado"] = (
        100 * resumen["obligado"] / resumen["programado"]).round(1)
    resumen["brecha fisico menos financiero"] = (
        resumen["avance_fisico"] - resumen["% ejecutado sobre programado"]).round(1)
    resumen = resumen.round(1)

    cols = st.columns(len(resumen))
    for col, (mun, r) in zip(cols, resumen.iterrows()):
        col.markdown(
            f'<div class="ci-panel"><h3>{mun}</h3><p>'
            f"<b>{numero(r['proyectos'])}</b> proyectos<br>"
            f"Apropiado: <b>{moneda(r['programado'], corto=True)}</b><br>"
            f"Ejecutado: <b>{moneda(r['ejecutado'], corto=True)}</b><br>"
            f"<b>{r['% ejecutado sobre programado']:.1f} %</b> de ejecucion<br>"
            f"<b>{r['avance_fisico']:.1f} %</b> de avance fisico medio"
            "</p></div>",
            unsafe_allow_html=True,
        )

    st.markdown("#### Comparativo")
    tabla_res = resumen.copy()
    for c in ("programado", "obligado", "ejecutado"):
        tabla_res[c] = tabla_res[c].map(moneda)
    st.dataframe(tabla_res, use_container_width=True)

    st.markdown("#### Ejecucion por sector y municipio")
    por = base.groupby(["municipio", "sector"]).agg(
        proyectos=("bpin", "size"),
        programado=("valor_vigente_total", "sum"),
        ejecutado=("valor_pagado_total", "sum")).reset_index()
    por["% ejecutado"] = (100 * por["ejecutado"] / por["programado"]).round(1)
    por = por.sort_values("% ejecutado")
    for c in ("programado", "ejecutado"):
        por[c] = por[c].map(moneda)
    st.dataframe(por, hide_index=True, use_container_width=True, height=420)

    st.divider()
    st.markdown("#### Informe de Gestion de Cajica 2024")
    ctx = contexto_cajica()
    if ctx is None:
        st.markdown('<p class="ci-nota">Ejecute <code>python '
                    "scripts/04_documentos.py</code> para generar esta "
                    "seccion.</p>", unsafe_allow_html=True)
    else:
        st.caption(
            "Solo existe para Cajica y solo para 2024, por lo que no alimenta "
            "el score ni permite comparacion con Chia. Se muestra como "
            "contexto declarado por el propio municipio."
        )
        ctx = ctx.copy()
        ctx["% ejecutado sobre programado"] = (
            100 * ctx["recursos_ejecutados"] / ctx["recursos_programados"]).round(1)
        ctx = ctx.sort_values("brecha_sector", ascending=False)
        for c in ("recursos_programados", "recursos_ejecutados"):
            ctx[c] = ctx[c].map(moneda)
        st.dataframe(
            ctx[["sector_informe", "avance_fisico_sector",
                 "ejecucion_presupuestal_sector", "% ejecutado sobre programado",
                 "brecha_sector", "recursos_programados", "recursos_ejecutados"]]
            .rename(columns={
                "sector_informe": "sector",
                "avance_fisico_sector": "avance fisico %",
                "ejecucion_presupuestal_sector": "ejecucion reportada %",
                "brecha_sector": "brecha (puntos)",
                "recursos_programados": "programado",
                "recursos_ejecutados": "ejecutado"}),
            hide_index=True, use_container_width=True, height=440,
        )
        peor = ctx.iloc[0]
        st.markdown(
            f'<p class="ci-nota">Mayor brecha: <b>{peor["sector_informe"]}</b>, '
            f'con {peor["avance_fisico_sector"]:.1f} % de avance fisico frente '
            f'a {peor["ejecucion_presupuestal_sector"]:.1f} % de ejecucion '
            "presupuestal.</p>",
            unsafe_allow_html=True,
        )

# ===========================================================================
# METODOLOGIA
# ===========================================================================
elif seccion == "Metodologia":
    st.subheader("Como se construye la calificacion")
    st.markdown(
        "El modelo es una **calificacion compuesta ponderada**, no un modelo de "
        "aprendizaje supervisado. No hay variable objetivo ni fase de "
        "entrenamiento: los pesos provienen de juicio experto y se validaran "
        "con entrevistas a profesionales en gestion de proyectos."
    )
    st.latex(
        r"Score = \sum_{d=1}^{5} w_d \cdot P_d, \qquad \sum_{d=1}^{5} w_d = 1"
    )

    st.markdown("#### Pesos aplicados")
    st.markdown(
        "".join(barra_peso(ETIQUETAS_LARGAS[d], esquema[d], ancho=True)
                for d in DIMENSIONES),
        unsafe_allow_html=True,
    )

    st.markdown("#### Contribucion de cada dimension a la varianza del score")
    st.caption("Si una dimension aporta poca varianza, su peso es decorativo. "
               "Este diagnostico ya obligo a corregir tres variables.")
    st.dataframe(contribucion_dimensiones(df, cfg).round(4),
                 hide_index=True, use_container_width=True)

    st.markdown("#### Estabilidad del ranking frente a la ponderacion")
    st.caption(
        "Recalcula el score bajo esquemas alternativos y mide cuanto cambia el "
        "orden. Correlaciones de Spearman cercanas a 1 indican que el ranking "
        "no depende del juicio experto particular que se haya elegido."
    )
    with st.spinner("Recalculando..."):
        metricas, _ = comparar_esquemas(df, cfg)
    st.dataframe(
        metricas[["esquema", "spearman", "kendall_tau", "desplaz_medio",
                  "desplaz_max", "top10_estable", "top20_estable"]].round(4),
        hide_index=True, use_container_width=True,
    )
    for _, r in metricas.iterrows():
        st.caption(f"**{r['esquema']}**: {r['descripcion']}")

    st.markdown("#### Limitaciones declaradas")
    st.markdown(
        "- Los beneficiarios son cifra declarada en la formulacion MGA, no "
        "verificada. 188 de los 491 proyectos declaran mas beneficiarios que "
        "habitantes tiene el municipio, por lo que se usan como cobertura "
        "poblacional con tope y no como conteo.\n"
        "- Los documentos municipales cubren 79 de 491 proyectos y ninguno de "
        "Chia, por lo que no alimentan el score.\n"
        "- No existe llave comun entre proyecto y contrato de SECOP. El cruce "
        "por texto esta pendiente.\n"
        "- La poblacion municipal usada esta pendiente de verificar contra "
        "TerriData."
    )

st.divider()
st.caption(
    "Prototipo academico. Trabajo de grado, Maestria en Ciencia de Datos, "
    "Universidad EAN. Datos de fuentes publicas oficiales, con inconsistencias "
    "de origen documentadas en docs/."
)
