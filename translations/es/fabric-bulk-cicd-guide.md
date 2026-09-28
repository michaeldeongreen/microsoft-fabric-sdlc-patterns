[English](../../fabric-bulk-cicd-guide.md) | **Español**

<!-- source: fabric-bulk-cicd-guide.md @ d5c92c3 | translated: 2026-09-28 -->

> 📄 **La versión en inglés de este documento es la autoritativa.** En caso de discrepancia, [el original en inglés](../../fabric-bulk-cicd-guide.md) tiene precedencia.

# Guía de implementación de CI/CD masivo

Este repositorio implementa una ruta de despliegue paralela para Microsoft Fabric mediante la **[API Bulk Import Item Definitions](https://learn.microsoft.com/en-us/rest/api/fabric/core/items/bulk-import-item-definitions)** (versión preliminar), como alternativa a la [ruta de fabric-cicd](fabric-hybrid-cicd-guide.md). Muestra cómo desplegar entre entornos los mismos elementos de un workspace de Fabric (*Notebooks*, *Lakehouses*, *Variable Libraries*, *Semantic Models*, *Reports*, *Ontologies* y *Data Agents*) usando GitHub Actions y la API REST de Fabric directamente.

Para la comparación estratégica entre fabric-cicd y las API masivas (y la recomendación), véase [fabric-cicd-release-options.md](fabric-cicd-release-options.md#herramientas-dentro-de-la-opción-3-fabric-cicd-frente-a-las-api-masivas).

> **Contexto importante.** La propia API de importación masiva tiene carencias conocidas: no admite parametrización, ni activación de conjuntos de valores, ni eliminación. Este repositorio implementa soluciones alternativas del lado del cliente para las dos primeras, de modo que la demostración funcione de principio a fin; no son correcciones de la plataforma. Quien elija la ruta masiva en su propio proyecto asumirá ese mismo trabajo. fabric-cicd sigue siendo la ruta recomendada para producción; esta guía existe para documentar el patrón masivo como ejemplo resuelto, no como recomendación.

---

## Índice

- [Visión general de la arquitectura](#visión-general-de-la-arquitectura)
- [Estructura del repositorio](#estructura-del-repositorio)
- [Flujo de despliegue](#flujo-de-despliegue)
- [Flujos de trabajo de GitHub Actions](#flujos-de-trabajo-de-github-actions)
- [Estrategia de configuración](#estrategia-de-configuración)
- [La decisión de los dos despliegues](#la-decisión-de-los-dos-despliegues)
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
┌─────────────────────────────────────────────────────┐
│  deploy-test-bulk.yml (orquestador)                 │
│                                                     │
│  deploy-bulk                                        │
│    └─ reusable-deploy-bulk.yml                      │
│       └─ scripts/deploy_bulk.py                     │
│          (Fase 1: POST de dependencias              │
│           — Lakehouse + Ontology)                   │
│          (Fase 2: sustituir IDs,                    │
│           POST del resto de elementos)              │
│          (Tras el despliegue: PATCH del conjunto    │
│           de valores activo de VariableLibrary)     │
└─────────────────────────────────────────────────────┘
                     │ workflow_run (si tiene éxito)
                     ▼
┌─────────────────────────────────────────────────────┐
│  etl-test.yml                                       │
│    └─ reusable-fabric-etl.yml                       │
│       └─ API REST de Fabric: ejecuta Notebook       │
└─────────────────────────────────────────────────────┘
```

El mismo patrón se aplica a Prod (`deploy-prod-bulk.yml` → `etl-prod.yml`), desencadenado por un *push* a `main`.

La forma refleja deliberadamente la de la [ruta de fabric-cicd](fabric-hybrid-cicd-guide.md#visión-general-de-la-arquitectura). Ambas dividen el despliegue en dos fases por el mismo motivo: la primera crea elementos cuyos IDs necesita referenciar la segunda. Las diferencias son mecánicas:

| Concepto | fabric-cicd | Masivo |
|---|---|---|
| Llamadas por fase | Una llamada a la biblioteca (`publish_all_items()`) por fase, que internamente hace muchas llamadas REST por elemento | Un POST masivo por fase que lleva el lote completo |
| Sustitución | La biblioteca fabric-cicd aplica las reglas de `parameter.yml` de forma transparente | `scripts/deploy_bulk.py` lee `bulk-parameter.yml` y reescribe las cargas útiles entre fases |
| Activación del conjunto de valores | La biblioteca lo gestiona automáticamente cuando se pasa `environment` | Quien llama hace una llamada aparte a `PATCH /variableLibraries/{id}` |
| Limpieza de huérfanos | `unpublish_all_orphan_items()` viene incorporado | No implementado |

> Junto a esta ruta masiva existen otras rutas de despliegue —la estándar de fabric-cicd y una variante `fabric-cicd-bulk` que ejecuta fabric-cicd con la publicación masiva habilitada—, todas seleccionables mediante la variable de repositorio `DEPLOY_METHOD`. fabric-cicd es la ruta recomendada; véase [fabric-cicd frente a las API masivas](fabric-cicd-release-options.md#herramientas-dentro-de-la-opción-3-fabric-cicd-frente-a-las-api-masivas) para la comparación y [fabric-hybrid-cicd-guide.md](fabric-hybrid-cicd-guide.md) para su guía de implementación.

### Ramas y workspaces

| Rama | Workspace | Método de despliegue |
|---|---|---|
| `dev` | Dev (microsoft-fabric-sdlc-patterns-dev) | Conectado a Git mediante la integración de Git de Fabric |
| `test` | Test (microsoft-fabric-sdlc-patterns-test) | API de importación masiva mediante GitHub Actions |
| `main` | Prod (microsoft-fabric-sdlc-patterns-prod) | API de importación masiva mediante GitHub Actions |

- El workspace de **Dev** es el único conectado a Git. Desde ahí se hace *Branch Out* para el trabajo aislado en características.
- Los workspaces de **Test** y **Prod** NO están conectados a Git. Con la ruta masiva activa, reciben los despliegues a través de `scripts/deploy_bulk.py`.

---

## Estructura del repositorio

```
microsoft-fabric-sdlc-patterns/
├── .github/
│   └── workflows/
│       ├── deploy-test-bulk.yml             # Orquestador: push a test → despliegue masivo
│       ├── deploy-prod-bulk.yml             # Orquestador: push a main → despliegue masivo
│       ├── etl-test.yml                     # Se activa cuando cualquier flujo deploy-test* termina con éxito
│       ├── etl-prod.yml                     # Se activa cuando cualquier flujo deploy-prod* termina con éxito
│       ├── reusable-deploy-bulk.yml         # Plantilla: despliegue con la API de importación masiva
│       ├── reusable-fabric-etl.yml          # Plantilla: ejecuta un Notebook con la API REST de Fabric
│       ├── check-pr-ready.yml               # Comprobación de PR: impide que los IDs de feature lleguen a dev
│       ├── run-tests.yml                    # Comprobación de PR: ejecuta pytest cuando cambian scripts o pruebas
│       └── enforce-promotion-path.yml       # Comprobación de PR: impone la promoción dev→test→main por rama de origen
├── data/
│   └── fabric/                              # Definiciones de los elementos de Fabric (repository_directory)
│       ├── bulk-parameter.yml               # Parametrización de la ruta masiva (formato independiente)
│       ├── parameter.yml                    # Parametrización de fabric-cicd (la ruta masiva la ignora)
│       ├── PatternsLakehouse.Lakehouse/
│       ├── Patterns_Ontology.Ontology/
│       ├── Patterns_Variables.VariableLibrary/
│       ├── Import_Patterns_Data.Notebook/
│       ├── Patterns_Patients_Data.Notebook/
│       ├── Patterns_Demo.Notebook/
│       ├── Patterns_Semantic_Model.SemanticModel/
│       ├── Patterns_Report.Report/
│       └── Patterns_Data_Agent.DataAgent/
├── scripts/
│   ├── deploy_bulk.py                       # Despliegue con la API de importación masiva (lo invoca reusable-deploy-bulk.yml)
│   ├── deploy_fabric_cicd.py                # Despliegue con fabric-cicd (ruta alternativa)
│   ├── run_fabric_etl.py                    # Ejecuta un trabajo de Notebook de Fabric (lo invoca reusable-fabric-etl.yml)
│   └── workspace_swap.py                    # Inicializa y restablece los enlaces del workspace de feature
├── tests/
│   └── test_deploy_bulk.py                  # Pruebas unitarias del script masivo
└── ... (otros documentos, véase README)
```

Los flujos de trabajo de fabric-cicd (`deploy-test.yml`, `deploy-prod.yml`, `reusable-deploy-fabric-cicd.yml`), sus equivalentes `fabric-cicd-bulk` (`deploy-test-fabric-cicd-bulk.yml`, `deploy-prod-fabric-cicd-bulk.yml`, `reusable-deploy-fabric-cicd-bulk.yml`) y los flujos masivos conviven en el mismo directorio `.github/workflows/`. La variable de repositorio `DEPLOY_METHOD` selecciona cuál se ejecuta.

---

## Flujo de despliegue

### Qué desencadena qué

| Evento | Flujo de trabajo desencadenado | Qué hace |
|---|---|---|
| *Push* a la rama `test` (cambios en `data/fabric/**`) con `DEPLOY_METHOD=bulk` | `deploy-test-bulk.yml` | Despliega todos los elementos en el workspace de Test mediante la API de importación masiva |
| `deploy-test-bulk.yml` termina con éxito | `etl-test.yml` | Ejecuta el *Notebook* `Import_Patterns_Data` en el workspace de Test |
| *Push* a la rama `main` (cambios en `data/fabric/**`) con `DEPLOY_METHOD=bulk` | `deploy-prod-bulk.yml` | Despliega todos los elementos en el workspace de Prod mediante la API de importación masiva |
| `deploy-prod-bulk.yml` termina con éxito | `etl-prod.yml` | Ejecuta el *Notebook* `Import_Patterns_Data` en el workspace de Prod |

La variable de repositorio `DEPLOY_METHOD` (Settings → Secrets and variables → Actions → Variables) controla qué flujo de despliegue se ejecuta:

| Valor de `DEPLOY_METHOD` | Comportamiento |
|---|---|
| `fabric-cicd` *(o sin definir)* | Se ejecutan los flujos de fabric-cicd; el resto se omite |
| `fabric-cicd-bulk` | Se ejecutan los flujos de fabric-cicd con la publicación masiva habilitada (en este repositorio recurre a la estándar); el resto se omite |
| `bulk` | Se ejecutan los flujos masivos; el resto se omite |
| cualquier otro valor | Se omiten todos los flujos de despliegue (valor seguro por defecto) |

### El trabajo de despliegue masivo

Cada flujo de trabajo de despliegue llama a `reusable-deploy-bulk.yml`, que invoca `scripts/deploy_bulk.py`. El script:

1. Obtiene un token de portador de Entra ID con las credenciales de cliente del service principal.
2. Recorre `data/fabric/` y construye un array `definitionParts[]`, con una entrada por archivo que incluye la ruta y el contenido codificado en base64.
3. Carga `bulk-parameter.yml` para obtener las reglas de sustitución y la configuración de activación del conjunto de valores.
4. Decide entre un despliegue simple o doble según si alguna regla referencia `$items.<Type>.<Name>.$id`.
5. Hace POST a `https://api.fabric.microsoft.com/v1/workspaces/{ws}/items/bulkImportDefinitions?beta=true` (una o dos veces, según la decisión anterior).
6. Hace PATCH sobre la *VariableLibrary* desplegada para establecer el conjunto de valores activo.

La API de importación masiva puede devolver `200 OK` con el cuerpo del resultado en línea, o `202 Accepted` con una operación de larga duración (LRO). El script gestiona ambos casos de forma transparente; véanse los [problemas habituales](#sondeo-de-operaciones-de-larga-duración-lro).

El flujo de trabajo de ETL se activa automáticamente cuando el de despliegue termina con éxito. Si el despliegue falla, el ETL no se ejecuta.

---

## Flujos de trabajo de GitHub Actions

### Plantillas reutilizables (invocadas con `workflow_call`)

| Plantilla | Propósito |
|---|---|
| `reusable-deploy-bulk.yml` | Obtiene un token (con los secretos del service principal), descarga el repositorio, instala `requests` y `PyYAML`, e invoca `scripts/deploy_bulk.py` pasándole como variables de entorno el ID del workspace, el directorio del repositorio y el entorno de destino. |
| `reusable-fabric-etl.yml` | Resuelve un elemento de Fabric por **nombre** (no por ID) mediante la API List Items, después inicia un trabajo (RunNotebook) y consulta su estado hasta que termina. Se comparte con la ruta de fabric-cicd: es la misma plantilla, sin cambios. |

### Por qué flujos de trabajo reutilizables y no acciones compuestas

Los flujos de trabajo reutilizables admiten la palabra clave `environment:` a nivel de trabajo, lo que permite:

- **Reglas de protección de entornos de GitHub** (revisores obligatorios, restricciones de rama en Prod)
- **Secretos de ámbito de entorno** (cada entorno tiene su propio `FABRIC_WORKSPACE_ID`)
- `secrets: inherit`, que reenvía todos los secretos del entorno sin enumerarlos

### Reejecuciones manuales con `workflow_dispatch`

`etl-test.yml` y `etl-prod.yml` admiten `workflow_dispatch`, de modo que se puede volver a lanzar el trabajo de ETL desde la interfaz de Actions sin un despliegue nuevo. Se añadió para sortear una peculiaridad de `workflow_run`: al reejecutar una ejecución desencadenada por `workflow_run`, se usa el archivo del flujo de trabajo congelado en el momento del desencadenamiento original, no el de la rama predeterminada actual. Para recuperarse de fallos transitorios o de correcciones del archivo del flujo recién incorporadas a `main`, el lanzamiento manual es el camino de menor fricción.

---

## Estrategia de configuración

En la ruta masiva, tres mecanismos complementarios gestionan la configuración específica de cada entorno. Los dos primeros reflejan la [estrategia de la ruta de fabric-cicd](fabric-hybrid-cicd-guide.md#estrategia-de-configuración); el tercero es propio de la ruta masiva, porque la API no activa por sí sola los conjuntos de valores.

### 1. Variable Libraries (en tiempo de ejecución)

Los *Notebooks* llaman a `notebookutils.variableLibrary.getLibrary("Patterns_Variables")` durante su ejecución para resolver IDs de workspace, nombres de *Lakehouse* y otros valores. La *Variable Library* tiene un **conjunto de valores** por entorno:

| Variable | Predeterminado (Dev) | Test | Prod |
|---|---|---|---|
| `target_workspace_id` | ID del workspace de Dev | ID del workspace de Test | ID del workspace de Prod |
| `target_workspace_name` | `microsoft-fabric-sdlc-patterns-dev` | `microsoft-fabric-sdlc-patterns-test` | `microsoft-fabric-sdlc-patterns-prod` |
| `target_lakehouse_name` | `PatternsLakehouse` | *(predeterminado)* | *(predeterminado)* |
| `target_lakehouse_id` | ID del *Lakehouse* de Dev | ID del *Lakehouse* de Dev* | ID del *Lakehouse* de Dev* |

\* `target_lakehouse_id` usa el GUID de Dev como marcador de posición en los archivos de conjunto de valores. En el momento del despliegue, `bulk-parameter.yml` lo reescribe con el ID real del *Lakehouse* en el workspace de destino (véase más abajo).

### 2. `bulk-parameter.yml` (en el momento del despliegue)

Es el equivalente en la ruta masiva al `parameter.yml` de fabric-cicd. El formato es deliberadamente distinto: la ruta masiva implementa un subconjunto reducido del DSL de fabric-cicd, solo lo que necesitan los despliegues de este repositorio.

El archivo incluido en `data/fabric/bulk-parameter.yml` tiene este aspecto:

```yaml
substitutions:
  - find: "c185283c-9dd9-4e40-a17c-aa6303e6f0e5"          # dev lakehouse ID
    replace_with: "$items.Lakehouse.PatternsLakehouse.$id"
    item_types: [VariableLibrary, SemanticModel, Notebook]

  - find: "d7270f11-feba-4990-baa6-d45e47f23737"            # dev workspace ID
    replace_with: "$workspace.$id"
    item_types: [SemanticModel, Notebook]

variable_library:
  active_value_set: "$environment"
```

**Esquema:**

| Clave de primer nivel | Propósito |
|---|---|
| `substitutions` | Lista de reglas de búsqueda y sustitución. Cada regla tiene `find` (la cadena literal), `replace_with` (el reemplazo, con marcadores de posición opcionales) e `item_types` (lista de tipos de elemento a los que se aplica). |
| `variable_library` | Ajustes por *VariableLibrary*. De momento, solo `active_value_set`. |

**Referencia de marcadores de posición:**

| Marcador | Se resuelve a |
|---|---|
| `$workspace.$id` | El ID del workspace de destino (de la variable de entorno `FABRIC_WORKSPACE_ID`) |
| `$items.<Type>.<Name>.$id` | El ID del elemento desplegado para `<Type>/<Name>`. Se resuelve a partir de la respuesta del POST masivo de la fase 1. |
| `$environment` | El valor de la variable de entorno `ENVIRONMENT` que se pasa al paso de despliegue (`Test` o `Prod`). |

**Filtro `item_types`:** una regla solo se aplica a los archivos cuyo tipo de elemento figure en su lista `item_types`. El script extrae el tipo de elemento de la convención de ruta `<DisplayName>.<Type>/<archivo>`. Los archivos de tipos no listados pasan sin cambios.

**Por qué un archivo aparte de `parameter.yml`:** ambos formatos coexisten de forma deliberada. fabric-cicd usa `parameter.yml` y la ruta masiva usa `bulk-parameter.yml`. Mantenerlos separados evita que la ruta masiva tenga que ignorar en silencio (o fallar ante) funciones exclusivas de fabric-cicd (`key_value_replace`, `spark_pool`, `semantic_model_binding`). Ambos archivos residen en la raíz de `data/fabric/` y `scripts/deploy_bulk.py` los excluye de la carga útil de la solicitud masiva.

### 3. Activación del conjunto de valores de VariableLibrary (tras el despliegue)

La API de importación masiva sube los archivos de conjunto de valores de la *VariableLibrary*, pero NO establece cuál queda activo en el workspace desplegado. fabric-cicd hace esa selección automáticamente con su parámetro `environment`; con la API masiva, debe hacerla quien llama.

`scripts/deploy_bulk.py` realiza la llamada una vez completados los POST masivos:

```
PATCH /v1/workspaces/{workspace_id}/variableLibraries/{library_id}
Content-Type: application/json

{
  "properties": {
    "activeValueSetName": "Test"
  }
}
```

La activación está condicionada a que `variable_library.active_value_set` de `bulk-parameter.yml` no sea nulo. El marcador `$environment` se resuelve al nombre del entorno de destino (`Test` o `Prod`). Si en su lugar se indica una cadena literal, se usa ese valor exacto.

Referencia: [Update Variable Library](https://learn.microsoft.com/en-us/rest/api/fabric/variablelibrary/items/update-variable-library).

---

## La decisión de los dos despliegues

El script masivo decide automáticamente entre un flujo de un despliegue y uno de dos, según el contenido de `bulk-parameter.yml`. La decisión es determinista:

```python
needs_two_deploy = any("$items." in r.replace_with for r in config.substitutions)
```

Si alguna regla de sustitución referencia `$items.<Type>.<Name>.$id`, el despliegue debe dividirse en dos: el script necesita los IDs de elemento de la respuesta de la fase 1 antes de poder sustituirlos en las cargas útiles de la fase 2.

### Flujo de un solo despliegue (sin referencias a `$items.*`, o sin configuración)

```
1. apply_substitutions(parts, rules, workspace_id, item_id_map={})
2. POST all items at once
3. PATCH VariableLibrary if value-set activation is configured
```

Las reglas que solo usan `$workspace.$id` se aplican en este flujo, porque el ID del workspace se conoce de antemano por la variable de entorno.

### Flujo de dos despliegues (reglas que referencian `$items.*`)

```
1. partition_dependencies(parts) → (deps, remaining)
2. POST deps                                  ┐
3. extract_item_ids(deps_response)            │  Phase 1
   → item_id_map = {(Type, Name): item_id}   ┘
4. apply_substitutions(remaining, rules,      ┐
                       workspace_id,          │
                       item_id_map)           │  Phase 2
5. POST remaining                             ┘
6. PATCH VariableLibrary if value-set activation is configured
```

`DEPENDENCY_TYPES`, en `scripts/deploy_bulk.py`, define qué cuenta como dependencia. La lista es deliberadamente reducida: solo deben figurar los tipos a los que realmente apunta `$items.<Type>.*` en `bulk-parameter.yml`. En este repositorio son `("Lakehouse", "Ontology")`.

Esto refleja el despliegue en dos fases de la ruta de fabric-cicd; véase [el problema del huevo y la gallina en la guía híbrida](fabric-hybrid-cicd-guide.md#el-problema-del-huevo-y-la-gallina-el-id-del-lakehouse) para el mismo problema planteado desde fabric-cicd.

### Cuándo falla el script de inmediato

El script lanza un error claro en dos situaciones:

- **Las reglas de sustitución referencian `$items.<Type>.<Name>.$id`, pero no se encuentra en el repositorio ningún elemento de los tipos de dependencia.** El despliegue no puede satisfacer el marcador de posición.
- **Una regla referencia un elemento que el script no encuentra por `(Type, Name)`.** El marcador no se resolverá. Causa habitual: una errata en `bulk-parameter.yml`.

En ambos casos el despliegue se detiene antes de enviar ningún elemento.

---

## Requisitos previos y configuración

### 1. Fabric Capacity

Se necesita una *Fabric Capacity* o una capacidad de Power BI Premium para todos los workspaces.

### 2. Workspaces de Fabric

Hacen falta tres workspaces:

- **microsoft-fabric-sdlc-patterns-dev**: conectado a la rama `dev` mediante la integración de Git de Fabric
- **microsoft-fabric-sdlc-patterns-test**: sin conexión a Git, recibe los despliegues mediante la API de importación masiva
- **microsoft-fabric-sdlc-patterns-prod**: sin conexión a Git, recibe los despliegues mediante la API de importación masiva

### 3. Service principal

Cree un service principal para la automatización de CI/CD:

```bash
az ad sp create-for-rbac --name "SPN-Microsoft-Fabric-SDLC-Patterns" \
  --query "{tenantId:tenant, clientId:appId, clientSecret:password}" -o json
```

- Añada el service principal como **colaborador** en los workspaces de Test y Prod (Workspace → Manage access → Add people or groups).
- Colaborador es el rol mínimo necesario según la documentación de la [API Create Item de Fabric](https://learn.microsoft.com/en-us/rest/api/fabric/core/items/create-item).
- **Crítico en la ruta masiva:** todos los tipos de elemento del repositorio deben admitir service principals. La API de importación masiva comprueba esa compatibilidad a nivel de solicitud: un solo tipo no compatible hace fallar la llamada entera. Véase la [tabla comparativa en release-options](fabric-cicd-release-options.md#herramientas-dentro-de-la-opción-3-fabric-cicd-frente-a-las-api-masivas) para el contexto.

> **Importante:** alguien con rol de administrador de Fabric debe habilitar el acceso de service principals a las API de Fabric en el portal de administración, dentro de la configuración de desarrollador, y limitarlo a un grupo de seguridad que contenga únicamente los service principals de CI/CD. Véanse la [configuración de inquilino para desarrolladores](https://learn.microsoft.com/en-us/fabric/admin/service-admin-portal-developer) y las [Consideraciones de gobernanza](fabric-cicd-governance-considerations.md).

### 4. Entornos de GitHub

Cree dos entornos de GitHub en la configuración del repositorio (Settings → Environments):

| Entorno | Reglas de protección |
|---|---|
| `Test` | Ninguna (el despliegue se ejecuta automáticamente al fusionar) |
| `Prod` | Revisores obligatorios y restricción de la rama de despliegue únicamente a `main` |

> **Nota:** el nombre del entorno también es el valor que sustituye a `$environment` en el marcador `active_value_set` de `bulk-parameter.yml`. Por tanto, los nombres de los entornos de GitHub deben coincidir exactamente con los de los conjuntos de valores de la *Variable Library* (`Test`, `Prod`).

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

### 6. Establecer la variable de repositorio `DEPLOY_METHOD`

Para activar la ruta masiva, establezca `DEPLOY_METHOD=bulk` en Settings → Secrets and variables → Actions → Variables. Sin eso, los flujos masivos se omiten y se ejecuta fabric-cicd.

---

## Primer despliegue en un workspace vacío

Al desplegar en un workspace por primera vez, siga estos pasos en orden. Los despliegues posteriores están completamente automatizados: solo el primero requiere intervención manual.

### Paso 1: desencadenar el despliegue

Haga *push* a la rama de destino (`test` o `main`). El flujo de despliegue masivo se activa automáticamente y ejecuta:

- **Fase 1 (si hace falta):** POST del *Lakehouse* y la *Ontology*
- **Fase 2:** sustituye en el resto de elementos los IDs obtenidos en la respuesta de la fase 1 y los envía por POST
- **Tras el despliegue:** PATCH sobre la *VariableLibrary* para establecer el conjunto de valores activo del entorno

### Paso 2: el ETL carga el Lakehouse

El flujo de trabajo de ETL (`etl-test.yml` o `etl-prod.yml`) se activa automáticamente tras un despliegue correcto. Ejecuta el *Notebook* `Import_Patterns_Data`, que crea y carga las tablas Delta (`doctors`, `patients`, `appointments`) en el *Lakehouse*.

### Paso 3: configurar el origen de datos del Graph Model (manual)

La *Ontology* se despliega solo como definición: su Graph Model no tiene enlace a un origen de datos hasta que se configura manualmente.

1. Abra el elemento **Ontology** en la interfaz de Fabric y vaya al **Graph Model**.
2. Seleccione **Get data** para enlazar el Graph Model con las tablas del *Lakehouse*.

### Paso 4: activar la Ontology (solución manual)

Tras configurar el origen de datos, la *Ontology* puede quedarse en *"Setting up your ontology — We are preparing the ontology overview for the first time."* Es un comportamiento conocido de la plataforma Fabric en el primer despliegue.

**Solución alternativa:** seleccione cualquier Entity Type de la *Ontology*, cámbiele el nombre por uno temporal y vuelva a ponerle el original. Eso hace que Fabric termine de inicializar la vista general de la *Ontology*.

### Paso 5: verificar de principio a fin

Confirme que todos los elementos funcionan en el workspace de destino:

- **Lakehouse**: tablas cargadas con datos
- **Ontology**: la vista general carga y se ven los tipos de entidad y las relaciones
- **Variable Library**: el conjunto de valores activo coincide con el entorno de destino (`Test` o `Prod`)
- **Semantic Model**: conectado al *Lakehouse* (puede requerir configurar la conexión manualmente en el primer despliegue)
- **Report**: se representa con datos del *Semantic Model*
- **Data Agent**: referencia la *Ontology* y responde a las consultas

> **Nota:** los pasos 3 y 4 (activación de la *Ontology*) son comportamientos de la plataforma, no específicos de la ruta masiva. La ruta de fabric-cicd requiere los mismos pasos manuales en el primer despliegue.

---

## Problemas habituales y decisiones clave

### El huevo y la gallina de los dos despliegues

La *Variable Library*, el *Semantic Model* y los *Notebooks* referencian el ID del *Lakehouse* de cada entorno, pero el *Lakehouse* no existe en Test ni en Prod hasta que lo crea el primer despliegue. Con la API masiva no hay resolución de esas referencias del lado de la biblioteca: el script debe enviar primero los elementos de dependencia, leer sus IDs de la respuesta y sustituirlos en el resto antes del segundo POST.

**Solución:** [la decisión de los dos despliegues](#la-decisión-de-los-dos-despliegues). La fase 1 envía las dependencias (`DEPENDENCY_TYPES`), el script lee sus IDs de la respuesta y la fase 2 sustituye y envía el resto.

### Compatibilidad con service principals por solicitud

La API de importación masiva exige que **todos** los tipos de elemento de la carga útil admitan service principals. Si uno solo no lo hace, la solicitud entera falla con un error de autorización, sin degradación elegante.

fabric-cicd, en cambio, falla por elemento: un tipo no compatible hace fallar únicamente ese elemento, y el resto del despliegue continúa.

**Solución:** verifique la compatibilidad con service principals de todos los tipos de elemento del repositorio antes de adoptar la ruta masiva. A día de hoy, los 7 tipos de este repositorio (Lakehouse, Ontology, VariableLibrary, Notebook, SemanticModel, Report y DataAgent) admiten service principals y el despliegue funciona de principio a fin. Si un tipo de elemento futuro de Fabric no los admitiera, la ruta masiva no sería utilizable hasta que se añadiera la compatibilidad.

### Sondeo de operaciones de larga duración (LRO)

La API de importación masiva puede devolver:

- **`200 OK`** con el cuerpo completo del resultado (`importItemDefinitionsDetails[]`) en línea: caso síncrono
- **`202 Accepted`** con una cabecera `x-ms-operation-id` y otra `Retry-After`: asíncrono, con sondeo de una operación de larga duración por parte de quien llama

`scripts/deploy_bulk.py` gestiona ambos casos de forma transparente. En el caso asíncrono, sondea `GET /v1/operations/{id}` hasta que la operación llega a `Succeeded`, `Failed` o `Undefined`, y después obtiene `GET /v1/operations/{id}/result` con la misma forma `importItemDefinitionsDetails[]` que el caso síncrono devuelve en línea.

### Acotación de Retry-After

El script acota la cabecera `Retry-After` al intervalo `[5 s, 600 s]` y usa 30 s cuando falta o no se puede interpretar. Sin el límite superior, un valor patológico de `Retry-After` podría provocar una espera más larga que el tiempo de espera global de sondeo (20 minutos), dejándolo sin efecto. Sin la validación de entrada, un valor no entero haría fallar el script con un `ValueError` no controlado.

### El token de portador no se escribe en los registros

Una versión anterior del script emitía `::add-mask::<token>` para registrar una máscara en los registros del flujo de trabajo. Esa misma línea escribía el token en texto claro en la salida estándar, anulando el propósito de la máscara (el ejecutor solo oculta la salida posterior). El script actual nunca imprime el token. GitHub enmascara automáticamente el secreto del service principal porque procede de `secrets.AZURE_CLIENT_SECRET`.

### `bulk-parameter.yml` se excluye de la carga útil

El script incluye `bulk-parameter.yml`, `parameter.yml` y `.gitkeep` en `EXCLUDED_FILES` para que nunca se envíen a Fabric como parte de la solicitud masiva. La regla estructural «los archivos en la raíz de `repository_directory` no son definiciones de elementos» ya los excluye, pero la lista explícita documenta la intención.

### Peculiaridad de `workflow_run`: las reejecuciones usan el archivo congelado

Al reejecutar un ETL desencadenado por `workflow_run` se usa el archivo del flujo de trabajo congelado en el momento en que se disparó el desencadenador, no el de la rama predeterminada actual. Si una corrección del archivo llega a `main` después de ese momento, ni el reintento automático ni `gh run rerun` la recogen. Para recuperarse de un fallo transitorio o de una corrección del archivo, conviene usar el desencadenador manual `workflow_dispatch` añadido a `etl-test.yml` y `etl-prod.yml`.

### `?beta=true` es necesario hoy

La URL del extremo masivo es actualmente `POST /v1/workspaces/{ws}/items/bulkImportDefinitions?beta=true`. Cuando la API salga de la versión preliminar, ese parámetro dejará de ser necesario.

### La URL del tutorial de Microsoft es incorrecta

El [tutorial de importación masiva](https://learn.microsoft.com/en-us/fabric/cicd/tutorial-bulkapi-cicd) de Microsoft Learn usa `/importItemDefinitions` (en singular), y ese extremo devuelve `404`. La ruta correcta es `/items/bulkImportDefinitions`, según la [página de referencia de la API](https://learn.microsoft.com/en-us/rest/api/fabric/core/items/bulk-import-item-definitions). Verificado contra un workspace real.

---

## Ampliar la implementación masiva

El script está estructurado para que los casos de ampliación habituales queden localizados. Esta es la forma de cada uno.

### Añadir una regla de sustitución

Edite `data/fabric/bulk-parameter.yml`:

```yaml
substitutions:
  # ... existing rules ...
  - find: "<old-string>"
    replace_with: "<new-string-or-placeholder>"
    item_types: [Notebook, SemanticModel]
```

No hace falta cambiar código. La regla nueva se recoge automáticamente en el siguiente despliegue.

Si la regla nueva referencia `$items.<Type>.<Name>.$id` para un tipo de elemento nuevo, amplíe también `DEPENDENCY_TYPES` en `scripts/deploy_bulk.py` para que ese tipo se despliegue en la fase 1.

### Añadir un tipo de marcador de posición

Para añadir, por ejemplo, `$secrets.<name>` que se resuelva a un secreto de CI, modifique `scripts/deploy_bulk.py`:

1. Añada una constante `_SECRETS_PLACEHOLDER = re.compile(r"\$secrets\.([^.\s]+)")`.
2. En `resolve_dynamic_value()`, añada una llamada a `_SECRETS_PLACEHOLDER.sub(...)`.
3. Añada la variable de entorno correspondiente (por ejemplo, `BULK_SECRETS_JSON`) y léala en `main()`.
4. Añada pruebas para el nuevo resolutor.

El patrón sigue lo que ya hacen `$workspace.$id` y `$items.<Type>.<Name>.$id`.

### Añadir un tipo de dependencia

Si un tipo de elemento nuevo pasa a ser destino de sustituciones `$items.<Type>.*` (por ejemplo, un *Warehouse* nuevo del que dependan otros elementos):

```python
DEPENDENCY_TYPES = ("Lakehouse", "Ontology", "Warehouse")
```

Ese es el único cambio de código. La fase 1 empezará a incluir el tipo nuevo y las sustituciones de la fase 2 resolverán sus IDs.

### Añadir un enlace posterior al despliegue

La activación del conjunto de valores de la *VariableLibrary* es el ejemplo existente. Para añadir otro (por ejemplo, crear un acceso directo de *Lakehouse* tras el despliegue):

1. Añada una función auxiliar, por ejemplo `create_shortcut(workspace_id, lakehouse_id, shortcut_config, headers)`, que envuelva la llamada correspondiente a la API REST de Fabric.
2. Añada el bloque de configuración correspondiente a `BulkConfig` (por ejemplo, `shortcuts: tuple[ShortcutConfig, ...]`).
3. Amplíe `load_bulk_config()` para interpretar el bloque nuevo de `bulk-parameter.yml`.
4. Conecte el enlace en `main()` después del despliegue, junto a la activación del conjunto de valores existente.
5. Añada pruebas unitarias para la función auxiliar y para la interpretación de la configuración.

El patrón es deliberadamente repetible: cada paso posterior al despliegue es «bloque de configuración en YAML → campo de la dataclass → función auxiliar → punto de llamada en `main()`».

### Añadir un bloque de configuración masiva

La configuración incluida tiene `substitutions` y `variable_library`. Para añadir un tercer bloque (por ejemplo, `shortcuts`, como arriba):

1. Añada una `@dataclass(frozen=True)` para el contenido del bloque (por ejemplo, `ShortcutConfig`).
2. Añádala como campo de `BulkConfig` con un valor predeterminado razonable.
3. Amplíe `load_bulk_config()` para interpretar el bloque nuevo, con mensajes de error explícitos ante entradas mal formadas.
4. Añada pruebas que cubran el caso correcto, el uso del valor predeterminado cuando falta el bloque y cada error documentado.

La `VariableLibraryConfig` existente es un ejemplo funcional.

---

## Limitaciones no resueltas

La ruta masiva de este repositorio implementa la sustitución y la activación del conjunto de valores, pero NO resuelve lo siguiente. Quien elija la ruta masiva en su propio proyecto tendrá que implementarlo o asumir su ausencia.

| Limitación | Qué falta | Solución alternativa, si se necesita |
|---|---|---|
| **Limpieza de huérfanos** | La API de importación masiva solo admite crear y actualizar, no eliminar. Los elementos que se quitan del repositorio permanecen en el workspace. | Mantener un bucle `DELETE` por elemento después del POST masivo. |
| **`key_value_replace`** | La sustitución por clave basada en JSONPath de fabric-cicd (por ejemplo, IDs de conexión en el JSON de un *pipeline*). | Ampliar `apply_substitutions()` para admitir un paso de sustitución estilo JSONPath además de la búsqueda literal. |
| **Sustitución de `spark_pool`** | El intercambio de grupos de Spark por entorno de fabric-cicd. | Añadir un bloque de configuración y una llamada a la API posterior al despliegue (similar a la activación del conjunto de valores). |
| **`semantic_model_binding`** | El enlace automático de *Semantic Models* a conexiones de origen de datos de fabric-cicd. | Añadir una llamada a la API posterior al despliegue contra el *Semantic Model*. |
| **Degradación elegante por elemento con service principals** | La ruta masiva hace fallar la solicitud entera si algún tipo de elemento no admite service principals. | Comprobación previa: listar los tipos de elemento de la solicitud y validarlos contra un conjunto conocido de tipos compatibles. |
| **Gestión de varias VariableLibrary** | `find_variable_library_id()` lanza un error si hay más de una *VariableLibrary* (el paso de activación apunta a una sola). | Rediseñar el flujo de activación para que acepte configuración por biblioteca e itere. |
| **Filtro `item_type_in_scope`** | El script despliega todo lo que hay en `repository_directory`. No hay forma de acotar un despliegue a un subconjunto. | Añadir una variable de entorno que se lea en `main()` y filtrar las partes antes del POST. |

Son no-objetivos deliberados de este repositorio de demostración. Pueden añadirse de forma incremental con los [patrones de ampliación](#ampliar-la-implementación-masiva) anteriores.

---

## Referencias

- [fabric-cicd-release-options.md](fabric-cicd-release-options.md) — Documento de estrategia con la comparación entre fabric-cicd y las API masivas
- [fabric-hybrid-cicd-guide.md](fabric-hybrid-cicd-guide.md) — Guía de implementación de la ruta de fabric-cicd
- [fabric-cicd-governance-considerations.md](fabric-cicd-governance-considerations.md) — Identidad, RBAC, protección de ramas y puertas de aprobación
- [API Bulk Import Item Definitions de Fabric (versión preliminar)](https://learn.microsoft.com/en-us/rest/api/fabric/core/items/bulk-import-item-definitions) — Referencia del extremo *(solo en inglés)*
- [Operaciones de larga duración de Fabric](https://learn.microsoft.com/en-us/rest/api/fabric/articles/long-running-operation) — Semántica de `?async=true` y patrón de sondeo *(solo en inglés)*
- [Update Variable Library de Fabric](https://learn.microsoft.com/en-us/rest/api/fabric/variablelibrary/items/update-variable-library) — Extremo PATCH que usa la activación del conjunto de valores *(solo en inglés)*
- [Tutorial de importación masiva de Microsoft](https://learn.microsoft.com/en-us/fabric/cicd/tutorial-bulkapi-cicd) — Recorrido de Microsoft (obsérvese la discrepancia de URL señalada en [Problemas habituales](#la-url-del-tutorial-de-microsoft-es-incorrecta)) *(solo en inglés)*
- [API Create Item de Fabric — Permisos](https://learn.microsoft.com/en-us/rest/api/fabric/core/items/create-item) — Requisito del rol de colaborador *(solo en inglés)*
- [Flujos de trabajo reutilizables de GitHub](https://docs.github.com/en/actions/sharing-automations/reusing-workflows) — `workflow_call`, entradas y secretos *(solo en inglés)*

---

## Sobre esta traducción

Este documento es una traducción de [fabric-bulk-cicd-guide.md](../../fabric-bulk-cicd-guide.md). La versión en inglés es la fuente autorizada y puede estar más actualizada.

La terminología sigue [`GLOSARIO.md`](GLOSARIO.md) y [`GUIA-DE-ESTILO.md`](GUIA-DE-ESTILO.md). Para revisar esta traducción, véase [`REVISION.md`](REVISION.md).

**Los enlaces a documentación externa apuntan a la versión en inglés.** Los motivos están en el apartado «Sobre esta traducción» del [README en español](README.md).

Los errores pueden comunicarse abriendo una incidencia e indicando el idioma. Si el error existe también en el original en inglés, **debe corregirse primero allí**: véase [`TRANSLATION.md`](../../TRANSLATION.md).
