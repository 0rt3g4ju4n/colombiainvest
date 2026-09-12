# Diagnostico de fuentes de datos

Verificacion realizada el 11 de septiembre de 2026 contra la API de Socrata
de datos.gov.co. Ningun nombre de campo fue asumido: todos se confirmaron
consultando el endpoint de metadatos de cada dataset.

Este documento sustenta la decision sobre unidad de analisis y sirve de
insumo para la seccion de metodologia del anteproyecto.

---

## 1. SECOP II Contratos Electronicos (`jbjy-vk9h`)

85 campos. Descarga completa del subconjunto municipal de Chia y Cajica,
excluyendo entidades de orden nacional y privadas ubicadas en esos
municipios: **16.865 contratos**.

### Entidades contratantes

| Contratos | Municipio | Entidad |
|---|---|---|
| 6.375 | Chia | Alcaldia Municipal de Chia |
| 4.239 | Cajica | Alcaldia Municipio de Cajica |
| 2.096 | Chia | Instituto Municipal de Recreacion y Deportes |
| 1.314 | Cajica | Instituto Municipal de Deporte y Recreacion |
| 1.311 | Cajica | Instituto Municipal de Cultura y Turismo |

Se excluyeron 3.491 contratos del SENA Regional Cundinamarca, 8 de la
Universidad de La Sabana y 3 de una institucion educativa departamental, por
no corresponder a inversion municipal.

### Hallazgos que descartan el contrato como unidad de analisis

1. **No existe campo BPIN ni identificador de proyecto.** Se revisaron los 85
   campos del esquema.
2. **La tabla puente `DNP-ProyectosContratos` (`uwns-mbwd`) devolvio cero
   coincidencias** con los 643 BPIN municipales. Esa tabla cubre proyectos de
   regalias, no proyectos territoriales financiados con recursos propios.
3. **El 85,9 % son contratos de prestacion de servicios** y el 85,7 % se
   adjudican por contratacion directa. Es contratacion de personal, no
   proyectos de inversion evaluables por un inversionista.
4. Solo hay **172 contratos de obra, 60 de consultoria y 51 de
   interventoria** en todo el historico de inversion.
5. **`origen_de_los_recursos` es inservible**: el 97,1 % de los registros
   dice "Distribuido".
6. **Las regalias son marginales**: 20 contratos de 16.865 reportan recursos
   del Sistema General de Regalias. Chia y Cajica no son municipios
   receptores relevantes, de modo que el Mapa de Inversiones del DNP aporta
   muy poco a este caso y no deberia presentarse como fuente central.
7. **Valores atipicos extremos.** Trece contratos superan el billon de pesos,
   con un maximo de 2.582 billones, frente a una mediana de 24,6 millones.
   Son errores de digitacion en la fuente. La razon entre maximo y mediana es
   de 105 millones a uno.

| Percentil | Valor del contrato |
|---|---|
| p25 | $15.000.000 |
| p50 | $24.593.481 |
| p75 | $40.000.000 |
| p90 | $76.655.500 |
| p99 | $1.882.314.967 |
| p99,9 | $40.000.000.000 |
| maximo | $2.582.672.400.000.000 |

Este hallazgo es el que sustenta la decision de winsorizar antes de
normalizar. Sin ese tratamiento, min-max comprime el 99,9 % de los registros
contra cero.

### Campos aprovechables de SECOP

Pese a lo anterior, SECOP conserva valor como evidencia complementaria:
`valor_facturado`, `valor_pagado` y `valor_pendiente_de_ejecucion` estan
diligenciados entre el 86 % y el 88 % de los casos, y `dias_adicionados`
tiene valor distinto de cero en el 14 %. Permiten calcular brecha de
ejecucion y desviacion de cronograma a nivel de contrato.

---

## 2. SUIFP del DNP: la fuente que resuelve la unidad de analisis

### Universo

Filtrando `DNP-LocalizacionProyecto` (`xikz-44ja`) por entidad responsable se
obtienen **643 proyectos BPIN** cuya entidad responsable es la alcaldia:
322 de Chia y 321 de Cajica.

El filtro por entidad responsable, y no por localizacion, es deliberado:
localizacion incluye proyectos nacionales ejecutados en el municipio (SENA,
ICBF, Colciencias, ministerios), que no son proyectos del municipio.

### Tablas utilizadas

| Dataset | ID | Registros para el universo | Aporte |
|---|---|---|---|
| DNP-LocalizacionProyecto | `xikz-44ja` | 643 | sector, municipio, entidad |
| DNP-SeguimientoProyecto | `7mxf-bp6x` | 643 | avance fisico y financiero, horizonte |
| DNP-EjecucionProyectoDivipola | `u3qu-swda` | 2.029 | ejecucion por vigencia y fuente |
| DNP-proyectos_datos_basicos | `cf9k-55fw` | 643 | estado, valores, beneficiarios |
| DNP-BeneficiariosProyectoLocalizacion | `iuc2-3r6h` | 641 | no utilizable, ver nota |

### Nota sobre beneficiarios

`DNP-BeneficiariosProyectoLocalizacion` trae `totalbeneficiario` en cero para
los 640 proyectos consultados. En cambio, `DNP-proyectos_datos_basicos` trae
el campo diligenciado en el **100 % de los 643 proyectos**, con mediana de
70.749 beneficiarios.

Limitacion: **188 de los 491 proyectos evaluables (38,3 %) declaran mas
beneficiarios que habitantes tiene el municipio.** Es una cifra declarada en
la formulacion MGA, probablemente acumulada sobre el horizonte o referida a
poblacion total impactada. Por eso el modelo la usa como cobertura
poblacional relativa con tope en 1,0, y no como conteo absoluto.

### Fuentes de financiacion observadas

| Fuente | Registros |
|---|---|
| Propios de las entidades territoriales | 1.659 |
| SGP, Sistema General de Participaciones | 358 |
| Propios de las EICE y SEM | 9 |
| Propios de los privados | 2 |
| PGN, Presupuesto General de la Nacion | 1 |

Confirma que Chia y Cajica financian su inversion casi enteramente con
recursos propios. Esto invalida la variable "proporcion de cofinanciacion
frente a recursos del SGP" tal como estaba planteada, por falta de varianza
util, y motiva la variable `cofinanciacion_externa` que si discrimina.

---

## 3. Universo evaluable

De los 643 proyectos, **491 tienen apropiacion presupuestal mayor que cero**
y conforman el universo evaluable: 268 de Cajica, 221 de Chia y 2 registrados
como "Todo el Depto".

| Indicador | Valor |
|---|---|
| Valor vigente, mediana | $2.384 millones |
| Valor vigente, p10 | $254 millones |
| Valor vigente, p90 | $20.473 millones |
| Avance fisico, mediana | 65,9 % (entre los que reportan) |
| Proyectos que reportan avance fisico | 276 |

---

## 4. Variables descartadas por falta de varianza

El diagnostico automatico de `scripts/02_dataset.py` detecto y obligo a
corregir tres defectos:

1. **`presencia_cruzada`** resulto constante: los 643 proyectos aparecen en
   las cuatro tablas del SUIFP. Peso decorativo. Se sustituyo por
   `cobertura_reporte`, que mide si el proyecto reporta apropiacion a lo
   largo de su horizonte declarado.
2. **`estadoproyecto`** resulto constante en el universo evaluable: los 491
   proyectos con apropiacion estan "En Ejecucion". Se sustituyo por
   `subestadoproyecto`, que tiene tres niveles reales (Inactivo 319, En
   ejecucion 143, Sin recursos para la vigencia actual 29).
3. **`completitud_ficha`** tenia rango 0,889 a 1,0, casi constante. Se
   amplio el conjunto de campos evaluados de nueve a catorce, incorporando
   los campos financieros, que son los que realmente distinguen una ficha
   bien diligenciada.

Tambien se acoto `ratio_pago` a 1,0: cinco proyectos reportan pagado por
encima de obligado, lo cual es inconsistencia de la fuente y no mejor
desempeno.

---

## 5. Pendientes de verificacion

1. Poblacion municipal usada para normalizar: reemplazar los valores de
   `config/pesos.yaml` por el dato de TerriData y citar la fuente.
2. Cruce SECOP con proyectos por similitud de texto del objeto contractual
   contra el nombre del proyecto, reportando tasa de emparejamiento.
3. Informes de gestion municipales para contrastar avance fisico reportado
   en el SUIFP con el reportado en los informes.
