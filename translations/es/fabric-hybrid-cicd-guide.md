[English](../../fabric-hybrid-cicd-guide.md) | **Español**

<!-- source: fabric-hybrid-cicd-guide.md @ d5c92c3 | translated: 2026-09-28 -->

> 📄 **La versión en inglés de este documento es la autoritativa.** En caso de discrepancia, [el original en inglés](../../fabric-hybrid-cicd-guide.md) tiene precedencia.

# Guía de implementación híbrida de CI/CD

Este repositorio implementa la **recomendación híbrida de CI/CD** para Microsoft Fabric mediante **fabric-cicd**. Muestra cómo desplegar elementos de un workspace de Fabric (*Notebooks*, *Lakehouses*, *Variable Libraries*, *Semantic Models*, *Reports*, *Ontologies* y *Data Agents*) entre entornos con GitHub Actions.

Para la estrategia completa de CI/CD, la comparación de opciones de publicación y el razonamiento de la recomendación, véase [fabric-cicd-release-options.md](fabric-cicd-release-options.md).

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
┌─────────────────────────────────────────────────────┐
│  deploy-test.yml (orquestador)                      │
│                                                     │
│  deploy-fabric-cicd                                 │
│    └─ reusable-deploy-fabric-cicd.yml               │
│       └─ fabric-cicd: publish_all_items()           │
│          (Fase 1: Lakehouse + Ontology)             │
│          (Fase 2: el resto de elementos)            │
└─────────────────────────────────────────────────────┘
                     │ workflow_run (si tiene éxito)
                     ▼
┌─────────────────────────────────────────────────────┐
│  etl-test.yml                                       │
│    └─ reusable-fabric-etl.yml                       │
│       └─ API REST de Fabric: ejecuta Notebook       │
└─────────────────────────────────────────────────────┘
```

El mismo patrón se aplica a Prod (`deploy-prod.yml` → `etl-prod.yml`), desencadenado por un *push* a `main`.

> Junto a esta ruta estándar de fabric-cicd existen rutas de despliegue alternativas —una ruta directa con la API de importación masiva y una variante `fabric-cicd-bulk` que ejecuta fabric-cicd con la publicación masiva habilitada—, todas seleccionables mediante la variable de repositorio `DEPLOY_METHOD`. La ruta estándar de fabric-cicd que se muestra aquí es la recomendada; véase [fabric-cicd frente a las API masivas](fabric-cicd-release-options.md#herramientas-dentro-de-la-opción-3-fabric-cicd-frente-a-las-api-masivas) para la comparación y la [Guía de implementación de CI/CD masivo](fabric-bulk-cicd-guide.md) para el recorrido de la ruta masiva.

### Ramas y workspaces

| Rama | Workspace | Método de despliegue |
|---|---|---|
| `dev` | Dev (microsoft-fabric-sdlc-patterns-dev) | Conectado a Git mediante la integración de Git de Fabric |
| `test` | Test (microsoft-fabric-sdlc-patterns-test) | fabric-cicd mediante GitHub Actions |
| `main` | Prod (microsoft-fabric-sdlc-patterns-prod) | fabric-cicd mediante GitHub Actions |

- El workspace de **Dev** es el único conectado a Git. Desde ahí se hace *Branch Out* para el trabajo aislado en características.
- Los workspaces de **Test** y **Prod** NO están conectados a Git. Reciben los despliegues exclusivamente a través de fabric-cicd.

---

## Estructura del repositorio

```
microsoft-fabric-sdlc-patterns/
├── .github/
│   ├── instructions/
│   │   ├── actions.instructions.md          # Instrucciones de Copilot para escribir flujos de trabajo
│   │   └── python.instructions.md           # Instrucciones de Copilot para scripts de Python
│   └── workflows/
│       ├── deploy-test.yml                       # Orquestador: push a test → despliegue con fabric-cicd
│       ├── deploy-prod.yml                       # Orquestador: push a main → despliegue con fabric-cicd
│       ├── deploy-test-bulk.yml                  # Orquestador alternativo: despliegue con API masiva al hacer push a test
│       ├── deploy-prod-bulk.yml                  # Orquestador alternativo: despliegue con API masiva al hacer push a main
│       ├── etl-test.yml                          # Se activa cuando cualquier flujo deploy-test* termina con éxito
│       ├── etl-prod.yml                          # Se activa cuando cualquier flujo deploy-prod* termina con éxito
│       ├── reusable-deploy-fabric-cicd.yml       # Plantilla: despliegue con fabric-cicd
│       ├── reusable-deploy-bulk.yml              # Plantilla: despliegue con la API de importación masiva (versión preliminar)
│       ├── reusable-fabric-etl.yml               # Plantilla: ejecuta un Notebook con la API REST de Fabric
│       ├── check-pr-ready.yml                    # Comprobación de PR: impide que los IDs de feature lleguen a dev
│       ├── run-tests.yml                         # Comprobación de PR: ejecuta pytest cuando cambian scripts o pruebas
│       └── enforce-promotion-path.yml            # Comprobación de PR: impone la promoción dev→test→main por rama de origen
├── data/
│   └── fabric/                              # Definiciones de los elementos de Fabric (repository_directory)
│       ├── parameter.yml                    # Parametrización de fabric-cicd en el despliegue
│       ├── bulk-parameter.yml               # Parametrización de la ruta masiva (formato independiente)
│       ├── PatternsLakehouse.Lakehouse/
│       ├── Patterns_Ontology.Ontology/
│       ├── Patterns_Variables.VariableLibrary/
│       │   ├── variables.json
│       │   ├── settings.json
│       │   └── valueSets/
│       │       ├── Test.json
│       │       └── Prod.json
│       ├── Import_Patterns_Data.Notebook/   # Notebook de ETL (crea las tablas Delta)
│       ├── Patterns_Patients_Data.Notebook/
│       ├── Patterns_Demo.Notebook/
│       ├── Patterns_Semantic_Model.SemanticModel/
│       ├── Patterns_Report.Report/
│       └── Patterns_Data_Agent.DataAgent/
├── scripts/
│   ├── workspace_swap.py                    # Inicializa y restablece los enlaces del workspace de feature
│   ├── deploy_fabric_cicd.py                # Despliegue con fabric-cicd (lo invoca reusable-deploy-fabric-cicd.yml)
│   ├── deploy_bulk.py                       # Despliegue con la API de importación masiva (lo invoca reusable-deploy-bulk.yml)
│   └── run_fabric_etl.py                    # Ejecuta un trabajo de Notebook de Fabric (lo invoca reusable-fabric-etl.yml)
├── assets/                                  # Diagramas de arquitectura (SVG)
├── fabric-cicd-release-options.md           # Estrategia de CI/CD y comparación de opciones de publicación
├── fabric-hybrid-cicd-guide.md               # Este archivo
├── fabric-development-process.md             # Proceso de desarrollo
└── README.md                                # Página de inicio del repositorio
```

---

## Flujo de despliegue

### Qué desencadena qué

| Evento | Flujo de trabajo desencadenado | Qué hace |
|---|---|---|
| *Push* a la rama `test` (cambios en `data/fabric/**`) | `deploy-test.yml` | Despliega todos los elementos compatibles en el workspace de Test |
| `deploy-test.yml` termina con éxito | `etl-test.yml` | Ejecuta el *Notebook* `Import_Patterns_Data` en el workspace de Test |
| *Push* a la rama `main` (cambios en `data/fabric/**`) | `deploy-prod.yml` | Despliega todos los elementos compatibles en el workspace de Prod |
| `deploy-prod.yml` termina con éxito | `etl-prod.yml` | Ejecuta el *Notebook* `Import_Patterns_Data` en el workspace de Prod |

### Trabajo de despliegue

Cada flujo de trabajo de despliegue llama a `reusable-deploy-fabric-cicd.yml`, que publica desde Git en el workspace de destino todos los elementos compatibles mediante fabric-cicd. Usa un enfoque en dos fases: la fase 1 despliega el *Lakehouse* y la *Ontology*, y la fase 2 despliega el resto de elementos (*Variable Library*, *Notebooks*, *Semantic Model*, *Report* y *Data Agent*). Los tipos de elemento se acotan explícitamente con `item_type_in_scope`.

El flujo de trabajo de ETL se activa automáticamente cuando el de despliegue termina con éxito. Si el despliegue falla, el ETL no se ejecuta.

> **Nota:** si el workspace incluye tipos de elemento que fabric-cicd aún no admite, esto puede ampliarse a un patrón «sándwich» de varios trabajos: (1) desplegar los elementos compatibles, (2) promover los no compatibles mediante la [API REST de *Deployment Pipelines* de Fabric](https://learn.microsoft.com/en-us/rest/api/fabric/core/deployment-pipelines/deploy-stage-content) y (3) desplegar los elementos compatibles que dependan de los no compatibles. Véase [fabric-cicd-release-options.md](fabric-cicd-release-options.md) para más detalles.

---

## Flujos de trabajo de GitHub Actions

### Plantillas reutilizables (invocadas con `workflow_call`)

| Plantilla | Propósito |
|---|---|
| `reusable-deploy-fabric-cicd.yml` | Despliegue con fabric-cicd en dos fases: la fase 1 despliega el *Lakehouse* y la *Ontology*, y la fase 2 el resto de elementos mediante `publish_all_items()` y `unpublish_all_orphan_items()`. Acepta las entradas `environment`, `repository_directory` y, opcionalmente, `item_type_in_scope`. |
| `reusable-fabric-etl.yml` | Resuelve un elemento de Fabric por **nombre** (no por ID) mediante la API List Items, después inicia un trabajo (RunNotebook) y consulta su estado hasta que termina. No hace falta conocer de antemano ningún ID de elemento. |

### Por qué flujos de trabajo reutilizables y no acciones compuestas

Los flujos de trabajo reutilizables admiten la palabra clave `environment:` a nivel de trabajo, lo que permite:

- **Reglas de protección de entornos de GitHub** (revisores obligatorios, restricciones de rama en Prod)
- **Secretos de ámbito de entorno** (cada entorno tiene su propio `FABRIC_WORKSPACE_ID`)
- `secrets: inherit`, que reenvía todos los secretos del entorno sin enumerarlos

---

## Estrategia de configuración

Dos mecanismos complementarios gestionan la configuración específica de cada entorno:

### 1. Variable Libraries (en tiempo de ejecución)

Los *Notebooks* llaman a `notebookutils.variableLibrary.getLibrary("Patterns_Variables")` durante su ejecución para resolver IDs de workspace, nombres de *Lakehouse* y otros valores. La *Variable Library* tiene un **conjunto de valores** por entorno:

| Variable | Predeterminado (Dev) | Test | Prod |
|---|---|---|---|
| `target_workspace_id` | ID del workspace de Dev | ID del workspace de Test | ID del workspace de Prod |
| `target_workspace_name` | `microsoft-fabric-sdlc-patterns-dev` | `microsoft-fabric-sdlc-patterns-test` | `microsoft-fabric-sdlc-patterns-prod` |
| `target_lakehouse_name` | `PatternsLakehouse` | *(predeterminado)* | *(predeterminado)* |
| `target_lakehouse_id` | ID del *Lakehouse* de Dev | ID del *Lakehouse* de Dev* | ID del *Lakehouse* de Dev* |

\* `target_lakehouse_id` usa el GUID de Dev como marcador de posición en los archivos de conjunto de valores. En el momento del despliegue, `parameter.yml` lo sustituye por el ID real del *Lakehouse* en el workspace de destino (véase más abajo).

**Enlace del conjunto de valores activo:** fabric-cicd establece automáticamente el conjunto de valores activo a partir del parámetro `environment` que se pasa a `FabricWorkspace`. Cuando `environment="Test"`, se activa el conjunto de valores `Test`. Esto ocurre en cada despliegue, sin intervención manual.

> Cita: [fabric-cicd Item Types — Variable Library](https://microsoft.github.io/fabric-cicd/latest/reference/item_types/): *"The active value set of the variable library is defined by the `environment` field passed into the `FabricWorkspace` object."*
>
> Traducción: «El conjunto de valores activo de la *Variable Library* lo define el campo `environment` que se pasa al objeto `FabricWorkspace`.»

### 2. parameter.yml (en el momento del despliegue)

El archivo `parameter.yml` de `data/fabric/` usa `find_replace` de fabric-cicd con **sustitución dinámica** para resolver el ID del *Lakehouse* en el momento del despliegue:

```yaml
find_replace:
    - find_value: "7694ebac-deb9-4a40-a846-0782b36b3bda"  # Dev lakehouse ID
      replace_value:
          _ALL_: "$items.Lakehouse.PatternsLakehouse.$id"  # Resolved at deploy time
      item_type: "VariableLibrary"
```

**Cómo funciona:** fabric-cicd despliega los elementos en orden de dependencia, de modo que el *Lakehouse* se crea antes que la *Variable Library*. Al procesar los archivos de la *Variable Library*, `$items.Lakehouse.PatternsLakehouse.$id` se resuelve al GUID real del *Lakehouse* en el workspace de destino. La clave `_ALL_` indica que se aplica a todos los entornos.

---

## Requisitos previos y configuración

### 1. Fabric Capacity

Se necesita una *Fabric Capacity* o una capacidad de Power BI Premium para todos los workspaces.

### 2. Workspaces de Fabric

Hacen falta tres workspaces:

- **microsoft-fabric-sdlc-patterns-dev**: conectado a la rama `dev` mediante la integración de Git de Fabric
- **microsoft-fabric-sdlc-patterns-test**: sin conexión a Git, recibe los despliegues mediante fabric-cicd
- **microsoft-fabric-sdlc-patterns-prod**: sin conexión a Git, recibe los despliegues mediante fabric-cicd

### 3. Service principal

Cree un service principal para la automatización de CI/CD:

```bash
az ad sp create-for-rbac --name "SPN-Microsoft-Fabric-SDLC-Patterns" \
  --query "{tenantId:tenant, clientId:appId, clientSecret:password}" -o json
```

- Añada el service principal como **colaborador** en los workspaces de Test y Prod (Workspace → Manage access → Add people or groups)
- Colaborador es el rol mínimo necesario según la documentación de la [API Create Item de Fabric](https://learn.microsoft.com/en-us/rest/api/fabric/core/items/create-item)

> **Importante:** alguien con rol de administrador de Fabric debe habilitar el acceso de service principals a las API de Fabric en el portal de administración, dentro de la configuración de desarrollador, y limitarlo a un grupo de seguridad que contenga únicamente los service principals de CI/CD. Véanse la [configuración de inquilino para desarrolladores](https://learn.microsoft.com/en-us/fabric/admin/service-admin-portal-developer) y las [Consideraciones de gobernanza](fabric-cicd-governance-considerations.md).

### 4. Entornos de GitHub

Cree dos entornos de GitHub en la configuración del repositorio (Settings → Environments):

| Entorno | Reglas de protección |
|---|---|
| `Test` | Ninguna (el despliegue se ejecuta automáticamente al fusionar) |
| `Prod` | Revisores obligatorios y restricción de la rama de despliegue únicamente a `main` |

> **Nota:** los nombres de los entornos de GitHub no distinguen mayúsculas, pero deben coincidir con los nombres de los conjuntos de valores de la *Variable Library* (`Test`, `Prod`), porque fabric-cicd usa el valor de `environment` para establecer el conjunto de valores activo.

### 5. Secretos de entorno de GitHub

Añada estos secretos a **ambos** entornos, `Test` y `Prod`:

| Secreto | Descripción |
|---|---|
| `AZURE_TENANT_ID` | ID del inquilino de Entra ID |
| `AZURE_CLIENT_ID` | ID de cliente o de aplicación del service principal |
| `AZURE_CLIENT_SECRET` | Secreto de cliente del service principal |
| `FABRIC_WORKSPACE_ID` | ID del workspace de destino (distinto en cada entorno) |

Los tres primeros secretos son idénticos en ambos entornos (un único service principal). `FABRIC_WORKSPACE_ID` cambia:

- Test: el ID del workspace de Test
- Prod: el ID del workspace de Prod

### 6. Instrucciones de Copilot

El archivo `.github/instructions/actions.instructions.md` proporciona instrucciones de Copilot específicas por ruta para escribir flujos de trabajo de GitHub Actions. Se aplican automáticamente al editar cualquier archivo `.yml` bajo `.github/workflows/` y cubren seguridad (fijar acciones a SHA, permisos mínimos), rendimiento (`timeout-minutes`) y prácticas recomendadas de fabric-cicd.

---

## Primer despliegue en un workspace vacío

Al desplegar en un workspace por primera vez (por ejemplo, uno de Test o Prod recién creado), siga estos pasos en orden. Los despliegues posteriores están completamente automatizados: solo el primero requiere intervención manual.

### Paso 1: desencadenar el despliegue

Haga *push* a la rama de destino (`test` o `main`). El flujo de trabajo de despliegue se activa automáticamente y ejecuta dos fases:

- **Fase 1:** despliega el *Lakehouse* (vacío) y la definición de la *Ontology*
- **Fase 2:** despliega el resto de elementos (*Variable Library*, *Notebooks*, *Semantic Model*, *Report* y *Data Agent*) con los IDs de *Lakehouse* y workspace parametrizados

### Paso 2: el ETL carga el Lakehouse

El flujo de trabajo de ETL (`etl-test.yml` o `etl-prod.yml`) se activa automáticamente tras un despliegue correcto. Ejecuta el *Notebook* `Import_Patterns_Data`, que crea y carga las tablas Delta (`doctors`, `patients`, `appointments`) en el *Lakehouse*.

### Paso 3: configurar el origen de datos del Graph Model (manual)

La *Ontology* se despliega solo como definición: su Graph Model no tiene enlace a un origen de datos hasta que se configura manualmente.

1. Abra el elemento **Ontology** en la interfaz de Fabric y vaya al **Graph Model**
2. Seleccione **Get data** para enlazar el Graph Model con las tablas del *Lakehouse*

### Paso 4: activar la Ontology (solución manual)

Tras configurar el origen de datos, la *Ontology* puede quedarse en *"Setting up your ontology — We are preparing the ontology overview for the first time."* Es un comportamiento conocido de la plataforma Fabric en el primer despliegue.

**Solución alternativa:** seleccione cualquier Entity Type de la *Ontology*, cámbiele el nombre por uno temporal y vuelva a ponerle el original. Eso hace que Fabric termine de inicializar la vista general de la *Ontology*.

### Paso 5: verificar de principio a fin

Confirme que todos los elementos funcionan en el workspace de destino:

- **Lakehouse**: tablas cargadas con datos
- **Ontology**: la vista general carga y se ven los tipos de entidad y las relaciones
- **Semantic Model**: conectado al *Lakehouse* (puede requerir configurar la conexión manualmente en el primer despliegue; véanse los [Problemas habituales](#problemas-habituales-y-decisiones-clave))
- **Report**: se representa con datos del *Semantic Model*
- **Data Agent**: referencia la *Ontology* y responde a las consultas

> **Nota:** en los despliegues posteriores todos los pasos están automatizados. Los pasos manuales de la *Ontology* (3 y 4) solo son necesarios en el primer despliegue a un workspace vacío.

---

## Problemas habituales y decisiones clave

### El problema del huevo y la gallina: el ID del Lakehouse

La *Variable Library* y el *Semantic Model* necesitan el ID del *Lakehouse* de cada entorno, pero el *Lakehouse* no existe en Test ni en Prod hasta que lo crea el primer despliegue. Las variables dinámicas `$items` de fabric-cicd (por ejemplo, `$items.Lakehouse.PatternsLakehouse.$id`) se resuelven consultando el **workspace de destino en vivo** durante la parametrización, antes de publicar los elementos. En el primer despliegue a un workspace vacío, esa consulta no devuelve nada y la parametrización falla.

**Solución:** el flujo de trabajo `reusable-deploy-fabric-cicd.yml` usa un **despliegue en dos fases**. La fase 1 llama a `publish_all_items()` con `item_type_in_scope=["Lakehouse", "Ontology"]` para crear primero el *Lakehouse* y la *Ontology*. El *Lakehouse* debe existir para que `$items.Lakehouse.PatternsLakehouse.$id` se resuelva en las reglas de `parameter.yml`. La *Ontology* debe existir para que se resuelva la referencia por `logicalId` del *Data Agent* (fabric-cicd almacena en caché el estado del workspace una vez por cada llamada a `publish_all_items()`, así que los elementos desplegados dentro de la misma llamada no son visibles para la resolución de `logicalId` de los elementos posteriores). La fase 2 llama a `publish_all_items()` con el resto de tipos de elemento. En los despliegues posteriores, ambas fases son idempotentes.

### Acotar los tipos de elemento

Si se omite `item_type_in_scope`, fabric-cicd intenta desplegar todos los tipos de elemento y puede contar archivos que no lo son (por ejemplo, los recursos de tema de un *Report*) como elementos independientes, lo que da recuentos incorrectos.

**Solución:** establecer explícitamente `item_type_in_scope` en los flujos de trabajo de despliegue: `["Lakehouse", "Ontology", "VariableLibrary", "Notebook", "SemanticModel", "Report", "DataAgent"]`. Así solo se despliegan tipos de elemento válidos.

### El problema del huevo y la gallina: el ID del Notebook de ETL

El flujo de trabajo de ETL necesita ejecutar un *Notebook*, pero su ID cambia en cada workspace y no se conoce hasta después del despliegue.

**Solución:** el flujo de trabajo de ETL resuelve el *Notebook* por su **nombre para mostrar** en tiempo de ejecución mediante la [API List Items de Fabric](https://learn.microsoft.com/en-us/rest/api/fabric/core/items/list-items), no por su ID. El nombre del *Notebook* (`Import_Patterns_Data`) es idéntico en todos los entornos porque procede del repositorio Git.

### Los nombres de entorno deben coincidir con los de los conjuntos de valores

El parámetro `environment` que se pasa a `FabricWorkspace` de fabric-cicd sirve para establecer el conjunto de valores activo de la *Variable Library*. Los archivos de conjunto de valores se llaman `Test.json` y `Prod.json`, así que los valores de entorno deben ser `Test` y `Prod`, con mayúscula inicial. Los entornos de GitHub no distinguen mayúsculas, de modo que `Test` se resuelve correctamente al entorno `Test`.

### Rol del service principal: colaborador, no administrador

La [API Create Item](https://learn.microsoft.com/en-us/rest/api/fabric/core/items/create-item) de Fabric requiere el rol de workspace **colaborador**. Es el mínimo necesario: los roles de miembro y administrador también funcionan, pero incumplen el principio de privilegio mínimo.

### Acciones fijadas a SHA de commit

Siguiendo la [guía oficial de GitHub](https://docs.github.com/en/copilot/tutorials/customization-library/custom-instructions/github-actions-helper), las acciones de terceros se fijan a SHA de *commit* completos, no a etiquetas de versión, para evitar ataques a la cadena de suministro:

- `actions/checkout@de0fac2e4500dabe0009e67214ff5f5447ce83dd` (v6)
- `actions/setup-python@a309ff8b426b58ec0e2a45f0f869d46889d02405` (v6)

### Despliegue completo en cada ejecución

fabric-cicd no calcula diferencias entre *commits*. Cada elemento dentro del ámbito se publica en cada ejecución. Es intencionado: garantiza que el workspace coincida siempre exactamente con el repositorio Git.

### DefaultAzureCredential está obsoleto

fabric-cicd ha marcado `DefaultAzureCredential` como obsoleto. Todos los flujos de trabajo usan `ClientSecretCredential` de forma explícita, según la [documentación de autenticación de fabric-cicd](https://microsoft.github.io/fabric-cicd/latest/example/authentication/).

### El filtro de rutas evita ejecuciones innecesarias

Los flujos de trabajo de despliegue solo se activan cuando cambian archivos bajo `data/fabric/**`. Los *commits* que solo tocan documentación (por ejemplo, editar este archivo) no desencadenan ningún despliegue.

---

## Referencias

- [Opciones de publicación de CI/CD para Fabric](fabric-cicd-release-options.md) — Documento completo de estrategia con la comparación de opciones y la recomendación híbrida
- [Biblioteca de Python fabric-cicd](https://microsoft.github.io/fabric-cicd) — Documentación, primeros pasos y tipos de elemento compatibles *(solo en inglés)*
- [Parametrización de fabric-cicd](https://microsoft.github.io/fabric-cicd/latest/how_to/parameterization/) — Referencia de `parameter.yml` con `find_replace` y sustitución dinámica con `$items` *(solo en inglés)*
- [Tipos de elemento de fabric-cicd](https://microsoft.github.io/fabric-cicd/latest/reference/item_types/) — Notas por tipo de elemento, incluido el comportamiento del conjunto de valores activo de la *Variable Library* *(solo en inglés)*
- [Ejemplos de autenticación de fabric-cicd](https://microsoft.github.io/fabric-cicd/latest/example/authentication/) — Patrones de credenciales para GitHub Actions *(solo en inglés)*
- [API Create Item de Fabric — Permisos](https://learn.microsoft.com/en-us/rest/api/fabric/core/items/create-item) — Requisito del rol de colaborador *(solo en inglés)*
- [Modelo de permisos de Fabric](https://learn.microsoft.com/en-us/fabric/security/permission-model) — Roles de workspace (administrador, miembro, colaborador, lector) *(solo en inglés)*
- [Variable Library y CI/CD](https://learn.microsoft.com/en-us/fabric/cicd/variable-library/variable-library-cicd) — Conjuntos de valores, comportamiento del conjunto activo e integración de Git *(solo en inglés)*
- [Flujos de trabajo reutilizables de GitHub](https://docs.github.com/en/actions/sharing-automations/reusing-workflows) — `workflow_call`, entradas y secretos *(solo en inglés)*
- [Reglas de protección de entornos de GitHub](https://docs.github.com/en/actions/managing-workflow-runs-and-deployments/managing-deployments/managing-environments-for-deployment) — Revisores obligatorios y restricciones de rama de despliegue *(solo en inglés)*
- [GitHub Actions Helper — Instrucciones personalizadas](https://docs.github.com/en/copilot/tutorials/customization-library/custom-instructions/github-actions-helper) — Instrucciones oficiales de Copilot para flujos de trabajo de Actions *(solo en inglés)*

---

## Sobre esta traducción

Este documento es una traducción de [fabric-hybrid-cicd-guide.md](../../fabric-hybrid-cicd-guide.md). La versión en inglés es la fuente autorizada y puede estar más actualizada.

La terminología sigue [`GLOSARIO.md`](GLOSARIO.md) y [`GUIA-DE-ESTILO.md`](GUIA-DE-ESTILO.md). Para revisar esta traducción, véase [`REVISION.md`](REVISION.md).

**Los enlaces a documentación externa apuntan a la versión en inglés**, y las citas textuales se reproducen en su idioma original con su traducción debajo. Los motivos están en el apartado «Sobre esta traducción» del [README en español](README.md).

Los errores pueden comunicarse abriendo una incidencia e indicando el idioma. Si el error existe también en el original en inglés, **debe corregirse primero allí**: véase [`TRANSLATION.md`](../../TRANSLATION.md).
