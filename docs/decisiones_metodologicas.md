# Decisiones metodológicas frente a la especificación de dirección

Versión del modelo 0.2.0. Corte de datos: 2026-09-11 (SUIFP, DNP, vía datos.gov.co).

La evaluación de dirección (hallazgo crítico C5) señaló que el componente de ciencia de datos se anunciaba sin especificarse, y la versión 3 ajustada del anteproyecto escribió esa especificación siguiendo el manual de indicadores compuestos de la OCDE y el JRC (2008). Este documento registra, punto por punto, qué se adoptó, qué se adaptó y qué se descartó, con la evidencia de los datos del caso. Todas las cifras se reproducen con `python main.py`, que construye los datos desde el corte versionado en `datos/corte_2026-09-11`. El SUIFP se actualiza continuamente: un corte descargado el 25 de septiembre de 2026 (`python main.py --reconstruir`) da 638 proyectos identificados, 494 evaluables y 176 vigentes, por lo que toda cifra debe citarse con su fecha de corte.

## 1. Universo de datos (condición de aprobación 2)

| | Cajicá | Chía | Total |
|---|---:|---:|---:|
| Proyectos BPIN identificados | 321 | 322 | 643 |
| Evaluables (apropiación vigente acumulada mayor que cero) | 270 | 221 | 491 |
| Vigentes (en ejecución o sin recursos para la vigencia) | 80 | 92 | 172 |
| Previos (subestado inactivo) | 190 | 129 | 319 |
| Ficha SUIFP completa (14 de 14 campos) | 139 | 131 | 270 |
| Ficha financiera vacía (valor total en cero) | 127 | 68 | 195 |
| Seguimiento contradictorio con la ejecución | 21 | 16 | 37 |
| Con información insuficiente para calificar | 0 | 0 | 0 |

**Universo analítico y universo de oportunidades.** El score se calcula sobre los 491 evaluables: una base de comparación más amplia da una normalización más estable que la de los 172 vigentes solos. La vista para el inversionista muestra los 172 vigentes; los 319 inactivos se presentan aparte como proyectos previos, con su situación real y no como proyectos completados. Según el SUIFP, de los 319 previos 12 están terminados (100 % de avance), 108 tienen avance parcial, 174 no reportan avance y 25 tienen un avance que contradice su propia ejecución.

Dos proyectos de Cajicá aparecían localizados como "Todo el Depto" (código 25000) en la tabla de localización. La entidad que los formula es la alcaldía de Cajicá y así lo dice el nombre de cada proyecto; se reasignan por entidad responsable. Sin la corrección quedaban fuera del conteo por municipio y tomaban una población promedio.

## 2. Tabla de decisiones

| Especificación de dirección | Decisión | Evidencia o razón |
|---|---|---|
| Índice compuesto, no modelo predictivo | Adoptada | No existe variable objetivo observable de éxito de la inversión |
| Ponderación por proceso analítico jerárquico, CR < 0,10 por evaluador, agregación por media geométrica | Adoptada | `modelo/ahp.py`, `scripts/05_panel_expertos.py` e instrumento en `docs/instrumento_panel_expertos.docx` |
| Pesos preliminares 25/20/25/15/15 | Se mantienen 25/20/25/20/10 como punto de partida | Ambos son preliminares; el resultado lo da el panel |
| Faltantes: descartar variable con más de 30 %, excluir proyecto con más de 40 % | Adoptada | Descarta `consistencia_financiera` (39,7 % faltante). Ningún proyecto supera el 40 % |
| Completitud como metadato, nunca en el score | Adoptada | `completitud_ficha` con peso 0; se muestra en cada proyecto |
| Correlaciones y componentes principales | Adoptada | Llevó a retirar dos variables redundantes (sección 4) |
| Atractivo inversor como índice normativo de atributos observables | Adoptada y ampliada | Se agregó la vinculación de capital privado según el tipo de intervención (sección 5) |
| Normalización mín-máx en [0, 100] | Adoptada | Sin cambio |
| Normalización dentro de cada estrato municipio-sector | Descartada | 45 estratos: 3 con un solo proyecto (mín-máx indefinido) y 18 con cinco o menos. El score dejaría de ser comparable entre sectores. Se reporta aparte el percentil del proyecto dentro de su sector |
| Winsorización en p5 y p95 | Adoptada | p1 y p99 quedan como variante: Spearman 0,995 |
| Agregación por media geométrica ponderada | Adoptada, con piso | 33 proyectos tienen al menos una dimensión en cero y la media geométrica pura les daría cero. Cada dimensión se lleva a [1, 100] antes de agregar |
| Monte Carlo con Dirichlet, 10.000 iteraciones, intervalo de posiciones e índices de primer orden | Adoptada | Concentración 100, configurable. Índices por razón de correlación sobre las variables gamma que generan la Dirichlet, que son independientes |
| Robustez: pesos iguales, entropía, agregación aritmética, ρ > 0,85 | Adoptada | Todas cumplen, en el universo completo y dentro de los vigentes (sección 6) |
| Descomposición por dimensión y por variable | Adoptada | Vista Comparar del tablero |
| Validez convergente con desempeño fiscal y gobierno abierto | Adaptada | Son indicadores municipales: toman dos valores en este universo, y el avance ya está dentro del score. Se usa el Informe de Gestión 2024 de Cajicá por sector (sección 7) |
| Validez de utilidad con prueba de tarea y SUS > 68 | Pendiente | Trabajo de campo nuevo, fuera de lo acordado para el prototipo |
| Marco de referencia de Sabana Centro con TerriData | Pendiente | Toca la exclusión acordada de "escalar a otros municipios", aunque solo sea contexto |
| Arquitectura con PostgreSQL, orquestador y React | Fuera del alcance del prototipo | El prototipo usa Streamlit y archivos locales. La tabla de la v3 describe la arquitectura objetivo |

## 3. Cero real frente a dato faltante

El SUIFP no deja campos vacíos: escribe cero. Tratar todo cero como dato real castiga a un proyecto por un reporte incompleto; tratarlo todo como faltante premia al que no reporta. La regla adoptada es intermedia y verificable: un cero es faltante solo si es imposible o si otra tabla del propio SUIFP lo contradice.

- Ficha financiera vacía: valor total del proyecto en cero (195 proyectos). Ningún proyecto cuesta cero.
- Seguimiento contradictorio: avance financiero en cero mientras la tabla de ejecución registra obligaciones (37 proyectos). Si además el avance físico es cero, tampoco se usa (27 proyectos).

Si a un proyecto le falta una variable, su dimensión se calcula con las demás, renormalizando sus pesos; no se imputa un valor.

Con la completitud fuera del score, la brecha entre fichas incompletas y completas se mantiene: puntaje medio de 28,8 con 10 de 14 campos frente a 58,5 con 14 de 14. La brecha no la produce la falta de datos sino la ejecución registrada en otra tabla: de los 192 proyectos con 10 campos, 188 están inactivos y 159 no registran ninguna obligación.

## 4. Análisis multivariado y variables retiradas

El análisis detectó cuatro pares de variables de dimensiones distintas con Spearman de 0,8 o más. Se retiraron los dos que superan 0,9, porque miden lo mismo y hacían pesar dos veces una misma señal:

| Retirada | Par con | Spearman | Razón |
|---|---|---:|---|
| Inversión por habitante (impacto social) | Escala del proyecto (atractivo) | 0,991 | Con dos municipios, dividir el monto por la población solo lo reescala |
| Diversificación de fuentes (viabilidad) | Cofinanciación externa (atractivo) | 0,924 | Tener más de una fuente equivale casi siempre a tener una fuente externa |

Su peso se repartió en proporción a los pesos restantes de su dimensión. Se conservan los dos pares entre 0,8 y 0,9 (avance físico con reporta seguimiento, 0,880; obligación sobre apropiación con vigencias ejecutadas, 0,854) porque miden aspectos distintos (avance frente a conducta de reporte; proporción ejecutada frente a años con ejecución) y porque retirar el reporte de seguimiento dejaría a gobernanza con una sola variable. Hay una prueba automática que falla si reaparece un par de 0,9 o más.

Con estos retiros y la variable nueva de la sección 5, el índice queda con 16 variables. Componentes principales: cinco componentes con autovalor mayor que 1 explican el 69,3 % de la varianza; el primero (32,3 %) reúne las variables de ejecución de viabilidad, madurez y gobernanza. Alfa de Cronbach por dimensión: viabilidad 0,36; madurez 0,34; impacto social −0,95; gobernanza 0,07; atractivo 0,33.

Lectura: el índice es formativo (cada variable aporta un aspecto distinto del concepto), por lo que un alfa bajo no lo invalida. Se declaran dos limitaciones. Gobernanza e impacto social quedan con dos variables cada una. En impacto social, la cobertura poblacional y la prioridad del sector se correlacionan en sentido opuesto (Spearman −0,30): la dimensión reúne dos aspectos distintos, no una medida única.

## 5. Vinculación de capital privado

Entre los proyectos vigentes, los programas de funcionamiento (aseguramiento en salud, vigilancia sanitaria, fortalecimiento de la gestión) promediaban 59,2 puntos y las obras de inversión en capital 45,8, y 7 de los 10 primeros eran del sector salud. El índice premiaba la buena ejecución de los programas recurrentes, pero son las obras las que admiten capital privado (obras por impuestos, Ley 1819 de 2016; asociaciones público privadas, Ley 1508 de 2012). Ninguna variable medía eso.

Se agregó al atractivo inversor la variable **vinculación de capital privado**, con peso 0,30 dentro de la dimensión (los demás pesos se redujeron en proporción). Se construye con el tipo de intervención, que se infiere del verbo que encabeza el nombre del proyecto, y una escala preliminar de juicio experto que el panel valida en la pregunta C2 del instrumento:

| Tipo de intervención | Proyectos | Escala preliminar |
|---|---:|---:|
| Inversión en capital | 69 | 1,00 |
| Mejoramiento | 80 | 0,80 |
| Mantenimiento | 51 | 0,60 |
| Preinversión | 22 | 0,50 |
| Implementación de programa | 66 | 0,30 |
| Fortalecimiento institucional | 203 | 0,20 |

La clasificación compara por raíz de la palabra porque el SUIFP trae tildes corruptas ("CONSTRUCCIN"); con la palabra exacta, 68 proyectos quedaban sin clasificar y ahora ninguno. Cuando el verbo inicial es ambiguo ("Diseño y construcción...", "Administración, reposición y expansión..."), la mención de obra física define el tipo.

Efecto: con el peso actual del atractivo (0,10), las obras suben a 49,0 y los programas de funcionamiento bajan a 57,3 entre los vigentes; en el top 10 quedan 6 de salud. La variable mide lo correcto pero su efecto depende del peso que el panel asigne al atractivo inversor: con 0,25, las obras (50,8) superan a los programas de funcionamiento (49,7). No se modificaron los pesos entre dimensiones porque los define el panel.

## 6. Robustez e incertidumbre

Spearman frente al esquema base (criterio de aceptación: mayor que 0,85):

| Contraste | Universo completo (491) | Top 10 estable | Solo vigentes (172) | Top 10 estable |
|---|---:|---:|---:|---:|
| Pesos iguales | 0,988 | 0,9 | 0,967 | 0,9 |
| Énfasis financiero | 0,957 | 0,8 | 0,914 | 0,6 |
| Énfasis social | 0,979 | 0,9 | 0,961 | 0,7 |
| Énfasis en gobernanza | 0,983 | 0,8 | 0,984 | 0,8 |
| Ponderación por entropía | 0,973 | 0,9 | 0,965 | 0,8 |
| Agregación aritmética | 0,967 | 0,9 | 0,977 | 0,8 |
| Winsorización p1 y p99 | 0,995 | 1,0 | 0,997 | 0,9 |
| Imputación por mediana | 0,999 | 1,0 | 1,000 | 1,0 |
| Normalización por rango percentil | 0,972 | 0,7 | 0,977 | 0,8 |

Monte Carlo, 10.000 esquemas de pesos con Dirichlet de concentración 100 centrada en el esquema base: Spearman medio 0,995, percentil 5 0,987, mínimo 0,962; el 100 % de las simulaciones supera el criterio. Desplazamiento medio de 9,7 puestos.

Índices de sensibilidad de primer orden sobre el desplazamiento del ranking: atractivo inversor 0,17; impacto social 0,17; madurez de ejecución 0,16; viabilidad financiera 0,09; gobernanza 0,08. Suman 0,67; el resto corresponde a interacciones. El atractivo inversor es la dimensión cuyo peso más mueve el orden pese a pesar 0,10, lo que refuerza que su peso definitivo lo fije el panel.

Balance territorial del top 50 de vigentes: 29 de Chía y 21 de Cajicá. Score medio: Chía 46,7 y Cajicá 43,7.

## 7. Validez convergente

Fuente independiente: el Informe de Gestión 2024 de Cajicá, que produce el municipio y no el DNP. Unidad: el sector (18 sectores emparejados; entre 1 y 15 proyectos vigentes por sector, mediana 3). Se compara el puntaje medio de los proyectos vigentes de Cajicá en cada sector con lo que el informe reporta para ese sector. Criterio de dirección: correlación positiva y significativa.

| Contraste | Spearman | Valor p | Cumple |
|---|---:|---:|---|
| Score total frente a avance físico del sector | 0,631 | 0,005 | Sí |
| Viabilidad financiera frente a ejecución presupuestal | 0,497 | 0,036 | Sí |
| Score total frente a ejecución presupuestal | 0,307 | 0,215 | No |
| Madurez de ejecución frente a avance físico | 0,137 | 0,587 | No |

Con todos los proyectos de Cajicá, vigentes y previos, ningún contraste es significativo. Es coherente: el informe mide la vigencia 2024 del plan actual, que corresponde a los proyectos vigentes y no a los de planes anteriores.

La evidencia de validez convergente es parcial: dos de cuatro contrastes cumplen el criterio. Limitaciones: un solo municipio, 18 sectores con pocos proyectos cada uno, y el SUIFP acumula todo el horizonte del proyecto mientras el informe mide un año.

## 8. Referencias metodológicas

- Kendall, M. G. y Babington Smith, B. (1939). The problem of m rankings. The Annals of Mathematical Statistics, 10(3), 275-287.
- Lynn, M. R. (1986). Determination and quantification of content validity. Nursing Research, 35(6), 382-385.
- OCDE y JRC (2008). Handbook on constructing composite indicators: Methodology and user guide. OECD Publishing.
- Polit, D. F. y Beck, C. T. (2006). The content validity index: Are you sure you know what's being reported? Research in Nursing & Health, 29(5), 489-497.
- Saaty, T. L. (1980). The analytic hierarchy process. McGraw-Hill.
- Saaty, T. L. (2008). Decision making with the analytic hierarchy process. International Journal of Services Sciences, 1(1), 83-98.
- Saltelli, A. et al. (2008). Global sensitivity analysis: The primer. Wiley.
