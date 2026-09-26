# ColombiaInvest

**Version 1.0**

Componente de datos y prototipo del trabajo de grado, Maestria en Ciencia de
Datos, Universidad EAN, modalidad Creacion de Empresa.

Modelo de calificacion compuesta que evalua, califica y compara proyectos de
inversion publica de Chia y Cajica, para reducir la asimetria de informacion
entre entidades territoriales e inversionistas privados.

## Decision de diseno principal

**La unidad de analisis es el proyecto BPIN, no el contrato.**

Se verifico contra la API de Socrata el 11 de septiembre de 2026 que SECOP II
Contratos Electronicos no expone identificador de proyecto, y que la tabla
puente `DNP-ProyectosContratos` no cubre los proyectos territoriales de estos
municipios. En cambio, el SUIFP del DNP publica los proyectos municipales con
codigo BPIN, avance fisico, ejecucion financiera anual por fuente y
beneficiarios declarados.

SECOP queda como evidencia contractual complementaria, cruzable solo por
similitud de texto y con tasa de emparejamiento reportada como limitacion.

Ver `docs/diagnostico_fuentes.md` para la evidencia completa.

## Estructura

```
config/          pesos.yaml, fuentes.yaml y diccionario_variables.yaml.
                 Toda la parametrizacion vive aqui. pesos_panel.yaml lo
                 escribe el panel de expertos cuando existe.
src/colombiainvest/
  ingesta/       cliente Socrata y descarga del SUIFP
  procesamiento/ construccion del dataset, variables y normalizacion
  modelo/        score compuesto, sensibilidad, multivariado y AHP
scripts/         01_ingesta, 02_dataset, 03_score, 04_documentos,
                 05_panel_expertos
app/             prototipo en Streamlit (tablero.py y estilos.py)
tests/           pruebas del modelo
datos/documentos PDF municipales, versionados
datos/entrevistas plantillas y respuestas del panel (codigos, sin nombres)
datos/           crudos y procesados (derivados, no versionados)
salidas/         ranking, sensibilidad y diagnosticos (derivados)
docs/            diagnostico de fuentes, decisiones metodologicas e
                 instrumento del panel de expertos
main.py          punto de entrada unico
.vscode/         configuracion de F5
```

## Como ejecutarlo

Se necesita **Python 3.10 o superior**. Nada mas.

### Opcion 1: Visual Studio Code

Abrir la carpeta y presionar **F5**. Ya viene configurado en `.vscode/launch.json`.
Hay tres configuraciones en el menu de depuracion:

| Configuracion | Que hace |
|---|---|
| ColombiaInvest: abrir el tablero | instala lo que falte, construye los datos si es la primera vez y abre el navegador |
| ColombiaInvest: reconstruir los datos | rehace los datos desde las fuentes, sin abrir el tablero |
| ColombiaInvest: pruebas | corre la bateria de pruebas |

### Opcion 2: consola

```bash
python main.py
```

### Opcion 3: Windows sin editor

Doble clic sobre `ejecutar.bat`.

---

`main.py` hace tres cosas en orden, y avisa en pantalla de cada una:

1. Verifica las dependencias e instala las que falten desde `requirements.txt`.
2. Construye los datos si no existen. **Solo la primera vez**, toma unos dos
   minutos y **requiere conexion a internet**, porque descarga el SUIFP del
   DNP desde `datos.gov.co`.
3. Levanta el servidor en `http://localhost:8501` y abre el navegador.

Para detenerlo, `Ctrl+C` en la consola.

Opciones:

```bash
python main.py --reconstruir    # rehace los datos desde cero
python main.py --solo-datos     # construye los datos y no abre el tablero
python main.py --puerto 8600    # usa otro puerto
python main.py --sin-instalar   # no instala nada, solo avisa que falta
```

### Que se versiona y que no

Los datos derivados (`datos/crudos/`, `datos/procesados/`, `salidas/`) **no
se versionan**: se reconstruyen solos. Lo que si viaja en el repositorio es
`datos/documentos/`, con los dos PDF municipales que permiten reproducir la
seccion de contexto sin depender de rutas locales.

Quien reciba el proyecto en ZIP o lo clone obtiene exactamente el mismo
resultado corriendo `main.py`.

### Ejecutar los pasos por separado

```bash
python scripts/01_ingesta.py      # descarga el SUIFP (--secop agrega SECOP)
python scripts/02_dataset.py      # construye el dataset y diagnostica variables
python scripts/03_score.py        # califica y corre el analisis de sensibilidad
python scripts/04_documentos.py   # procesa los PDF municipales
python scripts/05_panel_expertos.py --plantilla   # plantillas del panel
python scripts/05_panel_expertos.py               # pesos del panel (AHP)
python -m streamlit run app/tablero.py
python -m pytest tests/ -q
```

## El modelo

Indice compuesto, no aprendizaje supervisado. No hay variable objetivo ni
fase de entrenamiento. La construccion sigue el manual de indicadores
compuestos de la OCDE y el JRC (2008), segun la especificacion de la
evaluacion de direccion. Las decisiones, con su evidencia, estan en
`docs/decisiones_metodologicas.md`.

Entre dimensiones la agregacion es una **media geometrica ponderada**, que
limita la compensacion: una gobernanza muy baja no se compensa del todo con
un impacto alto. Pesos preliminares del esquema base:

```
Viabilidad financiera 0.25 | Madurez de ejecucion 0.20 | Impacto social 0.25
Gobernanza 0.20            | Atractivo inversor 0.10
```

Son un punto de partida. Los pesos definitivos los produce el panel de
expertos por proceso analitico jerarquico (`scripts/05_panel_expertos.py`,
instrumento en `docs/instrumento_panel_expertos.docx`).

Los pesos **no estan incrustados en el codigo**. Viven en `config/pesos.yaml`
y son el insumo que se lleva a las entrevistas. Existe una prueba
(`test_pesos_no_estan_incrustados`) que falla si alguien los fija.

Cada dimension agrega variables normalizadas a `[0, 1]` y orientadas de modo
que un valor mayor siempre sea mejor. Los pesos intra dimension tambien son
configurables.

Datos faltantes: un cero del SUIFP se trata como faltante solo si es
imposible o si otra tabla del SUIFP lo contradice. Se descarta la variable
con mas del 30 % de faltantes y no se califica el proyecto con mas del 40 %.
Si a un proyecto le falta una variable, su dimension se calcula con las
demas. La completitud de la ficha se muestra como metadato y no entra al
score.

### Universo

De 643 proyectos BPIN cuya entidad responsable es la alcaldia de Chia o de
Cajica, **491 tienen apropiacion presupuestal mayor que cero** y conforman el
universo evaluable. El recorte es explicito y se reporta.

El score se calcula sobre los 491, que dan una base de comparacion amplia.
El tablero muestra como oportunidades los **172 vigentes** (en ejecucion o
sin recursos para la vigencia) y lleva los **319 inactivos** a la seccion
Proyectos previos, con la situacion que reporta el SUIFP: inactivo no
significa terminado (solo 12 reportan el 100 % de avance).

### Normalizacion

Parametrizada en `config/pesos.yaml`, con cuatro metodos comparables: min-max,
puntuacion z, robusta por mediana y MAD, y rango percentil. Por defecto se
winsoriza antes de escalar y se aplica logaritmo a las variables monetarias.

La justificacion es empirica: el diagnostico de SECOP hallo 13 contratos por
encima de un billon de pesos, con maximo de 2.582 billones frente a una
mediana de 24,6 millones. Sin winsorizar, min-max comprime el 99,9 % de los
registros contra cero.

### Analisis de sensibilidad y robustez

En `src/colombiainvest/modelo/sensibilidad.py` y `multivariado.py`:

1. **Esquemas de ponderacion.** Pesos iguales, tres esquemas de enfasis y
   ponderacion por entropia. Criterio de aceptacion: Spearman mayor que 0,85.
2. **Decisiones metodologicas.** Agregacion aritmetica, winsorizacion p1 y
   p99, imputacion por mediana y normalizacion por rango percentil.
3. **Monte Carlo con Dirichlet.** 10.000 esquemas de pesos centrados en el
   base; intervalo de posiciones de cada proyecto e indices de sensibilidad
   de primer orden por dimension.
4. **Analisis multivariado.** Correlaciones, pares redundantes, componentes
   principales y alfa de Cronbach por dimension.

Tambien se reporta la **contribucion de cada dimension a la varianza del
score**, para detectar pesos decorativos.

## Alcance

Dentro: carga de un conjunto acotado de proyectos depurados, calculo del
score, tablero de comparacion, visualizacion por dimension y ponderacion
configurable.

Fuera: integracion automatica en tiempo real, pipeline de actualizacion,
autenticacion, despliegue en produccion y escalamiento a otros municipios.

## Documentos municipales

`scripts/04_documentos.py` procesa dos PDF entregados por la alcaldia de
Cajica y produce enriquecimiento de ficha y contexto para el prototipo.

**Estas fuentes no alimentan el score.** Cubren 79 de los 491 proyectos
evaluables (16,1 %) y ninguno de los 221 de Chia. Si se usaran como
variables, un subconjunto quedaria calificado con informacion que el resto
no tiene, y el ranking premiaria la disponibilidad documental en lugar del
merito del proyecto.

| Documento | Estado | Uso |
|---|---|---|
| Proyectos de inversion PMD Cajica | 91 proyectos, todos ya en el SUIFP | ficha: dependencia responsable, dimension, programa |
| Informe de Gestion Cajica 2024 | 18 sectores con avance y ejecucion | contexto municipal en el prototipo |
| PDM 2024 (418 paginas) | escaneado, sin texto extraible | requiere OCR, no procesado |

Aporte principal: la cifra agregada de 92,5 % de avance fisico contra 58,1 %
de ejecucion presupuestal queda **desagregada en 18 sectores**. El caso
extremo es Minas y Energia, con 88,8 % de avance fisico y 0 % de ejecucion
presupuestal.

### Nota sobre el contraste entre fuentes

El SUIFP reporta avance acumulado del proyecto sobre su horizonte; el
informe municipal reporta avance de la vigencia 2024. No son comparables de
forma directa. Contra la base temporal correcta, que es el avance del
cuatrienio que el propio informe reporta en 22,4 %, el SUIFP arroja 31,0 %
para Cajica: una diferencia de 8,6 puntos, coherente entre fuentes.

## Limitaciones declaradas

1. **Beneficiarios.** El SUIFP los trae diligenciados en el 100 % de los
   proyectos, pero 188 de los 491 evaluables declaran mas beneficiarios que
   habitantes del municipio. Es cifra declarada en la MGA, no verificada. Se
   usa como cobertura poblacional con tope en 1,0, no como conteo.
2. **Estado del proyecto.** `estadoproyecto` es constante en el universo
   evaluable. Se usa `subestadoproyecto`, que si discrimina.
3. **Sin cruce con SECOP.** No existe llave comun. El cruce por texto esta
   pendiente y se reportara con su tasa de emparejamiento.
4. **Regalias.** Solo 20 de 16.865 contratos municipales las involucran. El
   Mapa de Inversiones del DNP aporta poco para este caso y no debe
   presentarse como fuente central en el documento.
5. **Poblacion municipal.** Los valores en `config/pesos.yaml` estan marcados
   como pendientes de verificacion contra TerriData.

## Sobre fuga de informacion

El score compuesto no es un modelo predictivo: no hay variable objetivo ni
particion temporal, de modo que no aplica el riesgo de leakage. Si se agrega
el componente supervisado de retraso o sobrecosto que esta en evaluacion,
ese modulo debera restringirse a variables conocidas al momento de la firma
del contrato.
