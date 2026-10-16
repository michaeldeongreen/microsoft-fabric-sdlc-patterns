[English](../../fabric-release-process.md) | **Español**

<!-- source: fabric-release-process.md @ f7f949d | translated: 2026-10-15 -->

> La versión en inglés es la fuente autorizada. Si existe alguna discrepancia,
> [el original en inglés](../../fabric-release-process.md) tiene precedencia.

# Proceso de lanzamiento

Esta guía explica cómo un cambio revisado pasa de Dev a Test y después a la
rama `main` y a Prod. Se aplica a los cuatro métodos de despliegue incluidos
en este repositorio.

Consulte:

- [Configuración](SETUP.md), para configurar un fork nuevo y sus entornos.
- [Proceso de desarrollo](fabric-development-process.md), para Branch Out,
  las pruebas de feature, la vuelta a Dev y la actualización manual de Dev.
- Las guías de cada método, para el comportamiento específico del publicador:
  [fabric-cicd sin publicación masiva](fabric-hybrid-cicd-guide.md),
  [adaptadores de Deployment Plan](fabric-deployment-plan-guide.md) y
  [REST directo masivo](fabric-bulk-cicd-guide.md).

## Correspondencia entre ramas, workspaces y entornos

| Rama de Git | Etapa de Fabric | Entorno de GitHub | Cómo llegan las definiciones |
|---|---|---|---|
| `dev` | Workspace Dev | `Dev` | Un operador designado del workspace Dev selecciona **Update all** |
| `test` | Workspace Test | `Test` | El método de despliegue seleccionado de GitHub Actions |
| `main` | Workspace Prod | `Prod` | El método de despliegue seleccionado de GitHub Actions |

La rama `main` tiene Prod como destino; la rama en sí no es un entorno de
Fabric. Solo Dev está conectado a Git. Test y Prod reciben las publicaciones
mediante API.

## Quién es responsable

| Actor | Responsabilidad |
|---|---|
| Administrador del repositorio de GitHub | Reglas, entornos, secretos y variables, selección del método de despliegue, ciclo de vida del PAT e inicio manual del aprovisionamiento de Dev |
| Operador del workspace Dev | Actualización de Dev desde Git, inspección de vinculaciones y ejecución manual del DataPipeline |
| GitHub Actions | Ejecuta el contenido revisado para el lanzamiento y hace cumplir el orden de dependencias entre trabajos |
| Service principal de despliegue | Crea o reutiliza y verifica las conexiones de Test/Prod, administra sus ACL, publica definiciones y envía trabajos de Fabric |
| PAT para las variables de los entornos de GitHub | Lee y crea las dos variables de ID de conexión durante las comprobaciones previas y la persistencia del lanzamiento |
| Workspace Identity de Fabric | Autentica las actividades de Notebook y de actualización del Semantic Model en tiempo de ejecución |
| Grupo de administradores de conexiones | Recibe acceso Owner verificado a las dos conexiones de la etapa |
| Responsable de verificación del lanzamiento y revisor de Prod | Acepta las evidencias de Test y autoriza Prod cuando se haya configurado la protección del entorno |

En un fork de ejemplo, una persona puede desempeñar varios roles humanos.
[Configuración](SETUP.md) define el modelo completo de administradores y
requisitos previos; esta tabla describe la operación del lanzamiento.

GitHub Actions es el orquestador, no una identidad. Sus llamadas a Fabric usan
el *Service principal* de despliegue. Sus llamadas a las variables de los
entornos de GitHub usan el PAT. Las actividades de Fabric usan la Workspace
Identity del workspace de destino.

## Ciclo de vida de un vistazo

1. Se realiza Branch Out desde Dev. Un administrador del workspace de feature
   crea la Workspace Identity y las conexiones; el desarrollador intercambia
   las referencias y valida el workspace.
2. Antes del PR, se restauran las referencias canónicas de Dev y se supera
   la comprobación de referencias para el PR.
3. Tras el *Merge* del PR de feature a `dev`, el operador designado del
   workspace Dev actualiza desde Git y ejecuta
   `Patterns_Load_Validate_And_Refresh` manualmente.
4. Se fusiona un PR revisado de `dev` a `test`. El trabajo seleccionado de
   Test crea o reutiliza y verifica sus dos conexiones, publica las
   definiciones y ejecuta el DataPipeline de Fabric de la misma revisión.
5. El equipo valida Test. Que el trabajo de publicación termine correctamente
   es necesario, pero no sustituye la aceptación de la carga de trabajo, el
   Semantic Model, los informes y los consumidores.
6. Se fusiona un PR revisado de `test` a `main`. El trabajo seleccionado de
   Prod usa la misma secuencia técnica, con la configuración específica de
   Prod y las protecciones que se hayan configurado.

## Trabajo de feature y entrega a Dev

El flujo de feature completo se describe en el
[Proceso de desarrollo](fabric-development-process.md). La entrega al proceso
de lanzamiento es:

1. Ejecute [`/swap-to-dev`](../../.github/skills/swap-to-dev/SKILL.md). CLI:
   `python scripts\workspace_swap.py --swap-to-dev`.
2. Revise los cambios exactos. La skill comprueba automáticamente las
   referencias para el PR; con la CLI también debe ejecutarse
   `python scripts\workspace_swap.py --check-ready`.
3. Haga *commit* y push de la feature branch con las referencias restauradas.
4. Abra un PR a `dev`.
5. Exija `Check for non-dev IDs in Fabric items` y `Run unit tests`.
6. Tras el merge, actualice Dev manualmente desde Fabric Git.
7. Ejecute el DataPipeline de Fabric de Dev y revise sus resultados.

No hay publicación en Dev activada por un push ni ejecución automática de su
DataPipeline. El aprovisionamiento de conexiones de Dev también es una acción
manual de configuración independiente.

## De Dev a Test

Antes de abrir el PR de promoción:

- Dev debe contener las definiciones revisadas que realmente se hayan
  actualizado y probado en el workspace Dev.
- `DEPLOY_METHOD` no debe estar definido si se usa el publicador
  predeterminado, o debe tener un valor admitido.
- Deben estar configurados previamente el workspace Test, su Workspace
  Identity, los permisos sobre los recursos, el entorno de GitHub, las
  credenciales de despliegue, el PAT y el grupo de administradores de
  conexiones.
- Ningún otro lanzamiento de Test o Prod debe estar usando un selector o una
  configuración compartida que se esté modificando.

Abra un PR de `dev` a `test`. GitHub ejecuta:

- `Enforce promotion path`
- `Run unit tests`

Tras el merge, los cuatro flujos de trabajo que invocan el despliegue de Test
pueden aparecer en Actions, pero solo el que coincide con `DEPLOY_METHOD`
ejecuta su trabajo de despliegue. Es normal que los demás muestren trabajos
omitidos.

El trabajo seleccionado realiza esta secuencia:

1. Valida la etapa y la referencia seleccionadas, la configuración necesaria,
   el acceso al entorno de GitHub y los IDs de conexión guardados, si existen.
2. Se autentica en Fabric con el Service principal de despliegue.
3. Valida la Workspace Identity de Test, que debe existir previamente.
4. Crea o reutiliza las conexiones de Notebook y de Power BI datasets para la
   actualización del Semantic Model, con autenticación Workspace Identity.
5. Concede al grupo configurado de administradores de conexiones el rol
   Owner en ambas conexiones, o lo eleva a ese rol, y vuelve a leer la
   asignación para verificarla.
6. Crea las variables de entorno `NOTEBOOK_CONNECTION_ID` y
   `SEMANTIC_MODEL_REFRESH_CONNECTION_ID` que falten y después las verifica.
   Un valor existente distinto provoca un error y nunca se sobrescribe.
7. Pasa directamente al publicador los IDs resueltos en la ejecución actual.
   El publicador vuelve a validar las dos conexiones y las usa en modo
   `existing`/`WorkspaceIdentity`.
8. Publica con el método de despliegue seleccionado.
9. Si la publicación termina correctamente, inicia el DataPipeline de Fabric
   `Patterns_Load_Validate_And_Refresh` de la misma revisión y consulta su
   estado hasta que termina.

El trabajo de despliegue completo no es de solo lectura: su preparación de
conexiones puede crearlas, cambiar asignaciones de roles de conexión y crear
variables de los entornos de GitHub. Solo el subpaso de publicación trata las
conexiones como dependencias existentes de solo lectura.

## De Test a `main` y Prod

Abra un PR de `test` a `main` solo cuando la versión candidata de Test tenga
las evidencias técnicas y de negocio necesarias. Antes del merge se ejecutan
las mismas comprobaciones de ruta de promoción y pruebas unitarias.

El lanzamiento de Prod sigue el mismo contrato técnico que Test:

1. Comprobaciones previas específicas de Prod
2. Creación o reutilización de las conexiones de Prod y verificación del rol
   Owner
3. Persistencia de los IDs de Prod solo cuando las variables no existen
4. Método de publicación seleccionado
5. DataPipeline de Fabric de Prod de la misma revisión

Cambian las ramas de origen y destino, el entorno de GitHub, el workspace, la
Workspace Identity, las conexiones, los secretos, la etiqueta de ejecución y
los revisores o las reglas de ramas de despliegue de Prod que se hayan
configurado.

El repositorio no crea la protección de los entornos de GitHub. Configure el
revisor de Prod y la política de ramas de despliegue antes de la primera
promoción a Prod. Una recomendación no debe describirse como un control ya
configurado.

## Ciclo de vida de las conexiones por etapa

| Etapa | Quién crea la Workspace Identity y concede acceso a los recursos | Quién crea las conexiones | Cómo llegan las definiciones |
|---|---|---|---|
| Feature | Un administrador del workspace de Fabric | Un administrador del workspace de feature o de conexiones crea las dos; la preparación solo las valida | Fabric Git en el workspace de Branch Out |
| Dev | Un administrador del workspace de Fabric | Un administrador del repositorio de GitHub ejecuta manualmente **Provision Fabric Connections** | El operador designado del workspace Dev selecciona **Update all** |
| Test | Un administrador del workspace de Fabric | El trabajo de despliegue seleccionado de Test crea o reutiliza y verifica las dos conexiones | El publicador de API seleccionado |
| Prod | Un administrador del workspace de Fabric | El trabajo de despliegue seleccionado de Prod crea o reutiliza y verifica las dos conexiones | El publicador de API seleccionado |

La creación o reutilización y verificación automática de conexiones no:

- crea ni aprovisiona una Workspace Identity;
- asigna permisos de workspace, Semantic Model ni OneLake;
- crea grupos ni administra su pertenencia;
- cambia la configuración del inquilino ni el acceso condicional;
- crea credenciales;
- aprueba un lanzamiento; ni
- elimina conexiones heredadas.

Las ejecuciones manuales de **Provision Fabric Connections** para Test/Prod
son herramientas de recuperación, migración o diagnóstico. No son necesarias
en el recorrido normal del primer lanzamiento.

## Flujos de trabajo de GitHub Actions

### Qué activa cada ejecución

| Evento | Resultado |
|---|---|
| PR a `dev` | Comprobación de referencias de Dev y pruebas unitarias |
| PR a `test` o `main` | Cumplimiento de la ruta de promoción y pruebas unitarias |
| Push a `test` | Los flujos de Test evalúan `DEPLOY_METHOD`; el método seleccionado despliega y después ejecuta el DataPipeline |
| Push a `main` | Los flujos de Prod evalúan `DEPLOY_METHOD`; el método seleccionado despliega y después ejecuta el DataPipeline |
| Inicio manual para Test | Debe usar la rama `test` |
| Inicio manual para Prod | Debe usar la rama `main` y las protecciones configuradas de Prod |
| Cambio únicamente de `DEPLOY_METHOD` | No hay despliegue hasta que se produce un push que cumpla los filtros o se inicia una ejecución manual |
| Cambio solo de documentación | No hay despliegue salvo que también cambie una ruta de implementación incluida en los filtros |

Un valor desconocido y no vacío de `DEPLOY_METHOD` no selecciona ningún
trabajo de despliegue. No use ese comportamiento como un control de lanzamiento
sin documentar.

### Comprobaciones de las pull requests

| Flujo de trabajo | Trigger | Propósito |
|---|---|---|
| [check-pr-ready.yml](../../.github/workflows/check-pr-ready.yml) | PR a `dev` | Exige referencias canónicas de Dev y ausencia de conjuntos de valores de feature residuales |
| [run-tests.yml](../../.github/workflows/run-tests.yml) | Todos los PR | Ejecuta la suite de pytest |
| [enforce-promotion-path.yml](../../.github/workflows/enforce-promotion-path.yml) | PR a `test` o `main` | Exige `dev` a `test` y `test` a `main` |

Las reglas deben exigir estas comprobaciones. El YAML de los flujos de trabajo
no impide que un administrador fusione sin una regla de rama configurada.

### Flujos de trabajo de despliegue

| `DEPLOY_METHOD` | Flujo que invoca el despliegue de Test | Flujo que invoca el despliegue de Prod |
|---|---|---|
| Sin definir o `fabric-cicd` | [deploy-test.yml](../../.github/workflows/deploy-test.yml) | [deploy-prod.yml](../../.github/workflows/deploy-prod.yml) |
| `fabric-cicd-plan` | [deploy-test-fabric-cicd-plan.yml](../../.github/workflows/deploy-test-fabric-cicd-plan.yml) | [deploy-prod-fabric-cicd-plan.yml](../../.github/workflows/deploy-prod-fabric-cicd-plan.yml) |
| `fabric-cicd-bulk` | [deploy-test-fabric-cicd-bulk.yml](../../.github/workflows/deploy-test-fabric-cicd-bulk.yml) | [deploy-prod-fabric-cicd-bulk.yml](../../.github/workflows/deploy-prod-fabric-cicd-bulk.yml) |
| `bulk` | [deploy-test-bulk.yml](../../.github/workflows/deploy-test-bulk.yml) | [deploy-prod-bulk.yml](../../.github/workflows/deploy-prod-bulk.yml) |

Los filtros de los flujos que invocan el despliegue incluyen su publicador,
los módulos compartidos de conexiones y preparación, las definiciones de
Fabric, las reglas de parámetros y los archivos de flujo de trabajo. Los
flujos de plan también incluyen sus lectores de planes y las rutas
configuradas para ellos.

### Plantillas reutilizables invocadas mediante `workflow_call`

| Plantilla | Script de ejecución | Función específica del publicador |
|---|---|---|
| [reusable-deploy-fabric-cicd.yml](../../.github/workflows/reusable-deploy-fabric-cicd.yml) | [deploy_fabric_cicd_non_bulk.py](../../scripts/deploy_fabric_cicd_non_bulk.py) | Fases predeterminadas sin publicación masiva y limpieza de elementos huérfanos aptos |
| [reusable-deploy-fabric-cicd-plan.yml](../../.github/workflows/reusable-deploy-fabric-cicd-plan.yml) | [deploy_fabric_cicd_non_bulk_plan.py](../../scripts/deploy_fabric_cicd_non_bulk_plan.py) | Grupos secuenciales del plan interpretado por el adaptador, elementos restantes y limpieza de huérfanos aptos |
| [reusable-deploy-fabric-cicd-bulk.yml](../../.github/workflows/reusable-deploy-fabric-cicd-bulk.yml) | [deploy_fabric_cicd_bulk.py](../../scripts/deploy_fabric_cicd_bulk.py) | Selecciones masivas estrictas agrupadas y limpieza de huérfanos aptos |
| [reusable-deploy-bulk.yml](../../.github/workflows/reusable-deploy-bulk.yml) | [deploy_fabric_rest_bulk.py](../../scripts/deploy_fabric_rest_bulk.py) | Cargas útiles REST directas, consulta de estado y activación de conjuntos de valores; sin limpieza de huérfanos |
| [reusable-fabric-etl.yml](../../.github/workflows/reusable-fabric-etl.yml) | [run_fabric_etl.py](../../scripts/run_fabric_etl.py) | Resuelve, inicia y consulta el estado de un único trabajo de Fabric |

### Por qué se usan flujos de trabajo reutilizables y no acciones compuestas

Las plantillas reutilizables de despliegue definen el entorno de GitHub de
destino. Así se mantienen los secretos del entorno, los controles opcionales
de revisión, la concurrencia, las comprobaciones previas de conexiones, la
publicación y el DataPipeline dependiente en un único grafo de trabajos
visible. Las acciones compuestas no sustituyen los controles de entorno y
dependencias entre trabajos definidos a nivel de flujo de trabajo.

### Flujos de trabajo que invocan el ETL y traspaso de control

| Flujo de trabajo | Trigger | Propósito |
|---|---|---|
| Trabajo `run-etl` del flujo de despliegue seleccionado | Finalización con éxito del trabajo de despliegue, mediante `needs` | Ejecuta el DataPipeline desde la misma revisión de la rama |
| [etl-test.yml](../../.github/workflows/etl-test.yml) | Manual, rama `test` | Recuperación de Test sin volver a publicar |
| [etl-prod.yml](../../.github/workflows/etl-prod.yml) | Manual, rama `main` | Recuperación de Prod con su entorno y las protecciones configuradas |

El traspaso automático no usa un receptor `workflow_run` cargado desde otra
rama. La publicación y el ETL permanecen en el mismo grafo y la misma revisión
del flujo de trabajo. La concurrencia por etapa cubre ambos trabajos. Si la
publicación falla, el ETL no se ejecuta.

### Actualización del Semantic Model posterior al ETL

El trabajo reutilizable de ETL inicia `Patterns_Load_Validate_And_Refresh`
como DataPipeline de Fabric y espera a su estado final:

1. `Import_Patterns_Data` escribe las tablas Delta del ejemplo.
2. `Validate_Patterns_Data` realiza comprobaciones de solo lectura sobre el
   esquema, las claves, las referencias, los tipos de fecha del origen y el
   mínimo de pacientes configurado.
3. La actualización nativa del Semantic Model solo se ejecuta si la
   validación termina correctamente, con ejecución transaccional y espera
   hasta la finalización habilitadas.

El DataPipeline de Fabric es el único responsable de la actualización.
GitHub no realiza una segunda actualización del Semantic Model.

`minimum_patient_count` es un Integer positivo que procede del conjunto de
valores activo de `Patterns_Variables`. `run_label` es un String independiente
que proporciona el flujo que invoca la ejecución cuando se requiere. Una
entrada no válida no se sustituye por un valor predeterminado que simule un
resultado correcto.

El Service principal de despliegue envía el trabajo de DataPipeline. Sus
actividades de Notebook y de actualización se autentican mediante las
conexiones de Workspace Identity de la etapa. Un despliegue correcto no
demuestra la propiedad del Semantic Model, el acceso al origen, los resultados
DAX, la visualización de informes ni el acceso de los consumidores.

## Límites ante fallos y reintentos

| Punto de fallo | Comportamiento y respuesta segura |
|---|---|
| Comprobaciones previas de etapa/referencia o configuración | Falla antes de escribir en Fabric; corrija la rama seleccionada, el entorno, los secretos o las variables |
| Creación o reutilización y verificación de conexiones | Puede dejar una conexión correctamente creada o un rol verificado; corrija el error y vuelva a ejecutar, ya que se concilian los nombres y los IDs |
| Persistencia de IDs | Nunca sobrescribe un valor existente distinto; revise el recurso previsto antes de eliminar o cambiar una variable |
| Publicación | El ETL no se inicia; inspeccione el resultado por elemento del publicador seleccionado |
| Fallo al iniciar el DataPipeline o finalización con error | Las definiciones ya están publicadas; inspeccione la ejecución exacta de Fabric y los diagnósticos de las actividades |
| Se agota el tiempo de espera de GitHub al consultar el estado | No cancela el trabajo de Fabric; inspeccione Fabric antes de reintentar |
| Recuperación manual del ETL | Usa la revisión actual de la rama y las definiciones publicadas existentes; no repara una publicación fallida |

No vuelva a ejecutar una revisión antigua para probar un flujo de trabajo más
reciente. Si se creó una conexión antes de que fallara un paso posterior,
reutilícela y verifíquela en lugar de crear otro recurso con un nombre similar.

## Estado de la verificación

La tabla distingue la implementación versionada de las evidencias de
ejecuciones reales.

| Ruta | Contrato versionado | Evidencia de ejecución real para esta revisión |
|---|---|---|
| `fabric-cicd` predeterminado, Test | Preparación de conexiones, tres fases de publicación y DataPipeline de la misma revisión | Verificado el 2026-10-14 mediante la [ejecución 38581072000](https://github.com/michaeldeongreen/microsoft-fabric-sdlc-patterns/actions/runs/38581072000) |
| `fabric-cicd-plan`, Test | Misma preparación de conexiones, grupos secuenciales del plan y DataPipeline de la misma revisión | Sin verificar mediante una ejecución real |
| `fabric-cicd-bulk`, Test | Misma preparación de conexiones, publicación masiva estricta agrupada y DataPipeline de la misma revisión | Sin verificar mediante una ejecución real |
| REST directo `bulk`, Test | Misma preparación de conexiones, tres lotes REST y DataPipeline de la misma revisión | Sin verificar mediante una ejecución real |
| Cualquier ruta de Prod | Equivalente de su ruta de Test con configuración específica de Prod | Sin verificar mediante una ejecución real |
| Revisión actual de Branch Out de feature | Conexiones creadas por una persona, preparación, intercambio, actualización desde Fabric Git y DataPipeline manual | Sin verificar mediante un ciclo completo de la revisión actual |

La ejecución `38581072000` completó las comprobaciones previas de GitHub, la
creación o reutilización y verificación de conexiones de Workspace Identity,
la verificación del rol Owner del grupo de administradores de conexiones, la
persistencia de IDs, la publicación predeterminada y el DataPipeline de Fabric
de la misma revisión. No certifica los tres métodos alternativos, Prod, el
comportamiento con recursos nuevos frente a su reutilización ni la aceptación
del Semantic Model, los informes y los consumidores de cada carga de trabajo.

## Evidencias del lanzamiento

Antes de la promoción a Prod, conserve evidencias que identifiquen la revisión
candidata y el destino:

- comprobaciones y revisiones obligatorias de PR;
- `DEPLOY_METHOD` seleccionado;
- URL de las ejecuciones del despliegue de Test y del DataPipeline;
- resultados de publicación por elemento;
- conjunto de valores activo de Variable Library y comprobaciones de
  vinculaciones físicas;
- resultados esperados de las tablas, el Semantic Model, los informes,
  Ontology y Data Agent;
- propiedad del Semantic Model, acceso al origen y comprobaciones de los
  consumidores;
- excepciones aceptadas y sus responsables; y
- un punto de recuperación o un plan de corrección mediante una nueva
  versión.

Véanse los
[Controles de calidad y de lanzamiento](fabric-cicd-quality-gates-and-release-controls.md)
para una base de controles más amplia y las
[Consideraciones de gobernanza](fabric-cicd-governance-considerations.md) para
los límites de identidad y aprobación.

---

*Este documento es una traducción de
[fabric-release-process.md](../../fabric-release-process.md). El original en
inglés es la fuente autorizada. Los errores pueden comunicarse mediante una
incidencia, indicando el idioma.*

*Los enlaces a documentación externa apuntan al inglés para conservar la
referencia y la terminología de la interfaz. Si se prefiere otro idioma, puede
cambiarse desde el selector de idioma del sitio de destino.*
