# ColombiaInvest

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
config/          pesos.yaml y fuentes.yaml. Toda la parametrizacion vive aqui.
src/colombiainvest/
  ingesta/       cliente Socrata y descarga del SUIFP
  procesamiento/ construccion del dataset, variables y normalizacion
  modelo/        score compuesto y analisis de sensibilidad
scripts/         01_ingesta, 02_dataset, 03_score
app/             prototipo en Streamlit
tests/           pruebas del modelo
datos/           crudos y procesados (no versionados)
salidas/         ranking, sensibilidad y diagnosticos
docs/            diagnostico de fuentes y notas metodologicas
```

## Uso

```bash
pip install -r requirements.txt

python scripts/01_ingesta.py        # descarga el SUIFP (agregue --secop si lo necesita)
python scripts/02_dataset.py        # construye el dataset y diagnostica variables
python scripts/03_score.py          # califica y corre el analisis de sensibilidad
python scripts/04_documentos.py     # procesa los PDF municipales (opcional)
streamlit run app/tablero.py        # prototipo
pytest tests/ -q                    # pruebas
```

## El modelo

Score compuesto ponderado, no aprendizaje supervisado. No hay variable
objetivo ni fase de entrenamiento. Los pesos provienen de juicio experto y
seran validados con entrevistas.

```
Score = 0.25 Viabilidad financiera
      + 0.20 Madurez de ejecucion
      + 0.25 Impacto social
      + 0.20 Gobernanza
      + 0.10 Atractivo inversor
```

Los pesos **no estan incrustados en el codigo**. Viven en `config/pesos.yaml`
y son el insumo que se lleva a las entrevistas. Existe una prueba
(`test_pesos_no_estan_incrustados`) que falla si alguien los fija.

Cada dimension agrega variables normalizadas a `[0, 1]` y orientadas de modo
que un valor mayor siempre sea mejor. Los pesos intra dimension tambien son
configurables.

### Universo

De 643 proyectos BPIN cuya entidad responsable es la alcaldia de Chia o de
Cajica, **491 tienen apropiacion presupuestal mayor que cero** y conforman el
universo evaluable. El recorte es explicito y se reporta.

### Normalizacion

Parametrizada en `config/pesos.yaml`, con cuatro metodos comparables: min-max,
puntuacion z, robusta por mediana y MAD, y rango percentil. Por defecto se
winsoriza antes de escalar y se aplica logaritmo a las variables monetarias.

La justificacion es empirica: el diagnostico de SECOP hallo 13 contratos por
encima de un billon de pesos, con maximo de 2.582 billones frente a una
mediana de 24,6 millones. Sin winsorizar, min-max comprime el 99,9 % de los
registros contra cero.

### Analisis de sensibilidad

Dos ejercicios, en `src/colombiainvest/modelo/sensibilidad.py`:

1. **Comparacion entre esquemas declarados.** Recalcula el score con pesos
   iguales y con tres esquemas de enfasis, y reporta correlacion de Spearman
   y Kendall, desplazamiento de posiciones y estabilidad del top-k.
2. **Perturbacion Monte Carlo.** Perturba los pesos con ruido relativo y mide
   la distribucion de la posicion de cada proyecto.

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
