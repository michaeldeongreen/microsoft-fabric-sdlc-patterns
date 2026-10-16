[English](../../fabric-hybrid-cicd-guide.md) | **Español**

<!-- source: fabric-hybrid-cicd-guide.md @ f7f949d | translated: 2026-10-15 -->

> 📄 **La versión en inglés de este documento es la de referencia.** En caso de discrepancia, [el original en inglés](../../fabric-hybrid-cicd-guide.md) tiene precedencia.

<a id="hybrid-cicd-implementation-guide"></a>

# Guía de CI/CD con fabric-cicd sin publicación masiva

Esta guía describe la ruta de fabric-cicd sin publicación masiva, el método de despliegue predeterminado de este repositorio y su punto de partida recomendado. Se centra en la mecánica propia del publicador: tres fases de publicación, `parameter.yml`, limpieza de elementos huérfanos que cumplan los criterios y comportamiento con destinos vacíos.

El [Proceso de lanzamiento](fabric-release-process.md) documenta el comportamiento común de los cuatro métodos: promoción, preparación y verificación de conexiones, selección de flujos de trabajo, traspaso al *Data Pipeline* de Fabric de la misma revisión, recuperación y estado de verificación.

Las [Opciones de lanzamiento de CI/CD](fabric-cicd-release-options.md) comparan las alternativas y describen las [extensiones opcionales para elementos no compatibles](fabric-cicd-release-options.md#extensiones-opcionales-para-elementos-no-compatibles).

Se conserva el nombre de archivo existente para no romper los enlaces a esta guía.

---

## Índice

- [Visión general de la arquitectura](#visión-general-de-la-arquitectura)
- [Estructura del repositorio](#estructura-del-repositorio)
- [Flujo de despliegue](#flujo-de-despliegue)
- [Flujos de trabajo de GitHub Actions](#flujos-de-trabajo-de-github-actions)
- [Estrategia de configuración](#estrategia-de-configuración)
- [Requisitos previos y configuración](#requisitos-previos-y-configuración)
- [Primer despliegue en un workspace vacío](#primer-despliegue-en-un-workspace-vacío)
- [Problemas habituales y decisiones clave](#problemas-habituales-y-decisiones-clave)
- [Referencias](#referencias)

---

## Visión general de la arquitectura

```
Repositorio Git (rama dev)
  │
  │  Merge del PR → rama test
  ▼
┌──────────────────────────────────────────────────────────────┐
│  deploy-test.yml (orquestador)                               │
│                                                              │
│  preparación del lanzamiento seleccionado                    │
│    └─ crear/reutilizar y verificar conexiones WI; guardar IDs│
│  deploy-fabric-cicd                                          │
│    └─ reusable-deploy-fabric-cicd.yml                        │
│       └─ fabric-cicd: publish_all_items()                    │
│          (Fase 1: Lakehouse + Ontology)                      │
│          (Fase 2: dependientes distintos de DataPipeline)    │
│          (Fase 3: DataPipeline; estado actualizado)          │
└──────────────────────────────────────────────────────────────┘
                     │ needs: deploy-fabric-cicd
                     ▼
┌──────────────────────────────────────────────────────────────┐
│  deploy-test.yml: run-etl (misma revisión)                   │
│    └─ reusable-fabric-etl.yml                                │
│       └─ API REST de Fabric: ejecutar DataPipeline y esperar │
└──────────────────────────────────────────────────────────────┘
                     │ dependencias de actividades de Fabric
                     ▼
    Import_Patterns_Data → Validate_Patterns_Data
       → actualización nativa de Patterns_Semantic_Model
```

La misma mecánica de publicación se aplica a Prod. El [contrato común de Test y Prod](fabric-release-process.md#de-dev-a-test) describe la secuencia completa de trabajos y la correspondencia entre ramas y entornos.

GitHub publica las definiciones, inicia un único trabajo de `Patterns_Load_Validate_And_Refresh` y consulta su estado. Fabric controla la validación y la única actualización del modelo; ya no hay un paso de actualización de Power BI en GitHub ni una ruta alternativa de actualización en tiempo de ejecución. Este Data Pipeline de Fabric orquesta trabajo; en cambio, los **Pipelines de despliegue de Fabric** nativos promueven contenido y DeploymentPlan ordena la publicación.

> Junto a esta ruta predeterminada de fabric-cicd sin publicación masiva existen rutas alternativas: REST masivo directo y dos rutas de fabric-cicd con planes interpretados por el adaptador. Todas se seleccionan mediante `DEPLOY_METHOD`. El punto de partida recomendado es la ruta predeterminada sin publicación masiva; véanse la [matriz de métodos](README.md#elegir-un-método-de-despliegue) y la [guía de REST directo](fabric-bulk-cicd-guide.md).

Para configurar la ordenación sin modificar esta ruta predeterminada, véase la [Guía de CI/CD con Deployment Plan](fabric-deployment-plan-guide.md). Los adaptadores independientes `fabric-cicd-plan` y `fabric-cicd-bulk` usan el plan versionado en lugar de fases fijas: llamadas estándar secuenciales o llamadas masivas estrictas agrupadas, respectivamente. Ninguno ejecuta un Deployment Plan nativo.

### Ramas y workspaces

| Rama | Workspace | Método de despliegue |
|---|---|---|
| `dev` | Dev (microsoft-fabric-sdlc-patterns-dev) | Conectado a Git mediante la integración de Git de Fabric |
| `test` | Test (microsoft-fabric-sdlc-patterns-test) | Publicador por API seleccionado; esta guía cubre fabric-cicd |
| `main` | Prod (microsoft-fabric-sdlc-patterns-prod) | Publicador por API seleccionado; esta guía cubre fabric-cicd |

- Dev es el único workspace compartido conectado a Git. Se hace Branch Out desde Dev para trabajar en *features* de forma aislada.
- Test y Prod no están conectados a Git. Reciben publicaciones por API.

---

## Estructura del repositorio

```
microsoft-fabric-sdlc-patterns/
├── .github/workflows/
│   ├── deploy-test.yml
│   ├── deploy-prod.yml
│   └── reusable-deploy-fabric-cicd.yml
├── data/fabric/
│   ├── parameter.yml
│   ├── PatternsLakehouse.Lakehouse/
│   ├── Patterns_Ontology.Ontology/
│   ├── Patterns_Variables.VariableLibrary/
│   ├── *.Notebook/
│   ├── *.SemanticModel/
│   ├── *.Report/
│   ├── *.DataAgent/
│   └── *.DataPipeline/
├── scripts/
│   └── deploy_fabric_cicd_non_bulk.py
├── fabric-release-process.md
└── fabric-hybrid-cicd-guide.md
```

El inventario completo de flujos de trabajo está en el [Proceso de lanzamiento](fabric-release-process.md#flujos-de-trabajo-de-github-actions).

---

## Flujo de despliegue

### Qué desencadena qué

Este contenido común se ha trasladado al [Proceso de lanzamiento: qué activa cada ejecución](fabric-release-process.md#qué-activa-cada-ejecución). Se conserva el título de este apartado para mantener los enlaces existentes.

### Trabajo de despliegue

Después de la [preparación común de conexiones](fabric-release-process.md#de-dev-a-test), el flujo seleccionado llama a `reusable-deploy-fabric-cicd.yml`. Cuando el ámbito incluye un Data Pipeline, el ejecutor estándar hace tres llamadas de publicación: Lakehouse + Ontology; elementos dependientes distintos de Data Pipeline —Variable Library, Notebooks, Semantic Model, Report y Data Agent—; por último, Data Pipeline.

fabric-cicd almacena en caché el estado del workspace durante una llamada, por lo que el orden de los elementos no basta para resolver las referencias del pipeline a los Notebooks y al modelo recién creados. La tercera llamada vuelve a consultar el inventario del workspace para resolver esas referencias con los nuevos IDs.

Si no hay ningún Data Pipeline, el ejecutor conserva su comportamiento de dos fases. Los tipos de elemento siguen acotándose explícitamente mediante `item_type_in_scope`.

El trabajo dependiente de ETL comienza cuando la publicación termina correctamente. El traspaso común se documenta en el [Proceso de lanzamiento](fabric-release-process.md#flujos-de-trabajo-que-invocan-el-etl-y-traspaso-de-control).

<a id="strict-plan-driven-sdk-bulk-14x"></a>
<a id="publicación-masiva-de-fabric-cicd-con-un-plan-leído-por-el-cliente-14x"></a>

### Publicación masiva de fabric-cicd con un plan interpretado por el adaptador (1.4.x)

Los adaptadores basados en planes ya no se documentan en esta guía. La [Guía de CI/CD con Deployment Plan](fabric-deployment-plan-guide.md#adaptador-masivo-independiente-14x) describe el comportamiento de la publicación masiva de fabric-cicd y sus límites de validación. Se conserva este anclaje para mantener la compatibilidad con los enlaces existentes.

---

## Flujos de trabajo de GitHub Actions

La referencia común de flujos de trabajo se ha trasladado al [Proceso de lanzamiento: flujos de trabajo de GitHub Actions](fabric-release-process.md#flujos-de-trabajo-de-github-actions). Los títulos siguientes mantienen los enlaces anteriores sin duplicar el contrato de lanzamiento.

### Comprobaciones de pull request

Véase el [Proceso de lanzamiento: comprobaciones de las pull requests](fabric-release-process.md#comprobaciones-de-las-pull-requests).

### Flujos invocadores de despliegue

Véase el [Proceso de lanzamiento: flujos de trabajo de despliegue](fabric-release-process.md#flujos-de-trabajo-de-despliegue).

### Plantillas reutilizables (invocadas con `workflow_call`)

Véase el [Proceso de lanzamiento: plantillas reutilizables](fabric-release-process.md#plantillas-reutilizables-invocadas-mediante-workflow_call).

### Flujos invocadores de ETL y traspaso

Véase el [Proceso de lanzamiento: flujos de trabajo que invocan el ETL y traspaso de control](fabric-release-process.md#flujos-de-trabajo-que-invocan-el-etl-y-traspaso-de-control).

#### Actualización del Semantic Model posterior al ETL

Véase el [Proceso de lanzamiento: actualización del Semantic Model posterior al ETL](fabric-release-process.md#actualización-del-semantic-model-posterior-al-etl).

### Por qué flujos de trabajo reutilizables y no acciones compuestas

Véase el [Proceso de lanzamiento: por qué se usan flujos de trabajo reutilizables](fabric-release-process.md#por-qué-se-usan-flujos-de-trabajo-reutilizables-y-no-acciones-compuestas).

---

## Estrategia de configuración

Dos mecanismos complementarios gestionan la configuración específica de cada entorno:

### 1. Variable Libraries (en tiempo de ejecución)

Los Notebooks de carga y validación llaman a `notebookutils.variableLibrary.getLibrary("Patterns_Variables")` durante su ejecución para obtener la configuración de workspace y Lakehouse. El pipeline también vincula el mínimo de pacientes de la Variable Library activa al parámetro base del Notebook de validación. La Variable Library tiene **conjuntos de valores** por entorno:

| Variable | Predeterminado (Dev) | Test | Prod |
|---|---|---|---|
| `target_workspace_id` | ID del workspace de Dev | ID del workspace de Test | ID del workspace de Prod |
| `target_workspace_name` | `microsoft-fabric-sdlc-patterns-dev` | `microsoft-fabric-sdlc-patterns-test` | `microsoft-fabric-sdlc-patterns-prod` |
| `target_lakehouse_name` | `PatternsLakehouse` | *(predeterminado)* | *(predeterminado)* |
| `target_lakehouse_id` | ID del Lakehouse de Dev | ID del Lakehouse de Dev* | ID del Lakehouse de Dev* |
| `minimum_patient_count` (Integer) | `5` | `5` | `5` |

\* Test y Prod heredan `target_lakehouse_id` del archivo base [variables.json](../../data/fabric/Patterns_Variables.VariableLibrary/variables.json); sus archivos de conjuntos de valores no lo sobrescriben. En el despliegue, [parameter.yml](../../data/fabric/parameter.yml) sustituye ese marcador base por el ID del Lakehouse de destino. La ruta masiva de fabric-cicd conserva literalmente, sin modificarlos, los archivos de control de configuración y conjuntos de valores; sus [límites de seguridad de las sustituciones](fabric-deployment-plan-guide.md#sustituciones-de-fabric-cicd-y-requisitos-de-éxito) se describen en la guía de planes.

**Vinculación del conjunto de valores activo:** fabric-cicd establece automáticamente el conjunto activo a partir del parámetro `environment` que se pasa a `FabricWorkspace`. Cuando `environment="Test"`, se activa el conjunto `Test`. Ocurre en cada despliegue, sin intervención manual.

> Cita: [fabric-cicd Item Types — Variable Library](https://microsoft.github.io/fabric-cicd/latest/reference/item_types/): *"The active value set of the variable library is defined by the `environment` field passed into the `FabricWorkspace` object."*
>
> Traducción: «El conjunto de valores activo de la Variable Library lo define el campo `environment` que se pasa al objeto `FabricWorkspace`».

### 2. parameter.yml (en el despliegue)

El archivo `parameter.yml` de `data/fabric/` usa `find_replace` de fabric-cicd con **sustitución dinámica** para resolver el ID del Lakehouse en el momento del despliegue:

```yaml
find_replace:
    - find_value: "<DEV_LAKEHOUSE_ID>"
      replace_value:
          _ALL_: "$items.Lakehouse.PatternsLakehouse.$id"  # Resuelto en el despliegue
      item_type: "VariableLibrary"
```

**Cómo funciona:** fabric-cicd despliega los elementos en orden de dependencia; el Lakehouse se crea antes que la Variable Library. Al procesar los archivos de la Variable Library, `$items.Lakehouse.PatternsLakehouse.$id` se resuelve al GUID real del Lakehouse de destino. La clave `_ALL_` indica que se aplica a todos los entornos.

Las reglas del Data Pipeline también sustituyen los IDs físicos de workspace y modelo y las conexiones canónicas de Dev del origen. La sustitución del modelo de destino usa `$items.SemanticModel.Patterns_Semantic_Model.$id`; la de conexiones utiliza los nombres exactos `$ENV:NOTEBOOK_CONNECTION_ID` y `$ENV:SEMANTIC_MODEL_REFRESH_CONNECTION_ID`.

Los ejecutores habilitan la sustitución de variables de entorno y validan los dos GUID de conexión antes de publicar las definiciones. Se requiere la biblioteca en el intervalo `>=1.4.0,<1.5.0`. La creación y el uso compartido de las conexiones de Test y Prod corresponden a los pasos previos de conexión del lanzamiento seleccionado, no al subproceso publicador ni a la sustitución de parámetros.

Las comprobaciones previas de las definiciones de origen examinan los campos reales y los valores de referencia de parametrización para evitar que los IDs obsoletos de feature queden sin sustituir de forma inadvertida.

---

## Requisitos previos y configuración

La [Guía de configuración](SETUP.md) describe cómo configurar un fork, crear los workspaces de Fabric, sustituir los IDs del entorno de referencia, configurar GitHub y realizar la primera promoción. Esta guía de implementación presupone que esa configuración ya está completa.

---

## Primer despliegue en un workspace vacío

Este recorrido usa la ruta estándar `fabric-cicd`. Los pasos siguientes corresponden al primer despliegue en un destino vacío. La publicación, el ETL y la actualización del modelo posteriores están automatizados, sujetos a las aprobaciones configuradas; la validación obligatoria del lanzamiento y los cambios en los requisitos de configuración siguen siendo tareas independientes.

### Paso 1: desencadenar el despliegue

Con `DEPLOY_METHOD=fabric-cicd` o sin definir, fusione un PR válido de `dev -> test` o `test -> main` que incluya cambios en las definiciones de Fabric o en los flujos de trabajo. Se aplican las aprobaciones de despliegue configuradas. En este ejemplo, el trabajo estándar ejecuta tres fases de publicación:

- **Fase 1:** despliega el Lakehouse vacío y la definición de la Ontology.
- **Fase 2:** despliega los elementos dependientes distintos de Data Pipeline —Variable Library, Notebooks, Semantic Model, Report y Data Agent— con las sustituciones de destino.
- **Fase 3:** publica el Data Pipeline con un estado actualizado del workspace para resolver los IDs de sus Notebooks y modelo, creados en la fase 2.

### Paso 2: el ETL carga el Lakehouse y después actualiza el modelo

El trabajo dependiente de ETL del despliegue inicia el Data Pipeline cuando el despliegue termina correctamente. El Notebook de carga crea y carga `doctors`, `patients` y `appointments`; la validación debe completarse correctamente antes de la actualización nativa del modelo. El trabajo de despliegue seleccionado crea o reutiliza y verifica el par de conexiones de Workspace Identity de destino antes de que el publicador lo valide y lo utilice en modo de solo lectura. Véase el [contrato del pipeline](fabric-release-process.md#actualización-del-semantic-model-posterior-al-etl); el Notebook de carga no cambia ni actualiza el modelo por sí mismo.

### Paso 3: configurar el origen de datos del Graph Model (manual)

La Ontology se despliega solo como definición: su Graph Model no tiene una vinculación con un origen de datos hasta que se configura manualmente.

1. Abra el elemento **Ontology** en la interfaz de Fabric y vaya al **Graph Model**.
2. Seleccione **Get data** para vincular el Graph Model a las tablas del Lakehouse.

### Paso 4: activar la Ontology (solución manual)

Tras configurar el origen de datos, la Ontology puede quedarse en *"Setting up your ontology — We are preparing the ontology overview for the first time."* Es un comportamiento conocido de la plataforma Fabric en el primer despliegue.

**Solución alternativa:** seleccione cualquier Entity Type de la Ontology, cámbiele el nombre por uno temporal y después restablezca el original. Esto hace que Fabric termine de inicializar la vista general de la Ontology.

### Paso 5: verificar de principio a fin

Confirme que todos los elementos funcionan en el workspace de destino:

- **Lakehouse:** tablas cargadas y validación de solo lectura del origen superada.
- **Data Pipeline:** conexiones y vinculaciones del modelo de destino verificadas; las tres actividades completadas con las credenciales previstas para cada actividad.
- **Ontology:** la vista general carga y se ven los tipos de entidad y las relaciones.
- **Semantic Model:** verificar el destino Direct Lake desplegado, la finalización de la actualización y los permisos necesarios del propietario, la conexión y el origen; configurar una conexión compatible si el primer despliegue lo requiere y después comprobar campos como `appointment_date` y `date_of_birth` y los cálculos necesarios.
- **Report:** se visualiza con datos del Semantic Model.
- **Data Agent:** referencia la Ontology y responde a las consultas.

> **Nota:** los pasos de Ontology anteriores corresponden a la configuración inicial de un destino vacío. La automatización posterior de publicación, ETL y actualización del modelo no sustituye la verificación del paso 5 ni las [comprobaciones de lanzamiento](fabric-cicd-quality-gates-and-release-controls.md) específicas de la carga de trabajo.

---

## Problemas habituales y decisiones clave

### El problema del huevo y la gallina: el ID del Lakehouse

En la ruta predeterminada de fabric-cicd sin publicación masiva, la Variable Library y el Semantic Model necesitan un ID de Lakehouse que no existe hasta el primer despliegue. Las sustituciones `$items` se resuelven a partir del inventario de destino, por lo que un elemento dependiente no puede resolver un requisito que aún no se ha desplegado. La ruta masiva de fabric-cicd tiene su propia gestión de dependencias por etapas; el comportamiento del cliente descrito aquí corresponde a la ruta predeterminada sin publicación masiva.

**Solución:** la fase 1 publica Lakehouse + Ontology. Una nueva llamada de fase 2 puede resolver sus IDs para la Library, los Notebooks, el modelo, el informe y el Data Agent. El mismo límite de la caché de estado afecta al nuevo pipeline: la fase 3 publica el Data Pipeline después de volver a descubrir sus dependencias de Notebook y modelo de la fase 2. Cada fase debe terminar correctamente antes de que empiece la siguiente; la limpieza se realiza tras una publicación correcta. Son llamadas de publicación, no tres ejecuciones de la carga de trabajo. Si no existe ningún Data Pipeline, se omite la tercera llamada.

### Acotar los tipos de elemento

Si se omite `item_type_in_scope`, fabric-cicd intenta desplegar todos los tipos de elemento y puede contar archivos que no son elementos —por ejemplo, los recursos de tema de un Report— como elementos independientes, con recuentos incorrectos.

**Solución:** establecer explícitamente `item_type_in_scope` en los flujos de trabajo de despliegue: `["Lakehouse", "Ontology", "VariableLibrary", "Notebook", "SemanticModel", "Report", "DataAgent", "DataPipeline"]`. Así se incluyen los tipos de la carga de trabajo sin publicar los elementos de control DeploymentPlan.

### El problema del huevo y la gallina: el ID del Notebook de ETL

El paso posterior ahora inicia un Data Pipeline en lugar de un Notebook independiente, pero el problema de búsqueda en tiempo de ejecución es el mismo: los IDs físicos de los elementos varían entre workspaces.

**Solución:** resolver `Patterns_Load_Validate_And_Refresh` por **nombre para mostrar** y tipo de elemento mediante la [API List Items de Fabric](https://learn.microsoft.com/en-us/rest/api/fabric/core/items/list-items). Esta búsqueda no repara las vinculaciones de actividades de la definición; las sustituciones del despliegue y la configuración de conexiones ya deben apuntar al entorno correcto.

### Los nombres de entorno deben coincidir con los de los conjuntos de valores

El parámetro `environment` que se pasa a `FabricWorkspace` de fabric-cicd establece el conjunto de valores activo de la Variable Library. Los archivos se llaman `Test.json` y `Prod.json`, por lo que los valores de entorno deben ser `Test` y `Prod`, con mayúscula inicial. Los entornos de GitHub no distinguen mayúsculas y minúsculas, de modo que `Test` se resuelve correctamente al entorno `Test`.

### Rol del Service principal: Contributor, no Admin

La [API Create Item](https://learn.microsoft.com/en-us/rest/api/fabric/core/items/create-item) de Fabric requiere el rol de workspace **Contributor**. Es el mínimo necesario: Member y Admin también funcionan, pero incumplen el principio de privilegio mínimo.

### Acciones fijadas a SHA de commit

Siguiendo la [guía oficial de GitHub](https://docs.github.com/en/copilot/tutorials/customization-library/custom-instructions/github-actions-helper), las acciones de terceros se fijan a SHA de *commit* completos, no a etiquetas de versión, para evitar ataques a la cadena de suministro:

- `actions/checkout@de0fac2e4500dabe0009e67214ff5f5447ce83dd` (v6)
- `actions/setup-python@a309ff8b426b58ec0e2a45f0f869d46889d02405` (v6)

### Despliegue completo en cada ejecución

La ruta predeterminada publica todos los elementos de su ámbito seleccionado, no solo los archivos modificados en el último commit. Publicar definiciones no concilia por sí solo los datos, las conexiones, los permisos ni otros estados externos.

### DefaultAzureCredential está obsoleto

fabric-cicd ha marcado `DefaultAzureCredential` como obsoleto. Todos los flujos de trabajo usan `ClientSecretCredential` explícitamente, según la [documentación de autenticación de fabric-cicd](https://microsoft.github.io/fabric-cicd/latest/example/authentication/).

### El filtro de rutas evita ejecuciones innecesarias

Los flujos invocadores de despliegue estándar observan las definiciones de Fabric y los archivos de flujos de trabajo. Los basados en planes también observan sus rutas de plan, código y dependencias; véase la [referencia común de flujos invocadores](fabric-release-process.md#flujos-de-trabajo-de-despliegue). Los commits que solo modifican documentación no activan estos despliegues.

---

## Referencias

- [Proceso de lanzamiento](fabric-release-process.md): contrato común de promoción, conexiones, flujos de trabajo y Data Pipeline.
- [Configuración](SETUP.md): requisitos y configuración de un fork nuevo.
- [Opciones de lanzamiento de CI/CD en Fabric](fabric-cicd-release-options.md): comparación de opciones, punto de partida recomendado sin publicación masiva y extensiones híbridas opcionales.
- [Biblioteca de Python fabric-cicd](https://microsoft.github.io/fabric-cicd): documentación, primeros pasos y tipos de elemento compatibles.
- [Parametrización de fabric-cicd](https://microsoft.github.io/fabric-cicd/latest/how_to/parameterization/): referencia de `parameter.yml` con `find_replace` y sustitución dinámica de `$items`.
- [Tipos de elemento de fabric-cicd](https://microsoft.github.io/fabric-cicd/latest/reference/item_types/): notas por tipo, incluido el conjunto de valores activo de Variable Library.
- [Ejemplos de autenticación de fabric-cicd](https://microsoft.github.io/fabric-cicd/latest/example/authentication/): patrones de credenciales para GitHub Actions.
- [API Create Item de Fabric: permisos](https://learn.microsoft.com/en-us/rest/api/fabric/core/items/create-item): requisito del rol Contributor.
- [Modelo de permisos de Fabric](https://learn.microsoft.com/en-us/fabric/security/permission-model): roles de workspace Admin, Member, Contributor y Viewer.
- [API de actualización de Power BI](https://learn.microsoft.com/en-us/rest/api/power-bi/datasets/refresh-dataset-in-group): iniciar una actualización mejorada del Semantic Model.
- [Inventario de conjuntos de datos de Power BI](https://learn.microsoft.com/en-us/rest/api/power-bi/datasets/get-datasets-in-group): resolver el modelo en el workspace de destino.
- [Detalles de ejecución de una actualización de Power BI](https://learn.microsoft.com/en-us/rest/api/power-bi/datasets/get-refresh-execution-details-in-group): seguir la solicitud de actualización concreta.
- [Framing de Direct Lake](https://learn.microsoft.com/en-us/fabric/fundamentals/direct-lake-how-it-works#framing): comportamiento de actualización de las tablas Direct Lake.
- [Permisos del propietario de Direct Lake](https://learn.microsoft.com/en-us/fabric/fundamentals/direct-lake-security-integration#direct-lake-owners): la autorización del propietario sobre el origen se comprueba con independencia de quién actualice.
- [CI/CD de Variable Library](https://learn.microsoft.com/en-us/fabric/cicd/variable-library/variable-library-cicd): conjuntos de valores, conjunto activo e integración de Git.
- [Flujos de trabajo reutilizables de GitHub](https://docs.github.com/en/actions/sharing-automations/reusing-workflows): `workflow_call`, entradas y secretos.
- [Reglas de protección de entornos de GitHub](https://docs.github.com/en/actions/managing-workflow-runs-and-deployments/managing-deployments/managing-environments-for-deployment): revisores obligatorios y restricciones de rama de despliegue.
- [GitHub Actions Helper: instrucciones personalizadas](https://docs.github.com/en/copilot/tutorials/customization-library/custom-instructions/github-actions-helper): instrucciones oficiales de Copilot para los flujos de trabajo de Actions.

---

## Sobre esta traducción

Este documento es una traducción de [fabric-hybrid-cicd-guide.md](../../fabric-hybrid-cicd-guide.md). La versión en inglés es la fuente de referencia y puede estar más actualizada.

La actualización del 15-10-2026 se ha revisado con asistencia de IA, sin nueva validación por hablantes nativos. Se conservan las decisiones anteriores de [`GLOSARIO.md`](GLOSARIO.md) y se aplica [`GUIA-DE-ESTILO.md`](GUIA-DE-ESTILO.md).

Los enlaces externos apuntan a la documentación en inglés. Las citas literales conservan el texto original y, cuando corresponde, se acompañan de una traducción identificada. Los errores pueden comunicarse mediante una incidencia que indique el idioma. Si el error también existe en inglés, debe corregirse primero allí; véanse [`REVISION.md`](REVISION.md) y [`TRANSLATION.md`](../../TRANSLATION.md).
