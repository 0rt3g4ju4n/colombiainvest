# -*- coding: utf-8 -*-
"""Ponderacion por proceso analitico jerarquico (AHP) con panel de expertos.

Especificacion de la direccion (v3 ajustada, OE2 y pregunta 10 del jurado):
- Cada experto compara por pares las cinco dimensiones en la escala de
  Saaty (1 a 9). Con cinco dimensiones son diez comparaciones.
- Se exige razon de consistencia (CR) menor que 0,10 por evaluador.
- Los juicios individuales se agregan por media geometrica elemento a
  elemento (agregacion de juicios individuales, AIJ), que preserva la
  reciprocidad de la matriz.
- La concordancia entre evaluadores se mide con la W de Kendall.

Referencias: Saaty (1980, 2008) para la escala, el vector propio principal,
el indice de consistencia y el indice aleatorio; Kendall y Babington Smith
(1939) para la W. Los pesos resultantes son un RESULTADO del trabajo, no un
insumo: este modulo no contiene pesos, solo los calcula a partir de las
respuestas del panel.
"""
from __future__ import annotations

from itertools import combinations
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd
from scipy import stats

# Indice aleatorio de Saaty por tamano de matriz (Saaty, 1980).
INDICE_ALEATORIO = {1: 0.0, 2: 0.0, 3: 0.58, 4: 0.90, 5: 1.12,
                    6: 1.24, 7: 1.32, 8: 1.41, 9: 1.45, 10: 1.49}

ESCALA_SAATY = (1, 2, 3, 4, 5, 6, 7, 8, 9)
COLUMNAS = ["experto", "perfil", "fecha", "dimension_a", "dimension_b",
            "preferida", "intensidad"]


# ---------------------------------------------------------------------------
# matrices
# ---------------------------------------------------------------------------
def pares(elementos: Sequence[str]) -> List[Tuple[str, str]]:
    """Las n(n-1)/2 comparaciones, en orden fijo."""
    return list(combinations(elementos, 2))


def valor_juicio(preferida: str, intensidad: float) -> float:
    """Convierte (preferida, intensidad) en el valor a_ij de la matriz.

    preferida 'A': la dimension A es 'intensidad' veces mas importante.
    preferida 'B': la dimension B lo es, luego a_ij = 1 / intensidad.
    preferida '=': igual importancia, a_ij = 1.
    """
    p = str(preferida).strip().upper()
    k = float(intensidad)
    if p in ("=", "IGUAL", "I"):
        return 1.0
    if k not in ESCALA_SAATY:
        raise ValueError(f"Intensidad {intensidad} fuera de la escala de Saaty (1 a 9)")
    if p == "A":
        return k
    if p == "B":
        return 1.0 / k
    raise ValueError(f"Preferida debe ser A, B o '=' y se recibio '{preferida}'")


def matriz_desde_juicios(juicios: Dict[Tuple[str, str], float],
                         elementos: Sequence[str]) -> np.ndarray:
    """Matriz reciproca a partir de los juicios del triangulo superior."""
    n = len(elementos)
    pos = {e: i for i, e in enumerate(elementos)}
    a = np.ones((n, n))
    for (x, y), v in juicios.items():
        i, j = pos[x], pos[y]
        a[i, j] = v
        a[j, i] = 1.0 / v
    return a


def prioridades(a: np.ndarray) -> Tuple[np.ndarray, float]:
    """Vector propio principal normalizado y autovalor maximo (Saaty)."""
    valores, vectores = np.linalg.eig(a)
    k = int(np.argmax(valores.real))
    w = np.abs(vectores[:, k].real)
    return w / w.sum(), float(valores[k].real)


def razon_consistencia(a: np.ndarray) -> Tuple[float, float, float]:
    """(CR, CI, lambda_max). CR = CI / RI, CI = (lambda_max - n) / (n - 1)."""
    n = a.shape[0]
    _, lmax = prioridades(a)
    if n < 3:
        return 0.0, 0.0, lmax
    # El redondeo numerico puede dar un CI negativo minimo en matrices
    # perfectamente consistentes; se acota en cero.
    ci = max((lmax - n) / (n - 1), 0.0)
    return ci / INDICE_ALEATORIO[n], ci, lmax


def juicio_mas_inconsistente(a: np.ndarray, elementos: Sequence[str]) -> Dict[str, object]:
    """Comparacion que mas se aparta de lo que implican las demas.

    Sirve en la entrevista: si el CR supera 0,10 se le vuelve a preguntar al
    experto por ESTE par, mostrandole el valor coherente con el resto de sus
    respuestas. El experto decide si lo cambia; no se corrige a mano.
    """
    w, _ = prioridades(a)
    n = len(elementos)
    peor, desvio = (0, 1), -1.0
    for i in range(n):
        for j in range(i + 1, n):
            d = abs(np.log(a[i, j] * w[j] / w[i]))
            if d > desvio:
                peor, desvio = (i, j), d
    i, j = peor
    coherente = w[i] / w[j]
    return {"dimension_a": elementos[i], "dimension_b": elementos[j],
            "juicio_actual": _a_texto(a[i, j]), "valor_coherente": _a_texto(coherente)}


def _a_texto(v: float) -> str:
    """Expresa un valor de la matriz en la escala de Saaty legible."""
    if v >= 1:
        return f"A {min(max(round(v), 1), 9)}"
    return f"B {min(max(round(1 / v), 1), 9)}"


def agregar_juicios(matrices: Sequence[np.ndarray]) -> np.ndarray:
    """Media geometrica elemento a elemento (AIJ). Conserva la reciprocidad."""
    pila = np.stack([np.log(m) for m in matrices])
    return np.exp(pila.mean(axis=0))


# ---------------------------------------------------------------------------
# concordancia
# ---------------------------------------------------------------------------
def w_kendall(rangos: np.ndarray) -> float:
    """W de Kendall con correccion por empates. rangos: (evaluadores x objetos)."""
    r = np.asarray(rangos, dtype=float)
    m, n = r.shape
    if m < 2 or n < 2:
        return float("nan")
    totales = r.sum(axis=0)
    s = ((totales - totales.mean()) ** 2).sum()
    empates = 0.0
    for fila in r:
        _, t = np.unique(fila, return_counts=True)
        empates += (t ** 3 - t).sum()
    denom = m ** 2 * (n ** 3 - n) - m * empates
    return float(12 * s / denom) if denom > 0 else float("nan")


def significancia_kendall(rangos: np.ndarray, n_permutaciones: int = 10000,
                          semilla: int = 42) -> Dict[str, float]:
    """W, prueba chi cuadrado y prueba por permutacion.

    Con cinco objetos la aproximacion chi cuadrado es gruesa, por eso se
    reporta tambien el valor p por permutacion (se barajan los rangos de
    cada evaluador de forma independiente, bajo la hipotesis de que no hay
    acuerdo).
    """
    r = np.asarray(rangos, dtype=float)
    m, n = r.shape
    w = w_kendall(r)
    chi2 = m * (n - 1) * w
    p_chi2 = float(stats.chi2.sf(chi2, n - 1)) if np.isfinite(chi2) else float("nan")
    rng = np.random.default_rng(semilla)
    mayores = 0
    for _ in range(n_permutaciones):
        perm = np.array([rng.permutation(fila) for fila in r])
        if w_kendall(perm) >= w - 1e-12:
            mayores += 1
    return {"w_kendall": w, "chi2": float(chi2), "gl": n - 1, "p_chi2": p_chi2,
            "p_permutacion": (mayores + 1) / (n_permutaciones + 1), "evaluadores": m}


# ---------------------------------------------------------------------------
# respuestas del panel
# ---------------------------------------------------------------------------
def plantilla_respuestas(elementos: Sequence[str]) -> pd.DataFrame:
    """Diez filas vacias por experto, una por comparacion."""
    filas = [{"experto": "E01", "perfil": "", "fecha": "", "dimension_a": a,
              "dimension_b": b, "preferida": "", "intensidad": ""}
             for a, b in pares(elementos)]
    return pd.DataFrame(filas, columns=COLUMNAS)


def leer_respuestas(ruta: Path, elementos: Sequence[str]) -> pd.DataFrame:
    """Lee y valida el archivo de respuestas (separador ';' o ',').

    Falla con un mensaje concreto si a un experto le falta un par, lo tiene
    repetido, usa una dimension desconocida o una intensidad fuera de escala.
    Acepta el par escrito al reves (B antes que A) y lo invierte.
    """
    df = pd.read_csv(ruta, sep=None, engine="python", dtype=str, encoding="utf-8-sig")
    df.columns = [c.strip().lower() for c in df.columns]
    faltan = set(COLUMNAS) - set(df.columns)
    if faltan:
        raise ValueError(f"Faltan columnas en {Path(ruta).name}: {sorted(faltan)}")
    df = df[COLUMNAS].apply(lambda s: s.str.strip())
    df = df[df["preferida"].fillna("") != ""].copy()
    if df.empty:
        raise ValueError(f"{Path(ruta).name} no tiene respuestas diligenciadas")

    orden = {p: i for i, p in enumerate(pares(elementos))}
    validas = set(elementos)
    filas = []
    for _, r in df.iterrows():
        a, b = r["dimension_a"], r["dimension_b"]
        if a not in validas or b not in validas or a == b:
            raise ValueError(f"Experto {r['experto']}: par invalido ({a}, {b})")
        pref = str(r["preferida"]).upper()
        intensidad = 1 if pref in ("=", "IGUAL", "I") else r["intensidad"]
        if (a, b) not in orden:
            a, b = b, a
            pref = {"A": "B", "B": "A"}.get(pref, pref)
        try:
            valor = valor_juicio(pref, float(intensidad))
        except (TypeError, ValueError) as e:
            raise ValueError(f"Experto {r['experto']}, par ({a}, {b}): {e}") from e
        filas.append({**r.to_dict(), "dimension_a": a, "dimension_b": b,
                      "preferida": pref, "valor": valor})
    salida = pd.DataFrame(filas)

    esperados = len(orden)
    for exp, g in salida.groupby("experto"):
        repetidos = g.duplicated(["dimension_a", "dimension_b"])
        if repetidos.any():
            raise ValueError(f"Experto {exp}: comparaciones repetidas")
        if len(g) != esperados:
            ausentes = set(orden) - set(zip(g["dimension_a"], g["dimension_b"]))
            raise ValueError(f"Experto {exp}: faltan {len(ausentes)} comparaciones: {sorted(ausentes)}")
    return salida


def resultado_panel(respuestas: pd.DataFrame, elementos: Sequence[str],
                    umbral_cr: float = 0.10, semilla: int = 42,
                    n_permutaciones: int = 10000) -> Dict[str, object]:
    """Pesos por experto, consistencia, pesos agregados y concordancia."""
    por_experto, matrices = [], {}
    for exp, g in respuestas.groupby("experto", sort=True):
        juicios = {(r["dimension_a"], r["dimension_b"]): float(r["valor"]) for _, r in g.iterrows()}
        a = matriz_desde_juicios(juicios, elementos)
        w, _ = prioridades(a)
        cr, ci, lmax = razon_consistencia(a)
        fila = {"experto": exp, "perfil": g["perfil"].iat[0], "fecha": g["fecha"].iat[0],
                **{e: round(float(v), 4) for e, v in zip(elementos, w)},
                "lambda_max": round(lmax, 4), "cr": round(cr, 4),
                "consistente": bool(cr < umbral_cr)}
        if cr >= umbral_cr:
            fila["revisar"] = juicio_mas_inconsistente(a, elementos)
        por_experto.append(fila)
        matrices[exp] = a
    tabla = pd.DataFrame(por_experto)

    consistentes = [e for e in tabla.loc[tabla["consistente"], "experto"]]
    salida: Dict[str, object] = {"por_experto": tabla, "consistentes": consistentes,
                                 "agregado": None, "concordancia": None,
                                 "concentracion_sugerida": None}
    if not consistentes:
        return salida

    a_panel = agregar_juicios([matrices[e] for e in consistentes])
    w_panel, _ = prioridades(a_panel)
    cr_panel, _, _ = razon_consistencia(a_panel)
    salida["agregado"] = {"pesos": {e: float(v) for e, v in zip(elementos, w_panel)},
                          "cr": float(cr_panel), "n_expertos": len(consistentes)}

    if len(consistentes) >= 2:
        pesos = tabla.set_index("experto").loc[consistentes, list(elementos)].to_numpy()
        rangos = np.array([stats.rankdata(-fila) for fila in pesos])
        salida["concordancia"] = significancia_kendall(rangos, n_permutaciones, semilla)

    if len(consistentes) >= 3:
        pesos = tabla.set_index("experto").loc[consistentes, list(elementos)].to_numpy()
        media, var = pesos.mean(axis=0), pesos.var(axis=0, ddof=1)
        with np.errstate(divide="ignore", invalid="ignore"):
            alfa0 = media * (1 - media) / var - 1
        alfa0 = alfa0[np.isfinite(alfa0) & (alfa0 > 0)]
        if len(alfa0):
            salida["concentracion_sugerida"] = float(np.median(alfa0))
    return salida


# ---------------------------------------------------------------------------
# validez de contenido de las variables (opcional)
# ---------------------------------------------------------------------------
def indice_validez_contenido(calificaciones: pd.DataFrame) -> Tuple[pd.DataFrame, Dict[str, float]]:
    """I-CVI por variable y S-CVI/Ave (Lynn, 1986; Polit y Beck, 2006).

    calificaciones: columnas experto, variable, relevancia (1 a 4). Una
    variable cuenta como relevante para un experto si la califica 3 o 4.
    Criterio de Lynn: con cinco expertos o menos se exige I-CVI de 1; con
    seis o mas, 0,78.
    """
    c = calificaciones.copy()
    c["relevancia"] = pd.to_numeric(c["relevancia"], errors="coerce")
    c = c.dropna(subset=["relevancia"])
    n_exp = c["experto"].nunique()
    umbral = 1.0 if n_exp <= 5 else 0.78
    por_var = c.groupby("variable").agg(
        expertos=("experto", "nunique"),
        relevancia_media=("relevancia", "mean"),
        i_cvi=("relevancia", lambda s: float((s >= 3).mean())),
    ).round(3)
    por_var["cumple"] = por_var["i_cvi"] >= umbral
    resumen = {"n_expertos": n_exp, "umbral_i_cvi": umbral,
               "s_cvi_ave": round(float(por_var["i_cvi"].mean()), 3) if len(por_var) else float("nan")}
    return por_var.reset_index(), resumen
