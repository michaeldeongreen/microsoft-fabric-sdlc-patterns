[English](../../fabric-deployment-plan-guide.md) | **Español**

<!-- source: fabric-deployment-plan-guide.md @ f7f949d | translated: 2026-10-15 -->

> 📄 **La versión en inglés de este documento es la autoritativa.** En caso de discrepancia, [el original en inglés](../../fabric-deployment-plan-guide.md) tiene precedencia.

# Guía de CI/CD con Deployment Plan

Dos adaptadores independientes, mantenidos por este repositorio, leen un
*Deployment Plan* de Fabric guardado en Git: `fabric-cicd-plan` publica de forma
secuencial y no masiva, mientras que `fabric-cicd-bulk` combina grupos
independientes cuyas dependencias ya se han satisfecho en selecciones de
publicación masiva estricta de fabric-cicd. Cada adaptador sustituye las fases
definidas directamente en su propio método.
**fabric-cicd no masivo** (`fabric-cicd`) sigue siendo el método predeterminado
y el punto de partida recomendado de este repositorio; véase la
[Guía de CI/CD no masivo con fabric-cicd](fabric-hybrid-cicd-guide.md).
El método REST directo `bulk` es otro ejemplo alternativo.

Son aceleradores de soluciones que solo controlan el orden de publicación,
no una ejecución nativa de Deployment Plans. Los Deployment Plans están en
versión preliminar y la API de inclusión de elementos de fabric-cicd que se usa
aquí es experimental. El método debe validarse en Test antes de usarlo en
producción. Los *Pipelines* de despliegue nativos de Fabric son un servicio
distinto y ninguno de los dos adaptadores los invoca. La
[comparación del README](README.md#elegir-un-método-de-despliegue) permite elegir
una ruta; la
[referencia compartida de los flujos de trabajo](fabric-release-process.md#flujos-de-trabajo-de-github-actions)
permite localizar el flujo que la invoca y el script que la ejecuta.

> **Límite de compatibilidad:** los responsables de fabric-cicd describen el
> despliegue selectivo como
> «[not a best practice](https://github.com/microsoft/fabric-cicd/issues/384)»
> y afirman que es
> «[not officially supported or recommended](https://github.com/microsoft/fabric-cicd/issues/290#issuecomment-2881790140)».
> Traducción: «no es una práctica recomendada» y «no se admite ni se recomienda
> oficialmente».
> Este puente requiere una responsabilidad explícita, definiciones completas
> de las dependencias, validación fuera de producción y una vía para volver al
> método estándar de despliegue completo. Está pensado para equipos avanzados
> que evalúan una carencia documentada, no como nuevo método predeterminado
> para todos los usuarios de fabric-cicd.

## Cómo funciona

Este recorrido describe **fabric-cicd no masivo con un plan interpretado por
el cliente** (`fabric-cicd-plan`). La ruta masiva de fabric-cicd lee el mismo
formato de plan admitido, pero agrupa elementos independientes cuyas
dependencias ya se han satisfecho; sus instrucciones empiezan en
[Adaptador masivo independiente](#adaptador-masivo-independiente-14x).

<pre>
<a href="../../.github/workflows/deploy-test-fabric-cicd-plan.yml">deploy-test-fabric-cicd-plan.yml</a> / <a href="../../.github/workflows/deploy-prod-fabric-cicd-plan.yml">deploy-prod-fabric-cicd-plan.yml</a>
  (flujos de trabajo de orquestación)
  -&gt; comprobaciones previas de conexiones, creación o reutilización, verificación de Owner y persistencia de IDs
  -&gt; <a href="../../.github/workflows/reusable-deploy-fabric-cicd-plan.yml">reusable-deploy-fabric-cicd-plan.yml</a> (flujo de trabajo reutilizable)
     -&gt; <a href="../../scripts/deploy_fabric_cicd_non_bulk_plan.py">deploy_fabric_cicd_non_bulk_plan.py</a> (adaptador de despliegue)
        -&gt; <a href="../../scripts/deployment_plan.py">deployment_plan.py</a> (lector del plan y planificador)
        -&gt; validar el plan guardado en Git y el inventario del repositorio
        -&gt; publicar los elementos declarados en orden de dependencias
        -&gt; publicar los elementos restantes dentro del ámbito
        -&gt; limpiar los elementos huérfanos que corresponda
  -&gt; trabajo run-etl dependiente en la misma revisión del flujo, tras un despliegue correcto
     -&gt; <a href="../../.github/workflows/reusable-fabric-etl.yml">reusable-fabric-etl.yml</a>
        -&gt; iniciar Patterns_Load_Validate_And_Refresh y esperar a que termine su trabajo Pipeline
           -&gt; carga existente -&gt; validación de solo lectura -&gt; actualización nativa del modelo
</pre>

[deploy_fabric_cicd_non_bulk_plan.py](../../scripts/deploy_fabric_cicd_non_bulk_plan.py)
llama a [deployment_plan.py](../../scripts/deployment_plan.py), que lee
[plan.yml](../../data/fabric/DeploymentPlan.DeploymentPlan/plan.yml) desde la
misma revisión de Git que las definiciones de los elementos.
[deployment_plan.py](../../scripts/deployment_plan.py) relaciona los IDs
lógicos de los grupos con los
[metadatos `.platform`](../../data/fabric/PatternsLakehouse.Lakehouse/.platform)
de cada elemento, no con los IDs físicos de los elementos del workspace.
Las conexiones entre grupos se convierten en entradas `dependsOn`; la posición
del grupo en YAML o en el lienzo no determina el orden.

Esta correspondencia sigue el modelo de identidad de Fabric. Microsoft define
el ID lógico como la identidad generada automáticamente que vincula un elemento
de Fabric con su representación en Git y se conserva entre workspaces.
Los grupos de un Deployment Plan usan ese mismo ID lógico para que el plan
siga siendo válido cuando los elementos se trasladan entre workspaces. Véanse
[IDs lógicos en la integración de Git de Fabric](https://learn.microsoft.com/en-us/fabric/cicd/git-integration/logical-id-conflict-resolution)
y [ejemplos de Deployment Plan](https://learn.microsoft.com/en-us/fabric/cicd/deployment-plan/deployment-plan-sample-plans#understand-the-planyml-structure).

[deployment_plan.py](../../scripts/deployment_plan.py) rechaza los IDs lógicos
ausentes, con valor cero, mal formados y duplicados antes de la autenticación o el
despliegue. El riesgo restante es la desviación de los metadatos: sustituir un
ID lógico al resolver un conflicto de Git cambia la identidad del elemento y
obliga a actualizar el plan guardado en Git. Deben conservarse los IDs lógicos
generados por Fabric y revisarse los avisos de sobrescritura de metadatos antes
de aceptarlos.

El plan ordena las dependencias de publicación, entre ellas:

```text
Lakehouse -> Patterns_Semantic_Model ───────────┐
          -> Patterns_Variables ────────────────┤
          -> Import_Patterns_Data ──────────────┼-> DataPipeline
          -> Validate_Patterns_Data ────────────┘
          -> Ontology -> Data Agent
```

Las definiciones que necesita el DataPipeline deben existir antes de
publicarlo. Estas dependencias **no** ejecutan la carga, validan datos ni
actualizan el modelo. Las dependencias de éxito del DataPipeline controlan
esa secuencia independiente en tiempo de ejecución.
El plan guardado en Git tiene ocho grupos declarados. Su orden secuencial
determinista es `Lakehouse_Group` → `Import_Group` → `Ontology_Group` →
`SemanticModel_Group` → `Validation_Group` → `Variables_Group` →
`DataAgent_Group` → `Pipeline_Group`. Los comandos de vista previa que aparecen
más adelante permiten comprobar la planificación tras cambiar el plan o el
inventario.

En el método no masivo, cada elemento declarado recibe una llamada
`publish_all_items(..., items_to_include=...)` independiente, con el estado del
workspace obtenido de nuevo. Las llamadas posteriores pueden así resolver los
IDs de destino creados por las anteriores. Los grupos independientes se
procesan de forma secuencial y determinista, no en paralelo.

[deployment_plan.py](../../scripts/deployment_plan.py) descubre los elementos
restantes a partir de los metadatos del repositorio y de `ITEM_TYPE_IN_SCOPE`.
[deploy_fabric_cicd_non_bulk_plan.py](../../scripts/deploy_fabric_cicd_non_bulk_plan.py)
los publica en una llamada adicional a la biblioteca, con el orden estándar
de fabric-cicd.
Actualmente quedan tres elementos: `Patterns_Demo`, `Patterns_Patients_Data`
y `Patterns_Report`. La Variable Library, la carga, la validación y el
DataPipeline tienen ahora grupos explícitos en lugar de pertenecer a los
elementos restantes. Un plan personalizado puede producir otro inventario;
debe previsualizarse el grafo.
Para esta muestra de 11 elementos, la publicación no masiva con plan hace nueve
llamadas a la biblioteca —ocho grupos declarados y una selección de elementos
restantes—, no nueve solicitudes HTTP.
El elemento de control DeploymentPlan no se publica ni se elimina como
huérfano.

## Adaptador masivo independiente (1.4.x)

[deploy_fabric_cicd_bulk.py](../../scripts/deploy_fabric_cicd_bulk.py) llama a
[deployment_plan_bulk.py](../../scripts/deployment_plan_bulk.py). La ruta masiva
mantiene su propio inventario, análisis seguro de YAML, validación, planificador
y orquestación; ninguno de esos módulos importa la implementación del plan no
masivo. Ambos lectores admiten el mismo esquema, limitado al orden de
publicación, pero el código de Python está separado deliberadamente.

Solo las entradas explícitas `dependsOn` determinan si un grupo está listo.
Los grupos independientes que ya tienen satisfechas sus dependencias se
combinan en una selección exacta de fabric-cicd; no se envían en paralelo.
El plan actual da al DataPipeline dependencias explícitas de
`Patterns_Variables`, `Import_Patterns_Data`, `Validate_Patterns_Data` y
`Patterns_Semantic_Model`.
Para la muestra de 11 elementos guardada en Git, la planificación de solo
lectura es:

| Selección | Número de elementos | Grupos o elementos restantes |
|---|---|---|
| Lote declarado 1 | 1 | Lakehouse |
| Lote declarado 2 | 5 | Import, Ontology, SemanticModel, Validation, Variables |
| Lote declarado 3 | 2 | DataAgent, Pipeline |
| Restantes | 3 | `Patterns_Demo`, `Patterns_Patients_Data`, `Patterns_Report` |

Son cuatro selecciones de la biblioteca, con `[1, 5, 2, 3]` elementos.
El contrato de transporte comprobado sin conexión espera cuatro POST de
importación masiva de definiciones para esta muestra; los GET de inventario,
los PATCH de activación de conjuntos de valores y los DELETE de limpieza son
solicitudes HTTP adicionales.
Estas cifras no son evidencia de un despliegue real ni un orden de tipos
definido directamente: al cambiar las dependencias o el inventario, cambia la
planificación. Debe previsualizarse el plan guardado en Git después de cambiarlo.
Cada llamada obtiene de nuevo el estado del workspace y usa tipos de elemento
explícitos y selectores de inclusión exactos `Name.ItemType`.
En otros repositorios, fabric-cicd puede dividir una selección en más lotes
internos de dependencias; una llamada a la biblioteca no equivale a un número
fijo de solicitudes HTTP.

### Habilitar y previsualizar la ruta masiva

El código y los flujos de trabajo actualizados deben promoverse mediante los
controles existentes antes de cambiar el método para todo el repositorio.
Copie los valores de las dos variables del repositorio indicadas en
[Configuración: variables del método de despliegue](SETUP.md#variables-del-método-de-despliegue)
y use los secretos de entorno compartidos que se describen allí. Esta ruta
solo debe seleccionarse cuando esté preparada para una validación autorizada
en Test.
Los flujos de Test y Prod proporcionan un ámbito explícito de ocho tipos,
incluido `DataPipeline`. A diferencia de la ruta no masiva, omitir el ámbito o
dejarlo vacío es un error; no selecciona todos los tipos de forma predeterminada.

Desde la raíz del repositorio, con las dependencias instaladas:

```powershell
$env:ITEM_TYPE_IN_SCOPE = '["Lakehouse","Ontology","VariableLibrary","Notebook","SemanticModel","Report","DataAgent","DataPipeline"]'
python scripts\deploy_fabric_cicd_bulk.py --plan data\fabric\DeploymentPlan.DeploymentPlan\plan.yml --dry-run
```

La vista previa devuelve `batches`, `remainingItems`, `itemTypesInScope`,
`cleanupItemTypes` y la versión de fabric-cicd instalada, sin credenciales ni
llamadas a Fabric. Un plan ausente o no válido nunca restablece las fases ni
cambia de método.
Si se proporciona `ENVIRONMENT`, la vista previa también comprueba los metadatos
de los conjuntos de valores seleccionados en la Variable Library; sigue siendo
opcional para una vista previa local sin credenciales.
Ambos flujos de publicación masiva generan la vista previa antes de recibir
los secretos de Azure/Fabric en el paso de despliegue. Sus filtros de rutas
cubren las definiciones de Fabric, `deployment-plans/`, los scripts exclusivos
de la ruta masiva, las dependencias y los flujos de trabajo. Si el plan se
guarda en otro directorio, debe añadirse a los filtros de ambos flujos que lo
invocan.

<a id="sdk-replacements-and-strict-success"></a>

### Sustituciones de fabric-cicd y requisitos de éxito

fabric-cicd 1.4.0 admite las reglas dinámicas filtradas de
[parameter.yml](../../data/fabric/parameter.yml) de este repositorio con la
publicación masiva habilitada. fabric-cicd se encarga de las sustituciones y
de activar los conjuntos de valores de Test/Prod. La ruta masiva no incorpora
el motor de búsqueda y reemplazo de REST directo ni lee
[bulk-parameter.yml](../../data/fabric/bulk-parameter.yml).
Las reglas del DataPipeline sustituyen los IDs de referencia de Dev del modelo
y las conexiones. Los scripts habilitan la sustitución `$ENV:` y validan
`NOTEBOOK_CONNECTION_ID` y `SEMANTIC_MODEL_REFRESH_CONNECTION_ID` antes de
publicar. Son
[variables de entorno](SETUP.md#variables-de-entorno-y-del-repositorio),
no credenciales ni instrucciones para crear conexiones.
Antes de la autenticación en línea, el adaptador exige que cada Variable Library
seleccionada declare el nombre exacto del entorno y contenga el archivo de
conjunto de valores correspondiente. Si faltan metadatos o no coinciden,
se detiene en lugar de permitir que fabric-cicd active `Default` u omita la
activación sin avisar. No hace un segundo PATCH de activación.

Para que esa comprobación siga siendo válida después de parametrizar, se
ejecutan comprobaciones previas autenticadas y de solo lectura de las reglas
de fabric-cicd para todas las bibliotecas seleccionadas antes de la primera
importación de definiciones, y de nuevo para cada selección.
Esto no forma parte de `--dry-run`.
Los archivos de control de la biblioteca `settings.json` y `valueSets/*.json`,
incluido el contenido de las sobrescrituras, deben conservar sus valores
literales. Se rechazan las reglas activas `find_replace` que coincidan con el
contenido de esos archivos de control. También se rechaza cualquier regla
`key_value_replace` cuyos filtros los incluyan: fabric-cicd vuelve a serializar
el JSON aunque no coincidan la clave ni el entorno, lo que puede permitir que
una regla de texto posterior cambie los metadatos de activación.
Las reglas de sustitución por clave y valor de la biblioteca deben limitarse
a `**/variables.json`; los archivos normales de la carga de trabajo y las
variables de la biblioteca siguen usando la parametrización de fabric-cicd.
Las reglas guardadas en Git no se ven afectadas. Es una restricción de seguridad
conservadora del adaptador, no una limitación de fabric-cicd.

El adaptador solicita funciones experimentales, publicación masiva, inclusión
de elementos y recopilación de respuestas. Rechaza los tipos no aptos para
publicación masiva y usa la función auxiliar de elegibilidad, de solo lectura,
de la versión acotada 1.4.x de fabric-cicd para rechazar las reglas `$items` del
workspace actual sin filtros antes de publicar. Usa las API públicas de
publicación, no llamadas de transporte privadas ni modificaciones de fabric-cicd.

Después de cada selección exige `bulk_publish_enabled=True` real y resultados
completos, identificados correctamente, con `operationStatus=Succeeded` e IDs
de destino válidos para todos los elementos. Los resultados fallidos, parcialmente
correctos, desconocidos, ausentes o mal formados detienen las selecciones
dependientes, la publicación de los elementos restantes y la limpieza de
huérfanos.
La comprobación del modo se ejecuta después de que termine `publish_all_items`:
las causas conocidas de retorno a la publicación estándar se rechazan antes
de publicar, pero un retorno inesperado puede haber realizado ya escrituras
estándar. Que la ejecución falle no las deshace.
Se han eliminado `FAIL_IF_BULK_USED` y `fail_if_bulk_used`; elegir esta ruta
exige una publicación realmente masiva. Para publicar de forma estándar debe
seleccionarse la ruta estándar.

Solo después de publicar correctamente, el adaptador ejecuta una vez la
limpieza de huérfanos existente de fabric-cicd. Lakehouse, Ontology y
DeploymentPlan siguen excluidos. Los GET de inventario, los PATCH de acciones
posteriores o activación de fabric-cicd y los DELETE de limpieza son solicitudes
independientes legítimas, no un retorno a la publicación estándar de definiciones.

### Comportamiento verificado del cliente y comprobaciones pendientes del servicio

[Las pruebas del contrato masivo](../../tests/test_deploy_fabric_cicd_bulk.py)
ejecutan el código real de publicación y parametrización de la versión publicada
1.4.0, con solo HTTP simulado y las solicitudes reales bloqueadas.
Los casos de prueba con un destino vacío y otro con elementos ya existentes
ejercitan el archivo de parámetros, las sustituciones físicas, las solicitudes
de activación y la ausencia de POST de definiciones estándar.
Los nombres de sus etapas describen casos de prueba sin conexión, no una
validación real de Test/Prod.
También cubren resultados parciales, fallidos o ausentes, parámetros no válidos,
exclusiones de limpieza y la ausencia de cambios en los archivos de origen.
Las pruebas de regresión de la revisión adversarial rechazan las sustituciones
de metadatos de activación y las reglas encadenadas de clave/valor y texto
antes de importar definiciones, activar o limpiar, y permiten las reglas de
texto inactivas o sin coincidencias y las sustituciones por clave y valor
válidas limitadas a las variables de la biblioteca.

La carga útil masiva conserva `datasetReference.byPath` del Report; no realiza
la conversión a `byConnection` de la publicación estándar. El plan coloca el
Semantic Model antes del Report, pero una prueba real en Test debe verificar
la vinculación del Report y las relaciones Lakehouse–Ontology y
Ontology–DataAgent entre importaciones. El éxito simulado del cliente no
demuestra las vinculaciones del servicio, la Fabric Capacity, las conexiones,
el conjunto de valores activo ni el ETL.
Debe usarse un destino desechable autorizado para un despliegue inicial y una
repetición con los elementos ya existentes; nunca debe vaciarse un workspace
compartido.

## Aplicabilidad de los cambios de la versión 1.4.0

Todos los flujos de trabajo de fabric-cicd y
[requirements-dev.txt](../../requirements-dev.txt) usan
`fabric-cicd>=1.4.0,<1.5.0`; el adaptador masivo rechaza las versiones
incompatibles. Actions sigue usando Python 3.12. Se prueba el límite inferior
exacto 1.4.0.

| Cambio de la versión | Tratamiento en este repositorio |
|---|---|
| Variables dinámicas masivas y validación temprana de sintaxis | Ejercitar las sustituciones reales de fabric-cicd y rechazar la sintaxis no válida antes de escribir definiciones; probar por separado los recursos ausentes. |
| Eliminación del atributo `contains_param_vars` | Eliminar la dependencia anterior para informar del modo; la presencia de variables de elemento no demuestra un retorno a la publicación estándar. |
| Compatibilidad con GraphModel y CosmosDBDatabase | No hay elementos independientes de estos tipos aquí. No debe ampliarse el ámbito de publicación o limpieza ni eliminarse las advertencias de configuración de Ontology. |
| Compatibilidad con Python 3.14 | Es una capacidad heredada de la biblioteca, no un motivo para cambiar la versión de Python usada en Actions en este repositorio. |
| Correcciones de KQLQueryset, PaginatedReport y Activator | Se heredan las correcciones; estos tipos no están en el inventario. `Report` no es `PaginatedReport`. |
| Corrección de la barra final en conexiones de Semantic Model | Se aplica a las solicitudes `bindConnection` de fabric-cicd; aquí no se configura `semantic_model_binding`. No implica que toda la configuración de conexiones esté resuelta. |
| Tratamiento de nombres `$ENV:` | Usar los nombres exactos en mayúsculas de las variables de conexión de Notebook y actualización en las reglas del DataPipeline; los scripts habilitan la sustitución de variables de entorno. REST directo conserva su motor de sustituciones independiente. |
| Límite por una regresión de jsonpath-ng | Respetar la restricción transitiva `>=1.7.0,<1.8.0` de fabric-cicd, sin fijar otra dependencia directa redundante. No se añaden reglas activas `key_value_replace`. |
| Nuevo tutorial de principio a fin | Material de referencia, no un sustituto de la arquitectura del repositorio. |

Véanse el
[registro de cambios de la versión](https://microsoft.github.io/fabric-cicd/1.4.0/changelog/#v140-october-07-2026)
y las
[limitaciones de publicación masiva](https://microsoft.github.io/fabric-cicd/1.4.0/how_to/optional_feature/#bulk-publish).

## Flujos de trabajo y scripts

Los siguientes archivos implementan la **ruta no masiva con plan**. Para su
equivalente masivo y las demás familias de flujos de trabajo, véase la
[referencia compartida de los flujos de trabajo](fabric-release-process.md#flujos-de-trabajo-de-github-actions).

| Archivo | Función |
|---|---|
| [deploy-test-fabric-cicd-plan.yml](../../.github/workflows/deploy-test-fabric-cicd-plan.yml) | Despliega ante cambios que cumplan los filtros en `test`; también admite ejecuciones manuales en `test`. |
| [deploy-prod-fabric-cicd-plan.yml](../../.github/workflows/deploy-prod-fabric-cicd-plan.yml) | Despliega ante cambios que cumplan los filtros en `main`, con el entorno `Prod` y las protecciones configuradas. |
| [reusable-deploy-fabric-cicd-plan.yml](../../.github/workflows/reusable-deploy-fabric-cicd-plan.yml) | Instala las dependencias, previsualiza la planificación y ejecuta [deploy_fabric_cicd_non_bulk_plan.py](../../scripts/deploy_fabric_cicd_non_bulk_plan.py). |
| [deploy_fabric_cicd_non_bulk_plan.py](../../scripts/deploy_fabric_cicd_non_bulk_plan.py) | Se autentica con `ClientSecretCredential` y orquesta las llamadas públicas de fabric-cicd. |
| [deployment_plan.py](../../scripts/deployment_plan.py) | Valida el formato de plan admitido y calcula el orden declarado y los elementos restantes. |

[deploy-test-fabric-cicd-plan.yml](../../.github/workflows/deploy-test-fabric-cicd-plan.yml)
y
[deploy-prod-fabric-cicd-plan.yml](../../.github/workflows/deploy-prod-fabric-cicd-plan.yml)
usan los mismos secretos de ámbito de entorno, comprobaciones previas de
conexiones WI existentes y ámbito de ocho tipos que el método estándar.
Antes de iniciar el publicador, cada trabajo seleccionado crea o reutiliza el
par WI de la etapa, verifica que el grupo administrador de conexiones tenga
Owner y guarda los IDs que falten. No hace falta otra credencial del workspace
de origen. Sus trabajos ETL dependientes usan la misma revisión;
[deploy_fabric_cicd_non_bulk_plan.py](../../scripts/deploy_fabric_cicd_non_bulk_plan.py)
no ejecuta por sí mismo el ETL ni la actualización del modelo.
Ambos métodos con plan usan el mismo
[proceso posterior al ETL](fabric-release-process.md#actualización-del-semantic-model-posterior-al-etl)
que las rutas predeterminada no masiva y REST directa: GitHub inicia y sondea
un único DataPipeline; Fabric ejecuta carga → validación de solo lectura →
actualización nativa y espera a que termine. CI no es un segundo responsable
de la actualización.

## Habilitar el método

Este apartado habilita **`fabric-cicd-plan`**, no la publicación masiva de
fabric-cicd. Para `fabric-cicd-bulk`, véase
[Habilitar y previsualizar la ruta masiva](#habilitar-y-previsualizar-la-ruta-masiva).

Debe completarse primero la [Guía de configuración](SETUP.md). Mantenga
seleccionado el método existente mientras promueve
[deploy-test-fabric-cicd-plan.yml](../../.github/workflows/deploy-test-fabric-cicd-plan.yml),
[deploy-prod-fabric-cicd-plan.yml](../../.github/workflows/deploy-prod-fabric-cicd-plan.yml)
y
[reusable-deploy-fabric-cicd-plan.yml](../../.github/workflows/reusable-deploy-fabric-cicd-plan.yml)
por `dev -> test -> main`.
El ETL automático usa `needs`, no un flujo que escucha eventos desde la rama
predeterminada. Los archivos de los flujos de trabajo aún tienen que existir
en la rama predeterminada para que la interfaz de ejecución manual de Actions
los muestre. Deben terminar las ejecuciones en curso antes de cambiar el selector.

En `Settings > Secrets and variables > Actions > Variables` del repositorio,
establezca:

| Variable | Valor |
|---|---|
| `DEPLOYMENT_PLAN_PATH` | [`data/fabric/DeploymentPlan.DeploymentPlan/plan.yml`](../../data/fabric/DeploymentPlan.DeploymentPlan/plan.yml) |
| `DEPLOY_METHOD` | `fabric-cicd-plan` |

Después:

1. Compruebe que no siga ejecutándose ningún despliegue del método anterior.
2. En Actions, seleccione `Deploy to Test (fabric-cicd Plan)` y ejecútelo en la
   rama `test`, o fusione en `test` un cambio que cumpla los filtros.
3. Revise la planificación, el despliegue y los resultados del ETL con las
   comprobaciones siguientes.
4. Promueva a `main` cuando Test pase. Se aplica la protección configurada
   para el entorno Prod; el repositorio no crea esa protección.

Una ejecución manual de
[deploy-test-fabric-cicd-plan.yml](../../.github/workflows/deploy-test-fabric-cicd-plan.yml)
en otra rama se omite.
[deploy-test-fabric-cicd-plan.yml](../../.github/workflows/deploy-test-fabric-cicd-plan.yml)
y
[deploy-prod-fabric-cicd-plan.yml](../../.github/workflows/deploy-prod-fabric-cicd-plan.yml)
no cancelan un despliegue con plan que ya esté en curso. Las rutas seleccionadas
comparten un grupo de concurrencia por etapa: los lanzamientos de Test se
ejecutan de uno en uno junto con los demás métodos seleccionados para Test;
lo mismo ocurre con los de Prod.

[deploy-test-fabric-cicd-plan.yml](../../.github/workflows/deploy-test-fabric-cicd-plan.yml)
y
[deploy-prod-fabric-cicd-plan.yml](../../.github/workflows/deploy-prod-fabric-cicd-plan.yml)
se activan ante cambios en las definiciones de Fabric, `deployment-plans/`,
los nuevos scripts, las dependencias y los archivos de flujos de trabajo.
Si el plan se guarda en otro lugar, debe añadirse ese directorio a la lista
`paths` de ambos archivos.

## Previsualizar y personalizar

El siguiente comando previsualiza **el orden no masivo**. La
[vista previa masiva](#habilitar-y-previsualizar-la-ruta-masiva) informa de
lotes listos para publicar en lugar de una lista secuencial de grupos.

Desde la raíz del repositorio, después de instalar
[requirements-dev.txt](../../requirements-dev.txt):

El comando invoca
[deploy_fabric_cicd_non_bulk_plan.py](../../scripts/deploy_fabric_cicd_non_bulk_plan.py)
con el
[plan.yml](../../data/fabric/DeploymentPlan.DeploymentPlan/plan.yml) guardado
en Git.

```powershell
python scripts\deploy_fabric_cicd_non_bulk_plan.py --plan data\fabric\DeploymentPlan.DeploymentPlan\plan.yml --dry-run
```

La salida JSON enumera `groups` en orden de ejecución, `remainingItems`,
`itemTypesInScope` y `cleanupItemTypes`. El modo de simulación no requiere
credenciales de Azure ni hace llamadas a Fabric. Valida los metadatos locales
y el grafo definido en el plan; no verifica los permisos del inquilino, las
vinculaciones reales ni que los datos estén preparados.

Para personalizar:

- Edite el plan y haga *commit* en Fabric, o seleccione otro plan guardado en
  Git con `DEPLOYMENT_PLAN_PATH`. Las rutas son relativas al repositorio local.
- Declare los elementos cuyo orden importa, incluidos sus requisitos previos.
  [deploy_fabric_cicd_non_bulk_plan.py](../../scripts/deploy_fabric_cicd_non_bulk_plan.py)
  publica los elementos no enumerados después de todos los grupos declarados.
- Mantenga vacías las secciones Before/After. Ejecutan trabajos en la
  ejecución nativa de Fabric; no son listas de elementos que deban desplegarse
  a continuación.
- Mantenga el ID lógico de cada elemento distinto de cero, estable y único,
  incluidos los elementos no enumerados. La integración de Git de Fabric
  proporciona estos IDs portables.
- Ajuste el ámbito de tipos de elemento de
  [deploy-test-fabric-cicd-plan.yml](../../.github/workflows/deploy-test-fabric-cicd-plan.yml)
  y
  [deploy-prod-fabric-cicd-plan.yml](../../.github/workflows/deploy-prod-fabric-cicd-plan.yml)
  al añadir tipos de carga de trabajo compatibles. Un grupo fuera de ese
  ámbito es un error, no una ampliación implícita del ámbito.

Aquí el Report no necesita su propio grupo porque su Semantic Model se
despliega antes de los elementos restantes. Del mismo modo, un repositorio
de 500 elementos puede usar un plan breve para aquellos cuyo orden es crítico;
no necesita un grupo por elemento.
No se descubren las dependencias ocultas en código o ausentes del plan.
Cada organización es responsable de que el grafo de dependencias declarado
esté completo; fabric-cicd no valida que las llamadas selectivas incluyan
todos los requisitos previos.

## Configuración y límites ante fallos

Este apartado describe el comportamiento de **fabric-cicd no masivo con un
plan interpretado por el cliente**. Las protecciones adicionales del modo
masivo sobre el modo de publicación, las respuestas y la Variable Library se
documentan en
[Sustituciones de fabric-cicd y requisitos de éxito](#sustituciones-de-fabric-cicd-y-requisitos-de-éxito).

fabric-cicd sigue aplicando [parameter.yml](../../data/fabric/parameter.yml),
resolviendo los IDs físicos y seleccionando el conjunto de valores de la
Variable Library para `Test` o `Prod`.
Los IDs de origen y las reglas de sustitución deben mantenerse alineados,
y las vinculaciones de Dev deben restaurarse antes de la promoción, como
se describe en el [Proceso de desarrollo](fabric-development-process.md).
Leer un plan no sustituye la parametrización.
El trabajo seleccionado de Test/Prod crea o reutiliza automáticamente las
conexiones Notebook y Power BI datasets con Workspace Identity del destino
antes de ejecutar el publicador. Verifica Owner para el grupo configurado y
guarda los GUID que falten. El publicador usa después esas conexiones en modo
de solo lectura. Véase
[Proceso de lanzamiento](fabric-release-process.md#de-dev-a-test).
Que el ID lógico de DeploymentPlan sea portable no hace portables los GUID
físicos del modelo y las conexiones del DataPipeline.
Los nombres de entorno y de conjunto de valores deben coincidir exactamente.
Si no hay un nombre coincidente, fabric-cicd avisa y usa el conjunto de valores
predeterminado; deben conservarse los conjuntos `Test` y `Prod` guardados en
Git y verificarse el conjunto activo después del despliegue.

[deployment_plan.py](../../scripts/deployment_plan.py) rechaza los elementos
ausentes, los nombres o IDs ambiguos, los ciclos, las versiones de esquema no
admitidas y las acciones u opciones de grupo no vacías. Admite el formato de
ordenación 1.0.0, hasta 1 000 grupos y archivos de plan de hasta 1 MiB.
Cuantos más grupos se declaren, más llamadas secuenciales a la biblioteca y
consultas al workspace se realizan.

La limpieza de huérfanos se ejecuta una vez, solo después de que termine
correctamente toda la publicación. Como el flujo estándar actual, excluye
Lakehouse y Ontology; DeploymentPlan también queda excluido.
La limpieza puede eliminar elementos del destino que no estén en el repositorio,
dentro de los demás tipos configurados. Deben usarse workspaces administrados
por el repositorio, no workspaces compartidos que contengan otros elementos
de esos tipos. Durante la limpieza, la biblioteca también puede eliminar
carpetas vacías del workspace.

Una excepción durante la publicación o la limpieza detiene el trabajo posterior
e impide el ETL automático. Los cambios ya realizados no se revierten.
También deben revisarse las advertencias de la biblioteca; los fallos deben
corregirse y los resultados parciales inspeccionarse antes de repetir la
ejecución.
Para volver al método anterior, restablezca su valor de `DEPLOY_METHOD`;
esto cambia el método de las ejecuciones futuras, no el estado ya desplegado.

El recopilador Bulk de REST directo excluye las carpetas de control
DeploymentPlan para que el nuevo elemento sincronizado con Git no altere la
carga útil de trabajo de ese método anterior. No adjunta ni ejecuta el plan.
El script estándar sin plan usa sus propias fases de publicación; la
ordenación no masiva con plan y la planificación masiva de la biblioteca
siguen siendo adaptadores independientes.

## Verificar antes de producción

Debe usarse un destino Test autorizado y comprobarse lo siguiente:

- El registro indica la versión de fabric-cicd instalada y el modo seleccionado:
  publicación estándar o masiva estricta.
- Todos los elementos declarados y restantes, incluidos el nuevo Notebook de
  validación y el DataPipeline, se despliegan sin duplicados en el orden
  previsualizado.
- Los campos de destino de Notebook, Semantic Model y DataPipeline —modelo
  y conexiones— y el ID del Lakehouse de la Variable Library contienen las
  sustituciones esperadas. Los valores predeterminados de Dev que un conjunto
  de valores activo sobrescribe de forma intencionada no tienen que desaparecer
  de todos los archivos.
- En la ruta masiva, se verifican las vinculaciones Report–modelo y por ID
  lógico entre importaciones; no deben inferirse de las pruebas de solicitudes
  del cliente.
- El conjunto de valores correcto está activo antes de que el flujo ETL
  existente se ejecute una sola vez.
- El Service principal de CI puede publicar e iniciar el DataPipeline; sus
  actividades con Workspace Identity completan carga → validación →
  actualización nativa. Después del despliegue de CI se verifican la transmisión
  del umbral y la etiqueta, y la propiedad del modelo.
- Se verifican por separado los campos de fecha necesarios del modelo, los
  cálculos y las rutas de acceso de los consumidores; la validación del origen
  y una actualización correcta no son evidencia de consultas.
- Un segundo despliegue actualiza los mismos IDs de elemento en lugar de crear
  duplicados.
- La limpieza afecta solo a los elementos y tipos huérfanos esperados.

Siguen aplicándose las
[advertencias para un workspace vacío](fabric-hybrid-cicd-guide.md#primer-despliegue-en-un-workspace-vacío),
incluida la inicialización de Ontology/Graph Model.
Desplegar un Notebook no carga las tablas; publicar `SemanticModel_Group`
no lo actualiza después de las escrituras de la carga.
El orden por sí solo no sustituye la ejecución del DataPipeline, el
*framing* de Direct Lake ni la configuración de conexiones. El proceso
posterior no adjunta un plan nativo ni cambia el orden de publicación de
ninguno de los adaptadores.
Las pruebas sin conexión cubren la planificación y parametrización de
fabric-cicd con un transporte simulado; no demuestran que la ruta con plan
se haya desplegado correctamente en el inquilino.
La ruta Test no masiva predeterminada está verificada con una ejecución real,
pero ninguno de los adaptadores con plan tiene evidencia real de la revisión
actual. Véase la
[matriz compartida de verificación](fabric-release-process.md#estado-de-la-verificación).

## Relación con los Deployment Plans nativos

La ejecución nativa de Fabric combina las relaciones del plan con el linaje
detectado y puede ejecutar acciones.
[deploy_fabric_cicd_non_bulk_plan.py](../../scripts/deploy_fabric_cicd_non_bulk_plan.py)
solo aplica el orden declarado mediante fabric-cicd no masivo;
[deploy_fabric_cicd_bulk.py](../../scripts/deploy_fabric_cicd_bulk.py) lo hace
mediante llamadas masivas agrupadas. Ninguno adjunta un plan ni ejecuta
acciones Before/After nativas. El elemento de control DeploymentPlan no se
importa ni se elimina como huérfano.

REST de Fabric acepta `options.deploymentPlan`, pero fabric-cicd 1.4.0 no lo
expone en su API pública de publicación. El adaptador masivo independiente
debe mantenerse como un puente sustituible cuando se publique y verifique
una integración masiva nativa adecuada de fabric-cicd. Esto no implica
compatibilidad nativa no masiva ni retira el ejemplo no masivo independiente.

Las actualizaciones de fabric-cicd deben volver a probarse. Al migrar la ruta
masiva a una ejecución nativa del plan, deben reevaluarse los elementos no
enumerados, las acciones, los permisos, la gestión de fallos y la
parametrización: Fabric combina el plan nativo con el linaje y el orden
estándar, mientras que estos adaptadores publican deliberadamente los
elementos no enumerados después de los grupos definidos en el plan.

Referencias:
[automatización de planes de Fabric](https://learn.microsoft.com/en-us/fabric/cicd/deployment-plan/deployment-plan-automation),
[semántica y limitaciones de los planes](https://learn.microsoft.com/en-us/fabric/cicd/deployment-plan/deployment-plan-overview)
e
[inclusión de elementos de fabric-cicd](https://microsoft.github.io/fabric-cicd/1.4.0/how_to/optional_feature/#item-level-filtering).

---

## Sobre esta traducción

Este documento es una traducción de
[fabric-deployment-plan-guide.md](../../fabric-deployment-plan-guide.md).
El original en inglés es la fuente autorizada y puede recibir cambios antes
que esta traducción. Las incidencias pueden comunicarse indicando el idioma.
Los enlaces a documentación externa apuntan al inglés para mantener la
terminología de referencia; el idioma puede cambiarse en el sitio de destino.
