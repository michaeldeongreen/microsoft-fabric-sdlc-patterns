[English](../../fabric-bulk-cicd-guide.md) | **Español**

<!-- source: fabric-bulk-cicd-guide.md @ f7f949d | translated: 2026-10-15 -->

> 📄 **La versión en inglés de este documento es la de referencia.** En caso de discrepancia, [el original en inglés](../../fabric-bulk-cicd-guide.md) tiene precedencia.

# Guía de CI/CD masivo con llamadas REST directas

Esta es la ruta masiva de REST directo con código Python propio (`DEPLOY_METHOD=bulk`), no la publicación masiva de fabric-cicd. Para esta última, con sustituciones gestionadas por la biblioteca, debe consultarse la [guía de Deployment Plan](fabric-deployment-plan-guide.md#adaptador-masivo-independiente-14x). La [matriz del README](README.md#elegir-un-método-de-despliegue) compara las cuatro implementaciones.

Esta ruta publica la carga de trabajo del ejemplo mediante la [API Bulk Import Item Definitions](https://learn.microsoft.com/en-us/rest/api/fabric/core/items/bulk-import-item-definitions). La implementación predeterminada se documenta en la [Guía de CI/CD con fabric-cicd sin publicación masiva](fabric-hybrid-cicd-guide.md).

Las [Opciones de lanzamiento de CI/CD](fabric-cicd-release-options.md#herramientas-dentro-de-la-opción-3-fabric-cicd-frente-a-las-api-masivas) comparan estratégicamente fabric-cicd con las API masivas y explican la recomendación.

La API Bulk Import no aplica la parametrización de este repositorio, no activa el conjunto de valores de destino de la *Variable Library* ni elimina elementos huérfanos. El cliente propio implementa los dos primeros comportamientos. Sigue siendo un ejemplo cuyo mantenimiento corresponde a quien lo adopta, no una corrección de la plataforma.

La referencia actual de la API de Microsoft muestra el extremo v1 sin `?beta=true`. El cliente versionado todavía envía ese parámetro antiguo y no se ha verificado en un entorno real con el contrato actual. Antes de seleccionar `bulk`, hay que volver a validar y actualizar el cliente. La ruta predeterminada sin publicación masiva está verificada en Test; REST masivo directo no lo está.

---

## Índice

- [Visión general de la arquitectura](#visión-general-de-la-arquitectura)
- [Estructura del repositorio](#estructura-del-repositorio)
- [Flujo de despliegue](#flujo-de-despliegue)
- [Flujos de trabajo de GitHub Actions](#flujos-de-trabajo-de-github-actions)
- [Estrategia de configuración](#estrategia-de-configuración)
- [La decisión de desplegar por fases](#la-decisión-de-desplegar-por-fases)
- [Requisitos previos y configuración](#requisitos-previos-y-configuración)
- [Primer despliegue en un workspace vacío](#primer-despliegue-en-un-workspace-vacío)
- [Problemas habituales y decisiones clave](#problemas-habituales-y-decisiones-clave)
- [Ampliar la implementación masiva](#ampliar-la-implementación-masiva)
- [Limitaciones no resueltas](#limitaciones-no-resueltas)
- [Referencias](#referencias)

---

## Visión general de la arquitectura

```
Repositorio Git (rama dev)
  │
  │  Merge del PR → rama test
  ▼
┌──────────────────────────────────────────────────────────────┐
│  deploy-test-bulk.yml (orquestador)                          │
│                                                              │
│  crear/reutilizar y verificar conexiones WI de Test;         │
│  guardar sus IDs                                             │
│                                                              │
│  deploy-bulk                                                 │
│    └─ reusable-deploy-bulk.yml                               │
│       └─ scripts/deploy_fabric_rest_bulk.py                  │
│          (Fase 1: POST de dependencias                       │
│           — Lakehouse + Ontology)                            │
│          (Fase 2: POST de dependientes no DataPipeline)      │
│          (Fase 3: sustituir el ID del modelo de destino;     │
│           POST de DataPipeline)                              │
│          (Después: PATCH del conjunto activo                 │
│           de VariableLibrary)                                │
└──────────────────────────────────────────────────────────────┘
                     │ needs: deploy-bulk
                     ▼
┌──────────────────────────────────────────────────────────────┐
│  deploy-test-bulk.yml: run-etl (misma revisión)              │
│    └─ reusable-fabric-etl.yml                                │
│       └─ API REST de Fabric: ejecutar DataPipeline y esperar │
└──────────────────────────────────────────────────────────────┘
                     │ dependencias de actividades de Fabric
                     ▼
    Import_Patterns_Data → Validate_Patterns_Data
       → actualización nativa de Patterns_Semantic_Model
```

El mismo contrato versionado se aplica a Prod, pero ni Test ni Prod disponen de evidencias actuales de REST masivo directo en un entorno real. El [Proceso de lanzamiento](fabric-release-process.md) documenta el comportamiento común de promoción y conexiones.

Al igual que la [ruta predeterminada de fabric-cicd sin publicación masiva](fabric-hybrid-cicd-guide.md#visión-general-de-la-arquitectura), REST directo crea primero los elementos cuyos IDs necesitan los dependientes. Ahora incluye un tercer lote de Data Pipeline porque la actualización nativa necesita el ID del Semantic Model que devuelve la fase 2. La ruta predeterminada con el SDK también utiliza una tercera llamada de publicación para este ejemplo: descubre los IDs de Notebook y modelo a partir de un estado actualizado del workspace después de publicar las definiciones dependientes. REST directo, en cambio, captura los IDs de los cuerpos de respuestas anteriores. Las rutas basadas en planes derivan sus selecciones del grafo definido en el plan. Las fases de publicación no ejecutan el ETL.

| Concepto | fabric-cicd sin publicación masiva (predeterminado) | REST masivo directo |
|---|---|---|
| Llamadas por fase | Una llamada a la biblioteca (`publish_all_items()`) por fase, que internamente hace muchas llamadas REST por elemento | Un POST masivo por fase que contiene el lote completo |
| Sustitución | La biblioteca fabric-cicd aplica las reglas de `parameter.yml` de forma transparente | `scripts/deploy_fabric_rest_bulk.py` lee `bulk-parameter.yml` y reescribe las cargas útiles entre fases |
| Activación del conjunto de valores | La biblioteca la gestiona automáticamente cuando se pasa `environment` | El cliente realiza una llamada independiente a `PATCH /variableLibraries/{id}` |
| Limpieza de huérfanos | `unpublish_all_orphan_items()` incorporado | No implementada |

> Las otras rutas usan fabric-cicd sin publicación masiva, fabric-cicd sin publicación masiva con un plan interpretado por el adaptador, o fabric-cicd masivo con un plan interpretado por el adaptador. `DEPLOY_METHOD` selecciona la ruta; el punto de partida recomendado en este repositorio es fabric-cicd sin publicación masiva. Véanse la [matriz de métodos](README.md#elegir-un-método-de-despliegue) y la [Guía de CI/CD con fabric-cicd sin publicación masiva](fabric-hybrid-cicd-guide.md).

**No debe confundirse REST masivo directo con la publicación masiva de fabric-cicd.** En la versión 1.4.0, la publicación masiva de fabric-cicd admite las sustituciones dinámicas filtradas de [parameter.yml](../../data/fabric/parameter.yml). El [adaptador masivo aislado de fabric-cicd](../../scripts/deploy_fabric_cicd_bulk.py) delega las sustituciones en fabric-cicd y lee un plan de ordenación; no utiliza [bulk-parameter.yml](../../data/fabric/bulk-parameter.yml) ni el motor propio de búsqueda y sustitución de esta guía. Ese motor se conserva aquí para comparar ambas implementaciones.

REST directo permite adjuntar un plan nativo. El adaptador actual de fabric-cicd no lo hace: realiza selecciones masivas ordenadas por el plan y rechaza tanto la vuelta a la publicación estándar como los resultados fallidos o parciales por elemento. La [guía de Deployment Plan](fabric-deployment-plan-guide.md#adaptador-masivo-independiente-14x) detalla su configuración y los límites de validación de las vinculaciones reales.

### Ramas y workspaces

| Rama | Workspace | Método de despliegue |
|---|---|---|
| `dev` | Dev (microsoft-fabric-sdlc-patterns-dev) | Conectado a Git mediante la integración de Git de Fabric |
| `test` | Test (microsoft-fabric-sdlc-patterns-test) | API Bulk Import mediante GitHub Actions |
| `main` | Prod (microsoft-fabric-sdlc-patterns-prod) | API Bulk Import mediante GitHub Actions |

- **Dev** es el único workspace conectado a Git. Se hace Branch Out desde Dev para trabajar en *features* de forma aislada.
- **Test** y **Prod** no están conectados a Git. Con la ruta masiva activa, reciben los despliegues mediante `scripts/deploy_fabric_rest_bulk.py`.

---

## Estructura del repositorio

```
microsoft-fabric-sdlc-patterns/
├── .github/
│   └── workflows/
│       ├── deploy-test-bulk.yml             # Orquestador: push a test → despliegue masivo
│       ├── deploy-prod-bulk.yml             # Orquestador: push a main → despliegue masivo
│       ├── etl-test.yml                     # Recuperación manual del pipeline de Test
│       ├── etl-prod.yml                     # Recuperación manual del pipeline de Prod
│       ├── reusable-deploy-bulk.yml         # Plantilla: despliegue con la API Bulk Import
│       ├── reusable-fabric-etl.yml          # Plantilla: iniciar un trabajo de Fabric y consultar su estado
│       ├── check-pr-ready.yml               # Comprobación de PR: impide que los IDs de feature lleguen a dev
│       ├── run-tests.yml                    # Comprobación de PR: ejecuta pytest en todos los PR
│       └── enforce-promotion-path.yml       # Comprobación de PR: impone la promoción dev→test→main por rama de origen
├── data/
│   └── fabric/                              # Definiciones de elementos de Fabric (repository_directory)
│       ├── bulk-parameter.yml               # Parametrización de la ruta masiva (formato independiente)
│       ├── parameter.yml                    # Parametrización de fabric-cicd (la ruta masiva la ignora)
│       ├── PatternsLakehouse.Lakehouse/
│       ├── Patterns_Ontology.Ontology/
│       ├── Patterns_Variables.VariableLibrary/
│       ├── Import_Patterns_Data.Notebook/
│       ├── Validate_Patterns_Data.Notebook/
│       ├── Patterns_Load_Validate_And_Refresh.DataPipeline/
│       ├── Patterns_Patients_Data.Notebook/
│       ├── Patterns_Demo.Notebook/
│       ├── Patterns_Semantic_Model.SemanticModel/
│       ├── Patterns_Report.Report/
│       └── Patterns_Data_Agent.DataAgent/
├── scripts/
│   ├── deploy_fabric_rest_bulk.py           # Despliegue con Bulk Import (lo invoca reusable-deploy-bulk.yml)
│   ├── deploy_fabric_cicd_non_bulk.py       # Despliegue con fabric-cicd (ruta alternativa)
│   ├── run_fabric_etl.py                    # Inicia trabajos de Notebook o DataPipeline y consulta su estado
│   └── workspace_swap.py                    # Inicializa y restablece las vinculaciones del workspace de feature
├── tests/
│   └── test_deploy_fabric_rest_bulk.py      # Pruebas unitarias del script masivo
└── ... (otros documentos, véase README)
```

Las cuatro familias de métodos se encuentran en [.github/workflows/](../../.github/workflows/). `DEPLOY_METHOD` selecciona sus trabajos de despliegue; la [referencia común de flujos de trabajo](fabric-release-process.md#flujos-de-trabajo-de-github-actions) relaciona todos los flujos invocadores y las plantillas.

---

## Flujo de despliegue

### Qué desencadena qué

Véase el [Proceso de lanzamiento: qué activa cada ejecución](fabric-release-process.md#qué-activa-cada-ejecución). Para esta ruta, `DEPLOY_METHOD=bulk` selecciona `deploy-test-bulk.yml` o `deploy-prod-bulk.yml`.

### El trabajo de despliegue masivo

Después de los pasos comunes de preparación de conexiones, cada flujo de despliegue llama a `reusable-deploy-bulk.yml`, que invoca `scripts/deploy_fabric_rest_bulk.py`. El script:

1. Obtiene un token de portador de Entra ID con las credenciales de cliente del *Service principal*.
2. Recorre `data/fabric/` y construye un array `definitionParts[]`: una entrada por archivo con la ruta y el contenido codificado en base64.
3. Carga `bulk-parameter.yml` para obtener las reglas de sustitución y la configuración de activación del conjunto de valores.
4. Valida los GUID de las conexiones de destino antes de publicar y organiza por fases las dependencias de IDs dinámicos; pospone los Data Pipelines hasta que se conocen los IDs de sus modelos.
5. Envía tres lotes mediante POST a la URL masiva versionada. El script actual todavía añade el parámetro antiguo `?beta=true`; debe ajustarse al extremo v1 documentado actualmente antes de usarlo.
6. Realiza un PATCH sobre la VariableLibrary desplegada para establecer el conjunto de valores activo.

La API Bulk Import puede devolver `200 OK` con el cuerpo del resultado en la propia respuesta, o `202 Accepted` con una operación de larga duración (LRO). El script gestiona ambos casos de forma transparente; véanse los [problemas habituales](#sondeo-de-operaciones-de-larga-duración-lro).

El trabajo dependiente de ETL inicia el pipeline únicamente cuando el despliegue termina correctamente. A partir de ahí, Fabric controla la carga → validación → actualización nativa. Si falla una actividad, no se ejecutan las que dependen de su éxito; GitHub no realiza una actualización externa.

---

## Flujos de trabajo de GitHub Actions

La [referencia común](fabric-release-process.md#flujos-de-trabajo-de-github-actions) describe los eventos, selectores, plantillas reutilizables y el traspaso al ETL. Los títulos siguientes mantienen los enlaces anteriores sin duplicar el contrato común.

### Plantillas reutilizables (invocadas con `workflow_call`)

Véase el [Proceso de lanzamiento: plantillas reutilizables](fabric-release-process.md#plantillas-reutilizables-invocadas-mediante-workflow_call).

### Por qué flujos de trabajo reutilizables y no acciones compuestas

Véase el [Proceso de lanzamiento: por qué se usan flujos de trabajo reutilizables](fabric-release-process.md#por-qué-se-usan-flujos-de-trabajo-reutilizables-y-no-acciones-compuestas).

### Reejecuciones manuales con `workflow_dispatch`

Véase el [Proceso de lanzamiento: flujos invocadores de ETL y traspaso](fabric-release-process.md#flujos-de-trabajo-que-invocan-el-etl-y-traspaso-de-control).

---

## Estrategia de configuración

Tres mecanismos complementarios gestionan la configuración específica de cada entorno en la ruta masiva. Los dos primeros reflejan la [estrategia de la ruta de fabric-cicd](fabric-hybrid-cicd-guide.md#estrategia-de-configuración); el tercero es específico de la ruta masiva porque la API no activa por sí sola los conjuntos de valores.

### 1. Variable Libraries (en tiempo de ejecución)

Los Notebooks llaman a `notebookutils.variableLibrary.getLibrary("Patterns_Variables")` durante su ejecución para resolver IDs de workspace, nombres de Lakehouse y otros valores. La Variable Library tiene **conjuntos de valores** por entorno:

| Variable | Predeterminado (Dev) | Test | Prod |
|---|---|---|---|
| `target_workspace_id` | ID del workspace de Dev | ID del workspace de Test | ID del workspace de Prod |
| `target_workspace_name` | `microsoft-fabric-sdlc-patterns-dev` | `microsoft-fabric-sdlc-patterns-test` | `microsoft-fabric-sdlc-patterns-prod` |
| `target_lakehouse_name` | `PatternsLakehouse` | *(predeterminado)* | *(predeterminado)* |
| `target_lakehouse_id` | ID del Lakehouse de Dev | ID del Lakehouse de Dev* | ID del Lakehouse de Dev* |
| `minimum_patient_count` (Integer) | `5` | `5` | `5` |

\* Test y Prod heredan `target_lakehouse_id` del archivo base [variables.json](../../data/fabric/Patterns_Variables.VariableLibrary/variables.json); no lo sobrescriben en sus archivos de conjuntos de valores. El cliente REST directo aplica [bulk-parameter.yml](../../data/fabric/bulk-parameter.yml) para sustituir ese marcador base por el ID del Lakehouse desplegado.

El pipeline vincula el mínimo positivo de pacientes de la Variable Library activa al parámetro base del Notebook de validación. La validación utiliza ese valor recibido; `run_label` es un parámetro String independiente del pipeline, no otra política de la Variable Library ni un recuento fijo de datos de prueba definido directamente.

### 2. `bulk-parameter.yml` (en el despliegue)

Es el equivalente de la ruta masiva al `parameter.yml` de fabric-cicd. El formato es deliberadamente distinto: la ruta masiva implementa un subconjunto reducido del DSL de fabric-cicd, solo lo que necesitan los despliegues de este repositorio.

Este ejemplo muestra las reglas de Lakehouse y workspace de [bulk-parameter.yml](../../data/fabric/bulk-parameter.yml); el archivo completo también contiene las sustituciones del modelo y de las conexiones de ejecución del Data Pipeline:

```yaml
substitutions:
  - find: "c185283c-9dd9-4e40-a17c-aa6303e3a2e9"            # ID del Lakehouse de dev
    replace_with: "$items.Lakehouse.PatternsLakehouse.$id"
    item_types: [VariableLibrary, SemanticModel, Notebook]

  - find: "d7270f11-feba-4990-baa6-d45e47f23737"            # ID del workspace de dev
    replace_with: "$workspace.$id"
    item_types: [SemanticModel, Notebook, DataPipeline]

variable_library:
  active_value_set: "$environment"
```

**Esquema:**

| Clave de primer nivel | Propósito |
|---|---|
| `substitutions` | Lista de reglas de búsqueda y sustitución. Cada regla tiene `find` —la cadena literal—, `replace_with` —el reemplazo, con marcadores opcionales— e `item_types` —la lista de tipos de elemento a los que se aplica—. |
| `variable_library` | Configuración por VariableLibrary. Actualmente solo contiene `active_value_set`. |

**Referencia de marcadores de posición:**

| Marcador | Se resuelve a |
|---|---|
| `$workspace.$id` | ID del workspace de destino, obtenido de la variable de entorno `FABRIC_WORKSPACE_ID` |
| `$items.<Type>.<Name>.$id` | ID del elemento de destino capturado en una respuesta masiva anterior: Lakehouse y Ontology en la fase 1; Semantic Model en la fase 2 |
| `$environment` | Valor de la variable de entorno `ENVIRONMENT` que se pasa al paso de despliegue: `Test` o `Prod` |

**Filtro `item_types`:** una regla solo se aplica a los archivos cuyo tipo de elemento figure en su lista `item_types`. El script extrae el tipo de elemento de la convención de ruta `<DisplayName>.<Type>/<file>`. Los archivos de tipos no incluidos pasan sin cambios.

La referencia del modelo para la actualización nativa usa `$items.SemanticModel.Patterns_Semantic_Model.$id`, no el ID físico de Dev. El cliente también sustituye los GUID de las conexiones canónicas de Dev por las [variables del entorno](SETUP.md#variables-de-entorno-y-del-repositorio) de destino `NOTEBOOK_CONNECTION_ID` y `SEMANTIC_MODEL_REFRESH_CONNECTION_ID`. Las comprobaciones previas de GUID y las sustituciones no crean conexiones ni demuestran que su Workspace Identity tenga acceso.

**Por qué un archivo separado de `parameter.yml`:** los dos formatos coexisten deliberadamente. fabric-cicd usa `parameter.yml` y la ruta masiva utiliza `bulk-parameter.yml`. Mantenerlos separados evita que la ruta masiva tenga que ignorar en silencio —o fallar ante— funciones exclusivas de fabric-cicd: `key_value_replace`, `spark_pool` y `semantic_model_binding`. Los dos archivos residen en la raíz de `data/fabric/` y `scripts/deploy_fabric_rest_bulk.py` los excluye de la carga útil de las solicitudes masivas.

### 3. Activación del conjunto de valores de VariableLibrary (tras el despliegue)

La API Bulk Import sube los archivos de conjuntos de valores de la VariableLibrary, pero no establece cuál queda activo en el workspace desplegado. fabric-cicd lo selecciona automáticamente con su parámetro `environment`; con la API masiva, debe hacerlo el cliente.

`scripts/deploy_fabric_rest_bulk.py` realiza la llamada cuando terminan los POST masivos:

```
PATCH /v1/workspaces/{workspace_id}/variableLibraries/{library_id}
Content-Type: application/json

{
  "properties": {
    "activeValueSetName": "Test"
  }
}
```

La activación está condicionada a que `variable_library.active_value_set` de `bulk-parameter.yml` no sea nulo. El marcador `$environment` se resuelve al nombre del entorno de destino, `Test` o `Prod`. Si se indica una cadena literal, se utiliza ese valor exacto.

Referencia: [Update Variable Library](https://learn.microsoft.com/en-us/rest/api/fabric/variablelibrary/items/update-variable-library).

---

<a id="the-two-deploy-decision"></a>

## La decisión de desplegar por fases

Las reglas dinámicas `$items.<Type>.<Name>.$id` necesitan IDs de destino obtenidos previamente para poder sustituir las referencias en las cargas útiles dependientes. Este ejemplo usa **tres lotes de publicación**: Lakehouse y Ontology; sus dependientes distintos de Data Pipeline; y, por último, el Data Pipeline con el ID del modelo creado en la fase 2. Otros inventarios pueden necesitar menos lotes.

### Flujo de un solo despliegue (sin referencias a `$items.*` o sin configuración)

1. Ejecutar `apply_substitutions(parts, rules, workspace_id, item_id_map={})`.
2. Enviar todos los elementos a la vez mediante `POST`.
3. Aplicar `PATCH` a `VariableLibrary` si está configurada la activación del conjunto de valores.

Las reglas que solo usan `$workspace.$id` se aplican en este flujo porque el ID del workspace se conoce de antemano a través de la variable de entorno. Es el caso sin dependencias dinámicas, no el despliegue del pipeline de este ejemplo.

<a id="two-deploy-flow-rules-reference-items"></a>

### Flujo por fases (IDs dinámicos y tercer lote del pipeline)

1. Separar los elementos base, los dependientes distintos de `DataPipeline` y los elementos `DataPipeline`.
2. Enviar Lakehouse + Ontology mediante `POST` y capturar los IDs de destino: **fase 1**.
3. Sustituir los IDs de los elementos base en los elementos distintos de `DataPipeline`.
4. Enviar esos elementos mediante `POST` y capturar el ID del Semantic Model de destino: **fase 2**.
5. Sustituir los IDs de modelo, workspace y conexiones en `DataPipeline`.
6. Enviar la definición pospuesta de `DataPipeline` mediante `POST`: **fase 3**.
7. Aplicar `PATCH` a `VariableLibrary` únicamente si todas las importaciones tienen éxito.

`DEPENDENCY_TYPES` identifica los elementos base de la fase 1, actualmente Lakehouse y Ontology. El Semantic Model depende del Lakehouse y, por tanto, permanece en la fase 2; el Data Pipeline se pospone hasta que esté disponible el ID físico de su modelo. Mover todos los destinos de `$items` a la fase 1 rompería esta cadena de dependencias.

La fase 2 excluye las definiciones de Data Pipeline pospuestas y captura el ID del modelo de su respuesta. La fase 3 resuelve la referencia real del modelo del pipeline solo después de que esa importación tenga éxito. La ruta predeterminada con el SDK también aísla la publicación del pipeline en una tercera llamada, pero resuelve las referencias mediante un nuevo descubrimiento del workspace de fabric-cicd, no a partir de este mapa de IDs de respuestas REST.

### Cuándo falla el script de inmediato

El script devuelve un error claro en dos situaciones:

- **Las reglas de sustitución referencian `$items.<Type>.<Name>.$id`, pero no se encuentra en el repositorio ningún elemento de los tipos de dependencia.** El despliegue no puede resolver el marcador.
- **Una regla referencia un elemento que el script no encuentra por `(Type, Name)`.** El marcador no se resolverá. Una causa habitual es una errata en `bulk-parameter.yml`.

Los GUID de conexión no válidos hacen fallar el proceso antes del primer POST de definiciones. Las referencias dinámicas ausentes provocan el fallo antes de su solicitud dependiente; un fallo posterior no deshace los elementos que ya se hayan importado. Una publicación parcial nunca debe considerarse correcta.

---

## Requisitos previos y configuración

Primero debe completarse la [Configuración](SETUP.md). La ruta masiva directa añade estos requisitos específicos:

1. Todo workspace que reciba tipos de elemento de Fabric debe usar una SKU F o Fabric Trial. Power BI Premium solo es suficiente si todas las definiciones importadas son elementos de Power BI.
2. Todos los tipos de elemento de una solicitud deben admitir el Service principal de despliegue. Un único tipo no compatible puede hacer fallar toda la solicitud masiva.
3. Se debe establecer la variable de repositorio `DEPLOY_METHOD=bulk`.
4. Hay que ajustar la solicitud versionada con el parámetro antiguo `?beta=true` al extremo v1 documentado actualmente y, después, verificar la ruta en un entorno real de Test.

El lanzamiento seleccionado de Test o Prod sigue necesitando los cinco secretos del entorno, incluido `GH_ENV_VARIABLES_TOKEN`, y ejecuta la preparación y verificación automáticas de conexiones antes del publicador REST directo. Véase el [Proceso de lanzamiento](fabric-release-process.md#ciclo-de-vida-de-las-conexiones-por-etapa).

---

## Primer despliegue en un workspace vacío

Este recorrido utiliza la ruta REST directa. Los pasos siguientes corresponden a un destino vacío. La publicación, el ETL y la actualización del modelo posteriores están automatizados, sujetos a las aprobaciones configuradas; la validación obligatoria del lanzamiento y los cambios en los requisitos de configuración siguen siendo tareas independientes.

### Paso 1: desencadenar el despliegue

Con `DEPLOY_METHOD=bulk`, fusione un PR válido de `dev -> test` o `test -> main` que incluya cambios en las definiciones de Fabric o en los flujos de trabajo. Se aplican las aprobaciones de despliegue configuradas. El trabajo REST directo ejecuta:

- **Fase 1, si hace falta:** POST de Lakehouse + Ontology.
- **Fase 2:** sustituye los IDs de la fase 1 y envía mediante POST los elementos dependientes distintos de Data Pipeline; captura el ID del Semantic Model de destino.
- **Fase 3:** sustituye ese ID de modelo y los GUID de las conexiones de destino; después envía `Patterns_Load_Validate_And_Refresh` mediante POST.
- **Tras el despliegue:** PATCH de la VariableLibrary para establecer el conjunto de valores activo del entorno.

### Paso 2: el ETL carga el Lakehouse y después actualiza el modelo

Cuando el despliegue termina correctamente, el flujo de ETL inicia un único Data Pipeline y consulta su estado. El Notebook de carga no cambia: carga `doctors`, `patients` y `appointments`. El Notebook de validación de solo lectura comprueba esquemas, claves, referencias, tipos de fecha del origen y el mínimo de la Variable Library activa. Solo después se realiza el *framing* de `Patterns_Semantic_Model` mediante la actualización nativa y se espera a su finalización. GitHub no realiza una segunda actualización y las fases de publicación no ejecutan estas actividades.

### Paso 3: configurar el origen de datos del Graph Model (manual)

La Ontology se despliega solo como definición: su Graph Model no tiene una vinculación con un origen de datos hasta que se configura manualmente.

1. Abra el elemento **Ontology** en la interfaz de Fabric y vaya al **Graph Model**.
2. Seleccione **Get data** para vincular el Graph Model a las tablas del Lakehouse.

### Paso 4: activar la Ontology (solución manual)

Tras configurar el origen de datos, la Ontology puede quedarse en *"Setting up your ontology — We are preparing the ontology overview for the first time."* Es un comportamiento conocido de la plataforma Fabric en el primer despliegue.

**Solución alternativa:** seleccione cualquier Entity Type de la Ontology, cámbiele el nombre por uno temporal y después restablezca el original. Esto hace que Fabric termine de inicializar la vista general de la Ontology.

### Paso 5: verificar de principio a fin

Confirme que todos los elementos funcionan en el workspace de destino:

- **Lakehouse:** tablas cargadas con datos.
- **Ontology:** la vista general carga y se ven los tipos de entidad y las relaciones.
- **Variable Library:** el conjunto de valores activo coincide con el entorno de destino, `Test` o `Prod`.
- **Data Pipeline:** referencias físicas correctas al modelo y las conexiones, credenciales de Workspace Identity previstas, reenvío de parámetros y estado final correcto.
- **Semantic Model:** actualización posterior al ETL completada; verificar la conexión al Lakehouse local, los permisos del propietario y sobre el origen, y los campos y cálculos necesarios. Si el primer despliegue lo requiere, configurar una conexión compatible.
- **Report:** se visualiza con datos del Semantic Model.
- **Data Agent:** referencia la Ontology y responde a las consultas.

> **Nota:** los pasos 3 y 4, de activación de Ontology, son comportamientos de la plataforma, no específicos de la ruta masiva. La ruta de fabric-cicd requiere los mismos pasos manuales en el primer despliegue.

La validación del pipeline y la finalización de la actualización no sustituyen estas comprobaciones de consumo ni las [evidencias obligatorias del lanzamiento](fabric-cicd-quality-gates-and-release-controls.md).

---

## Problemas habituales y decisiones clave

<a id="two-deploy-chicken-and-egg"></a>

### El problema del huevo y la gallina del despliegue por fases

La Variable Library, el Semantic Model y los Notebooks referencian el ID del Lakehouse de cada entorno, pero el Lakehouse no existe en Test ni en Prod hasta que lo crea el primer despliegue. Con la API masiva, ninguna biblioteca resuelve esas referencias: el script debe enviar primero las dependencias mediante POST, leer sus IDs de la respuesta y sustituirlos en los elementos restantes antes del segundo POST.

**Solución:** [desplegar por fases](#la-decisión-de-desplegar-por-fases). La fase 1 crea Lakehouse y Ontology; la fase 2 importa los dependientes distintos de Data Pipeline; la fase 3 utiliza el ID capturado del modelo para resolver la referencia del Data Pipeline. Estos POST directos de definiciones son distintos tanto de las tres llamadas a la biblioteca del ejecutor predeterminado con el SDK como de la ejecución única de la carga de trabajo.

### Compatibilidad con Service principals por solicitud

La API Bulk Import exige que **todos** los tipos de elemento de la carga útil admitan Service principals. Si uno solo no los admite, la solicitud entera falla con un error de autorización; no continúa únicamente con los elementos compatibles.

La publicación estándar de fabric-cicd hace solicitudes por elemento; la publicación masiva de fabric-cicd también exige compatibilidad para todos los tipos de elemento y operaciones enviados. Seleccionar fabric-cicd no concede permisos ni hace que se utilice una identidad de usuario como alternativa.

**Solución:** verificar la compatibilidad con Service principals para cada tipo de elemento y operación enviados. El ámbito ahora incluye `DataPipeline` como octavo tipo de la carga de trabajo. Crear o exportar mediante una API con identidad de usuario y ejecutar correctamente actividades de feature no demuestra que el Service principal de CI pueda publicar mediante REST masivo directo e iniciar el trabajo. Debe validarse la ruta seleccionada en un destino aprobado que no sea de producción antes de promoverla; no debe deducirse la compatibilidad de principio a fin a partir de la interfaz ni de los contratos comprobados sin conexión.

### Sondeo de operaciones de larga duración (LRO)

La API Bulk Import puede devolver:

- **`200 OK`** con el cuerpo completo del resultado, `importItemDefinitionsDetails[]`, en la propia respuesta: caso síncrono.
- **`202 Accepted`** con las cabeceras `x-ms-operation-id` y `Retry-After`: caso asíncrono, en el que el cliente consulta una operación de larga duración.

`scripts/deploy_fabric_rest_bulk.py` gestiona ambos casos de forma transparente. En el caso asíncrono, consulta `GET /v1/operations/{id}` hasta que la operación llega a `Succeeded`, `Failed` o `Undefined`; después obtiene `GET /v1/operations/{id}/result` con la misma estructura `importItemDefinitionsDetails[]` que el caso síncrono devuelve directamente.

### Acotación de Retry-After

El script acota la cabecera `Retry-After` al intervalo de 5 a 600 segundos y usa 30 segundos si falta o no puede interpretarse. Sin el límite superior, un valor anómalo podría causar una única espera más larga que el tiempo de espera global del sondeo, de 20 minutos, y dejarlo sin efecto. Sin la validación de entrada, un valor no entero haría fallar el script con un `ValueError` no controlado.

### El token de portador no se escribe en los registros

Una versión anterior del script emitía `::add-mask::<token>` para registrar una máscara de los registros del flujo de trabajo. Esa misma línea escribía el token en texto claro en la salida estándar, anulando el propósito de la máscara: el ejecutor solo oculta la salida posterior. El script actual nunca imprime el token. GitHub enmascara automáticamente el secreto del Service principal porque procede de `secrets.AZURE_CLIENT_SECRET`.

### `bulk-parameter.yml` se excluye de la carga útil

El script incluye `bulk-parameter.yml`, `parameter.yml` y `.gitkeep` en `EXCLUDED_FILES` para que nunca se envíen a Fabric como parte de la solicitud masiva. La regla estructural «los archivos de la raíz de `repository_directory` no son definiciones de elementos» ya los excluye, pero la lista explícita documenta la intención.

También se excluyen las carpetas de elementos `*.DeploymentPlan` sincronizadas con Git. Este ejemplo de Bulk Import directo no adjunta un plan nativo a su solicitud; el [adaptador basado en planes](fabric-deployment-plan-guide.md) es un método distinto.

### Peculiaridad de `workflow_run`: las reejecuciones usan el archivo congelado

Se conserva este título para mantener los enlaces anteriores. El antiguo diseño de receptor automático se ha sustituido por una cadena `needs` dentro del mismo flujo de trabajo. Una ejecución antigua sigue utilizando su revisión original; reejecutarla no sirve para probar código nuevo. Debe lanzarse un despliegue nuevo o utilizar el flujo de recuperación manual en la rama prevista. Los flujos invocadores renombrados como `Deploy and Run Pipeline` tampoco coinciden con los receptores antiguos de la rama predeterminada durante la transición, lo que evita ETL automáticos duplicados.

### Ajustar el parámetro antiguo `?beta=true`

El script versionado envía:

```text
POST /v1/workspaces/{workspaceId}/items/bulkImportDefinitions?beta=true
```

La [referencia actual de la API](https://learn.microsoft.com/en-us/rest/api/fabric/core/items/bulk-import-item-definitions) y el [tutorial de Bulk Import](https://learn.microsoft.com/en-us/fabric/cicd/tutorial-bulkapi-cicd) muestran `/items/bulkImportDefinitions` sin ese parámetro y ya no identifican la operación como Preview. La antigua discrepancia de la ruta del tutorial está resuelta.

Esta corrección documental no demuestra que el cliente versionado sea compatible con el servicio actual. Antes de usar `DEPLOY_METHOD=bulk`, hay que actualizar el cliente y verificarlo en un entorno real.

### Extremo del tutorial de Microsoft

El tutorial actual y la referencia de la API coinciden en `/items/bulkImportDefinitions`. Las implementaciones nuevas no deben conservar la antigua solución alternativa con el singular `/importItemDefinitions`.

---

## Ampliar la implementación masiva

El script está organizado para que las ampliaciones habituales queden localizadas. Los apartados siguientes describen el patrón de cada una.

### Añadir una regla de sustitución

Edite `data/fabric/bulk-parameter.yml`:

```yaml
substitutions:
  # ... reglas existentes ...
  - find: "<old-string>"
    replace_with: "<new-string-or-placeholder>"
    item_types: [Notebook, SemanticModel]
```

No hace falta cambiar el código. La regla nueva se recoge automáticamente en el siguiente despliegue.

Si la regla referencia `$items.<Type>.<Name>.$id` para un tipo de elemento nuevo, amplíe también `DEPENDENCY_TYPES` en `scripts/deploy_fabric_rest_bulk.py` para que ese tipo se despliegue en la fase 1.

### Añadir un tipo de marcador de posición

Para añadir, por ejemplo, `$secrets.<name>` que se resuelva a un secreto de CI, modifique `scripts/deploy_fabric_rest_bulk.py`:

1. Añada la constante `_SECRETS_PLACEHOLDER = re.compile(r"\$secrets\.([^.\s]+)")`.
2. En `resolve_dynamic_value()`, añada una llamada a `_SECRETS_PLACEHOLDER.sub(...)`.
3. Añada la variable de entorno correspondiente, por ejemplo `BULK_SECRETS_JSON`, y léala en `main()`.
4. Añada pruebas del nuevo resolutor.

El patrón sigue lo que ya hacen `$workspace.$id` y `$items.<Type>.<Name>.$id`.

### Añadir un tipo de dependencia

Si un tipo de elemento nuevo pasa a ser destino de sustituciones `$items.<Type>.*` —por ejemplo, un Warehouse nuevo del que dependan otros elementos—:

```python
DEPENDENCY_TYPES = ("Lakehouse", "Ontology", "Warehouse")
```

Si se trata de un tipo base, esto amplía la fase 1. Si tiene requisitos previos propios, hay que definir un lote posterior y pruebas de regresión, en lugar de colocarlo antes que sus requisitos. La cadena del pipeline y el modelo es el ejemplo existente.

### Añadir una operación posterior al despliegue

La activación del conjunto de valores de VariableLibrary es el ejemplo existente. Para añadir otra operación —por ejemplo, crear un Shortcut de Lakehouse después del despliegue—:

1. Añada una función auxiliar, como `create_shortcut(workspace_id, lakehouse_id, shortcut_config, headers)`, que encapsule la llamada correspondiente a la API REST de Fabric.
2. Añada el bloque de configuración correspondiente a `BulkConfig`, por ejemplo `shortcuts: tuple[ShortcutConfig, ...]`.
3. Amplíe `load_bulk_config()` para interpretar el bloque nuevo de `bulk-parameter.yml`.
4. Conecte la operación en `main()` después del despliegue, junto a la activación del conjunto de valores existente.
5. Añada pruebas unitarias de la función auxiliar y de la interpretación de la configuración.

El patrón es deliberadamente repetible: cada paso posterior al despliegue es «bloque de configuración en YAML → campo de dataclass → función auxiliar → punto de llamada en `main()`».

### Añadir un bloque de configuración masiva

La configuración incluida tiene `substitutions` y `variable_library`. Para añadir un tercer bloque —por ejemplo, `shortcuts`, como en el apartado anterior—:

1. Añada una `@dataclass(frozen=True)` para el contenido del bloque, por ejemplo `ShortcutConfig`.
2. Añádala como campo de `BulkConfig` con un valor predeterminado razonable.
3. Amplíe `load_bulk_config()` para interpretar el bloque nuevo y emitir mensajes de error explícitos ante entradas mal formadas.
4. Añada pruebas que cubran el caso correcto, el comportamiento predeterminado cuando falta el bloque y todos los errores documentados.

La `VariableLibraryConfig` existente es un ejemplo funcional.

---

## Limitaciones no resueltas

La ruta masiva de este repositorio implementa las sustituciones y la activación del conjunto de valores, pero no resuelve lo siguiente. Quien adopte esta ruta en su proyecto tendrá que implementarlo o aceptar su ausencia.

| Limitación | Qué falta | Solución alternativa, si se necesita |
|---|---|---|
| **Limpieza de huérfanos** | La API Bulk Import solo admite crear y actualizar, no eliminar. Los elementos retirados del repositorio permanecen en el workspace. | Mantener un bucle independiente de `DELETE` por elemento después del POST masivo. |
| **`key_value_replace`** | Sustitución por clave basada en JSONPath de fabric-cicd, como los IDs de conexión del JSON de un pipeline. | Ampliar `apply_substitutions()` para admitir un paso de sustitución de tipo JSONPath además de la búsqueda literal. |
| **Sustitución de `spark_pool`** | Cambio de grupos de Spark por entorno de fabric-cicd. | Añadir un bloque de configuración y una llamada a la API posterior al despliegue, similar a la activación del conjunto de valores. |
| **`semantic_model_binding`** | Vinculación automática de Semantic Models a conexiones de origen de datos de fabric-cicd. | Añadir una llamada a la API posterior al despliegue sobre el Semantic Model. |
| **Tratamiento independiente de fallos por elemento con Service principals** | La ruta masiva hace fallar toda la solicitud si algún tipo de elemento no admite Service principals. | Comprobación previa: enumerar los tipos de elemento de la solicitud y validarlos frente a un conjunto conocido de tipos compatibles. |
| **Gestión de varias Variable Libraries** | `find_variable_library_id()` devuelve un error si hay varias Variable Libraries, porque la activación apunta a una sola. | Rediseñar la activación para que reciba una configuración por Library y recorra todas. |
| **Filtro `item_type_in_scope`** | El script despliega todo lo que contiene `repository_directory`. No hay forma de acotarlo a un subconjunto. | Añadir una variable de entorno que se lea en `main()` y filtrar las partes antes del POST. |

Estas funciones quedan deliberadamente fuera del alcance de este repositorio de demostración. Pueden añadirse de forma incremental con los [patrones de ampliación](#ampliar-la-implementación-masiva) anteriores.

---

## Referencias

- [Opciones de lanzamiento de CI/CD](fabric-cicd-release-options.md): estrategia y comparación entre fabric-cicd y las API masivas.
- [Proceso de lanzamiento](fabric-release-process.md): contrato común de promoción, conexiones y Data Pipeline.
- [Guía de CI/CD con fabric-cicd sin publicación masiva](fabric-hybrid-cicd-guide.md): mecánica del publicador predeterminado.
- [Consideraciones de gobernanza para CI/CD](fabric-cicd-governance-considerations.md): identidad, RBAC, protección de ramas y controles de aprobación.
- [API Bulk Import Item Definitions de Fabric](https://learn.microsoft.com/en-us/rest/api/fabric/core/items/bulk-import-item-definitions): referencia actual del extremo.
- [Operaciones de larga duración de Fabric](https://learn.microsoft.com/en-us/rest/api/fabric/articles/long-running-operation): semántica de `?async=true` y patrón de sondeo.
- [Update Variable Library de Fabric](https://learn.microsoft.com/en-us/rest/api/fabric/variablelibrary/items/update-variable-library): extremo PATCH usado para activar el conjunto de valores.
- [Tutorial de Bulk Import de Microsoft](https://learn.microsoft.com/en-us/fabric/cicd/tutorial-bulkapi-cicd): recorrido actual de Microsoft.
- [API Create Item de Fabric: permisos](https://learn.microsoft.com/en-us/rest/api/fabric/core/items/create-item): requisito del rol Contributor.
- [Flujos de trabajo reutilizables de GitHub](https://docs.github.com/en/actions/sharing-automations/reusing-workflows): `workflow_call`, entradas y secretos.

---

## Sobre esta traducción

Este documento es una traducción de [fabric-bulk-cicd-guide.md](../../fabric-bulk-cicd-guide.md). La versión en inglés es la fuente de referencia y puede estar más actualizada.

La actualización del 15-10-2026 se ha revisado con asistencia de IA, sin nueva validación por hablantes nativos. Se conservan las decisiones anteriores de [`GLOSARIO.md`](GLOSARIO.md) y se aplica [`GUIA-DE-ESTILO.md`](GUIA-DE-ESTILO.md).

Los enlaces externos apuntan a la documentación en inglés. Los errores pueden comunicarse mediante una incidencia que indique el idioma. Si el error también existe en inglés, debe corregirse primero allí; véanse [`REVISION.md`](REVISION.md) y [`TRANSLATION.md`](../../TRANSLATION.md).
