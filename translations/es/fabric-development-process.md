[English](../../fabric-development-process.md) | **Español**

<!-- source: fabric-development-process.md @ f7f949d | translated: 2026-10-15 -->

> 📄 **La versión en inglés de este documento es la de referencia.** En caso de discrepancia, [el original en inglés](../../fabric-development-process.md) tiene precedencia.

# Proceso de desarrollo

Esta guía describe el flujo de desarrollo desde Branch Out en Dev hasta el traspaso de los cambios de feature a Dev. La promoción de Dev a Test y de Test a `main`/Prod se documenta en el [Proceso de lanzamiento](fabric-release-process.md).

Este repositorio usa workspaces de Branch Out conectados a Git para desarrollar *features*. No publica en ellos mediante fabric-cicd.

## El flujo de desarrollo

El ciclo habitual con asistencia de Copilot utiliza dos *skills*:

> Después de Branch Out: [`/swap-to-feature`](../../.github/skills/swap-to-feature/SKILL.md); antes del *pull request* (PR) a Dev: [`/swap-to-dev`](../../.github/skills/swap-to-dev/SKILL.md).

Sin Copilot, se sigue el flujo de [CLI independiente](#cli-independiente).

El recorrido completo es el siguiente:

1. Se parte de un workspace de Dev actualizado y de la rama `dev` al día.
2. Se hace Branch Out para crear una *feature branch* y su workspace.
3. Quien administra el workspace crea la *Workspace Identity* de feature y dos conexiones con autenticación mediante Workspace Identity.
4. Se registran los GUID del workspace y de las conexiones en el `.env` de la persona que desarrolla.
5. Se ejecuta `/swap-to-feature`. La skill valida los recursos existentes, descubre los IDs del Lakehouse y del modelo de feature y reescribe las referencias físicas locales.
6. Se hace *commit* y *push*, se actualiza el workspace de feature desde Git, se activa su conjunto de valores de Variable Library y se realizan las pruebas.
7. Se ejecuta `/swap-to-dev`. La skill restaura las referencias canónicas de Dev sin conexión y ejecuta las comprobaciones de preparación.
8. Se hace commit y push y se abre el PR a `dev`.
9. Tras el *Merge* del PR, la persona designada para operar el workspace de Dev selecciona **Update all** y ejecuta manualmente el Data Pipeline de Fabric de Dev.

Ninguna de las dos skills hace commit o push, actualiza Fabric, activa un conjunto de valores ni ejecuta el Data Pipeline.

## Requisitos previos

Para desarrollar se necesita:

- un clon local con Python 3.10 o posterior y las dependencias de desarrollo;
- una credencial propia para GitHub y la integración de Git de Fabric;
- acceso mediante Azure CLI al inquilino aprobado para validar los recursos de feature;
- permiso para hacer Branch Out y crear o utilizar el workspace de feature;
- el rol Contributor o los permisos necesarios sobre los elementos del workspace de feature;
- una Workspace Identity de feature con los accesos necesarios al workspace y a los recursos;
- acceso User a las conexiones de feature, si las ha creado otra persona.

Quien administra el workspace de feature necesita permiso para crear la Workspace Identity y sus conexiones. Quienes desarrollan no necesitan las credenciales del *Service principal* de despliegue ni el PAT utilizado para las variables de los entornos de GitHub.

## 1. Hacer Branch Out desde Dev

Se utiliza la [operación Branch out](https://learn.microsoft.com/en-us/fabric/cicd/git-integration/branched-workspace#branch-out-operation) actual de Fabric:

1. Confirme que Dev está actualizado desde Git y que el workspace no contiene cambios pendientes.
2. En el panel **Source control** de Dev, seleccione **Branch out**.
3. Cree una feature branch a partir de `dev` y un workspace dedicado.
4. Incluya todos los elementos del repositorio para este flujo. No utilice la creación selectiva de ramas sin haber revisado todas las dependencias.
5. No seleccione un Deployment Plan nativo para la operación de creación de la rama. El plan versionado en este repositorio lo leen los adaptadores opcionales de publicación por API; no es el mecanismo de Branch Out.
6. Revise la advertencia relativa a los workspaces de destino existentes: pueden eliminarse los elementos sin confirmar.
7. Complete Branch Out y espere a que el workspace de feature termine de sincronizarse.

El workspace queda conectado por Git a la feature branch. La sincronización copia las definiciones compatibles, pero no crea la Workspace Identity de feature, las conexiones, los permisos ni la asignación de Fabric Capacity.

Antes de modificar la configuración del workspace o de utilizar uno existente, deben revisarse las [limitaciones actuales de Branch Out](https://learn.microsoft.com/en-us/fabric/cicd/git-integration/branched-workspace#branching-out-limitations).

## 2. Crear las conexiones de ejecución de feature

Este paso corresponde a una persona. `/swap-to-feature` no crea conexiones ni concede roles.

En el workspace de feature:

1. Abra **Workspace settings -> Workspace identity** y cree la Workspace Identity si no existe.
2. Abra **Manage access** y concédale los permisos de Notebook, Semantic Model, OneLake y demás recursos que necesite la carga de trabajo de feature.
3. Abra `Patterns_Load_Validate_And_Refresh` en modo de edición.
4. Para las actividades de Notebook, cree o seleccione una conexión de tipo Notebook con autenticación **Workspace Identity**. Ambas actividades de Notebook utilizan esta conexión.
5. Para la actividad de actualización nativa del Semantic Model, cree o seleccione una conexión independiente de tipo Power BI datasets con autenticación **Workspace Identity**.
6. Guarde el Data Pipeline.
7. Abra **Settings -> Manage connections and gateways -> Connections** y compruebe en ambos registros:
   - que tengan GUID distintos;
   - que correspondan al workspace de feature previsto;
   - que sus tipos de conector sean Notebook y Power BI datasets;
   - que usen autenticación Workspace Identity;
   - que se hayan compartido con los roles User/Owner necesarios.
8. Copie el GUID de cada conexión desde sus detalles o su URL a `.env`.

El repositorio no intenta deducir las conexiones buscando fragmentos de sus nombres para mostrar. Si las etiquetas de la interfaz de Fabric difieren, los criterios de aceptación son el tipo de conector, la autenticación Workspace Identity, la asociación con el workspace y el GUID.

## 3. Configurar el destino local de feature

Si es necesario, copie [.env.sample](../../.env.sample) a `.env`. `.env` está excluido de Git. Para el workspace de feature seleccionado, configure:

| Clave | Valor |
|---|---|
| `FEATURE_WORKSPACE_ID` | GUID del workspace de Branch Out |
| `FEATURE_NOTEBOOK_CONNECTION_ID` | GUID de la conexión de Notebook existente |
| `FEATURE_REFRESH_CONNECTION_ID` | GUID de la conexión de actualización de Power BI datasets existente |

Borre los valores de Lakehouse y modelo de feature que hayan quedado de otro workspace. El paso de preparación descubre y registra:

| Clave | Elemento descubierto |
|---|---|
| `FEATURE_LAKEHOUSE_ID` | GUID físico del elemento `PatternsLakehouse` |
| `FEATURE_SEMANTIC_MODEL_ID` | GUID físico del elemento `Patterns_Semantic_Model` |

No se deben utilizar los IDs lógicos de `.platform` en lugar de los GUID físicos.

## 4. Cambiar al workspace de feature

Seleccione y actualice la feature branch:

```powershell
git fetch origin
git checkout <feature-branch>
git pull --ff-only
```

Ejecute [`/swap-to-feature`](../../.github/skills/swap-to-feature/SKILL.md). Sin Copilot, siga la [secuencia independiente de feature](#cli-independiente).

Para un nuevo destino de feature, la skill:

1. usa la identidad de usuario aprobada de Azure CLI;
2. valida el workspace explícito y los GUID de ambas conexiones existentes;
3. descubre el Lakehouse y el Semantic Model exactos por nombre;
4. escribe los IDs descubiertos en `.env`;
5. se detiene antes de reescribir archivos locales si falla la preparación;
6. ejecuta el cambio de referencias sin conexión cuando la preparación termina correctamente.

La preparación utiliza `mode="existing"`. No crea conexiones, modifica permisos, realiza operaciones de Git ni efectúa ninguna otra escritura en la nube.

El cambio de referencias sin conexión:

- crea un conjunto de valores de feature y lo añade a `settings.json`;
- reescribe la URL de workspace y Lakehouse de Direct Lake del Semantic Model;
- reescribe las dependencias de Lakehouse de los bloques META de los Notebooks que las tengan;
- reescribe los campos registrados de workspace, modelo y conexión del Data Pipeline;
- conserva los IDs lógicos portables;
- detecta IDs obsoletos de un destino de feature anterior;
- comprueba que los IDs físicos críticos de Dev ya no estén presentes.

Revise los cambios exactos antes de hacer commit:

```powershell
git add -A
git commit -m "Swap references to feature workspace"
git push
```

## 5. Actualizar y probar el workspace de feature

1. En el panel **Source control** del workspace de feature, realice la Actualización desde Git.
2. Abra `Patterns_Variables` y active el conjunto de valores de feature.
3. Inspeccione el Data Pipeline:
   - ambas actividades de Notebook deben usar la conexión de Notebook de feature;
   - la actividad de actualización debe usar la conexión de actualización de feature;
   - los IDs físicos de workspace y modelo deben pertenecer al workspace de feature.
4. Inspeccione las vinculaciones del Semantic Model y del Lakehouse asociado a los Notebooks.
5. Ejecute `Patterns_Load_Validate_And_Refresh`.
6. Confirme que:
   - la carga haya finalizado;
   - la validación de solo lectura haya finalizado;
   - la actualización nativa haya finalizado;
   - los campos de fecha y los cálculos necesarios se comporten como se espera;
   - el informe se visualice;
   - se superen las comprobaciones necesarias de Ontology, Data Agent y consumo de datos.

`minimum_patient_count` procede de la Variable Library activa y es un valor positivo de tipo Integer. `run_label` es un parámetro independiente de tipo String cuyo valor predeterminado es `manual`. Que la validación termine correctamente no demuestra que funcionen DAX, la propiedad del modelo, el acceso al informe ni la autorización de quienes consumen los datos.

## 6. Restaurar Dev antes del PR

Ejecute [`/swap-to-dev`](../../.github/skills/swap-to-dev/SKILL.md). En la CLI: `python scripts\workspace_swap.py --swap-to-dev`. La operación se realiza sin conexión:

- sin autenticación en Azure ni GitHub;
- sin artefactos de Actions;
- sin activar flujos de aprovisionamiento;
- sin cambios en conexiones ni permisos;
- sin actualizar Fabric.

Elimina el conjunto de valores de feature, restaura las referencias canónicas de workspace, Lakehouse, modelo y conexiones de Dev y ejecuta las mismas comprobaciones de preparación que CI. La skill comprueba la preparación automáticamente. Si se utiliza la CLI, también debe ejecutarse `python scripts\workspace_swap.py --check-ready`.

Revise el resultado:

```powershell
git diff
git add -A
git commit -m "Restore Dev references before merge"
git push
```

Abra un PR a `dev`. Configure estas comprobaciones obligatorias:

- `Check for non-dev IDs in Fabric items`
- `Run unit tests`

La comprobación de preparación verifica:

- las referencias canónicas de workspace, Lakehouse, modelo y conexiones de Dev;
- que no haya archivos de conjuntos de valores de feature;
- que no queden IDs físicos de feature conocidos en los archivos registrados;
- que los valores de referencia de las reglas de parametrización sean coherentes.

## 7. Actualizar y validar Dev

Tras el merge del PR:

1. En Dev, abra **Source control**.
2. Revise las definiciones entrantes y seleccione **Update all**.
3. Espere a que termine la sincronización.
4. Inspeccione el Data Pipeline canónico de Dev y las vinculaciones del Semantic Model.
5. Ejecute `Patterns_Load_Validate_And_Refresh`.
6. Revise las tres actividades, los campos y cálculos del modelo, el informe y las evidencias de aceptación necesarias para la carga de trabajo.

Dev es manual de forma deliberada. El merge no actualiza el workspace ni ejecuta el Data Pipeline.

El paso siguiente es una promoción revisada de `dev` a `test`. Véase el [Proceso de lanzamiento](fabric-release-process.md#de-dev-a-test).

## Skills de Copilot

El repositorio incluye:

| Skill | Propósito |
|---|---|
| [/swap-to-feature](../../.github/skills/swap-to-feature/SKILL.md) | Validar y registrar un destino de feature conocido y, después, aplicar el cambio local a feature |
| [/swap-to-dev](../../.github/skills/swap-to-dev/SKILL.md) | Restaurar las referencias canónicas de Dev sin conexión y comprobar la preparación |
| [/swap-to-feature-dryrun](../../.github/skills/swap-to-feature-dryrun/SKILL.md) | Previsualizar cambios de feature conocidos sin autenticación ni escrituras |
| [/swap-to-dev-dryrun](../../.github/skills/swap-to-dev-dryrun/SKILL.md) | Previsualizar la restauración de Dev sin autenticación ni escrituras |
| [/prepare-feature-workspace](../../.github/skills/prepare-feature-workspace/SKILL.md) | Ejecutar la preparación y validación sin aplicar el cambio |
| [/prepare-dev-workspace](../../.github/skills/prepare-dev-workspace/SKILL.md) | Registrar un cambio aprobado de la configuración de referencia de Dev |

Las skills de simulación no crean los recursos que falten ni aplican el cambio. Invocar una skill constituye la solicitud de ejecución; los fallos normales de validación siguen siendo visibles.

## CLI independiente

Los scripts también se pueden utilizar sin Copilot.

Para preparar un nuevo destino de feature y aplicar el cambio:

```powershell
az login --tenant <tenant-guid> --use-device-code
az account show --query tenantId --output tsv
python scripts\prepare_fabric_workspace.py --feature --use-azure-cli
python scripts\workspace_swap.py
```

Confirme que el inquilino mostrado sea el aprobado. No imprima ni copie tokens de acceso. El cambio directo muestra las modificaciones previstas y espera a que se escriba literalmente `YES`.

Para restaurar Dev:

```powershell
python scripts\workspace_swap.py --swap-to-dev
python scripts\workspace_swap.py --check-ready
```

Para registrar un cambio deliberado de los recursos de Dev:

```powershell
python scripts\prepare_fabric_workspace.py --dev --replace-dev-bindings
```

Este comando se utiliza en la configuración inicial o para un cambio aprobado de recursos canónicos, no para la vuelta habitual desde el trabajo de feature.

## Por qué es necesario el cambio de referencias

Branch Out copia al workspace de feature las definiciones compatibles con Git. Algunas contienen referencias físicas del entorno que siguen apuntando a Dev:

- las URL de workspace y Lakehouse de Direct Lake del Semantic Model;
- las dependencias de Lakehouse en los bloques META de los Notebooks;
- los GUID de workspace, modelo y conexiones del Data Pipeline.

Un pipeline de feature nunca debe actualizar Dev. `workspace_swap.py` reescribe únicamente las referencias físicas registradas y crea o elimina el conjunto de valores de feature de la Variable Library.

Los IDs lógicos portables de `.platform`, como las referencias de Ontology a Lakehouse y de Data Agent a Ontology, se resuelven en el workspace actual y no necesitan un cambio de IDs físicos.

## Por qué no se usa fabric-cicd para los workspaces de feature

Este repositorio utiliza dos modelos de actualización:

| Workspace | Origen de las definiciones |
|---|---|
| Dev y feature | Fabric Git |
| Test y Prod | Publicador por API seleccionado |

Publicar mediante fabric-cicd en un workspace de feature conectado a Git puede provocar una **desviación del workspace** (*workspace drift*) entre Fabric y Git. La siguiente actualización desde Git puede sobrescribir la publicación por API o generar conflictos.

Un workspace de feature efímero, sin conexión a Git y desplegado mediante CI, es una arquitectura alternativa válida, pero no es el flujo implementado aquí.

## Registro de metadatos

El script de cambio utiliza un registro de tipos de elemento. Para añadir un tipo nuevo, basta con una entrada en el registro si las estrategias de reescritura existentes cubren sus campos físicos. Las nuevas estructuras de referencias físicas también requieren correspondencias de configuración y de valores de referencia, además de pruebas de regresión.

| Tipo de elemento | Referencias físicas o lógicas | Comportamiento del cambio |
|---|---|---|
| SemanticModel | URL física de workspace y Lakehouse | Se reescribe y se restaura |
| Notebook con Lakehouse asociado | Campos META físicos de workspace y Lakehouse | Se reescriben y se restauran |
| DataPipeline | Campos físicos de workspace, modelo y conexiones, además de referencias lógicas portables a los Notebooks | Se reescriben y restauran los campos físicos registrados |
| VariableLibrary | Conjuntos de valores de etapa y feature | Se crea o elimina el conjunto de valores de feature |
| Ontology | ID lógico portable de Lakehouse | Se valida, no se reescribe |
| DataAgent | ID lógico portable de Ontology | Se valida, no se reescribe |
| DeploymentPlan | IDs lógicos portables de los elementos | No se reescriben |

Archivos principales de la implementación:

| Archivo | Función |
|---|---|
| [workspace_swap.py](../../scripts/workspace_swap.py) | Cambio de referencias físicas sin conexión y comprobación de preparación |
| [prepare_fabric_workspace.py](../../scripts/prepare_fabric_workspace.py) | Validación y descubrimiento de feature, y registro explícito de la configuración de referencia de Dev |
| [pipeline_bindings.py](../../scripts/pipeline_bindings.py) | Campos físicos registrados del Data Pipeline |
| [parameter.yml](../../data/fabric/parameter.yml) | Sustituciones de destino de fabric-cicd y valores de referencia canónicos de Dev |
| [bulk-parameter.yml](../../data/fabric/bulk-parameter.yml) | Sustituciones de REST directo y valores de referencia canónicos de Dev |

## Limpieza de feature

Una vez fusionado el PR de feature y aceptado Dev tras su actualización:

1. La persona que desarrolló la feature registra el workspace, la Workspace Identity y los GUID exactos de las conexiones; después confirma que ninguna definición de origen, variable o pipeline activo haga referencia a ellos.
2. Se conservan las evidencias necesarias y se obtiene la aprobación para eliminar los recursos.
3. Quien administra las conexiones elimina las dos conexiones de feature de ámbito de inquilino mientras todavía se puede verificar su relación con el workspace y la identidad.
4. Quien administra el workspace elimina el workspace de feature y registra el estado resultante del ciclo de vida de la Workspace Identity. No debe suponerse que eliminar el workspace también elimine las conexiones de ámbito de inquilino.
5. Quien administra el repositorio elimina la feature branch cuando lo permitan las políticas de retención y recuperación.
6. La persona que desarrolla borra los cinco valores de feature de su `.env` local antes de seleccionar otro workspace.

La limpieza de archivos de origen que realiza `/swap-to-dev` no autoriza a eliminar recursos de Fabric. El apartado [Limpieza de la guía de configuración](SETUP.md#limpieza) describe la retirada completa de los recursos del ejemplo.

## Referencias

- [Flujo de Git de fabric-cicd](https://microsoft.github.io/fabric-cicd/latest/how_to/deployment_overview/#git-flow)
- [Operación Branch out de Fabric](https://learn.microsoft.com/en-us/fabric/cicd/git-integration/branched-workspace#branch-out-operation)
- [Limitaciones de Branch Out en Fabric](https://learn.microsoft.com/en-us/fabric/cicd/git-integration/branched-workspace#branching-out-limitations)
- [Prácticas recomendadas de integración de Git en Fabric](https://learn.microsoft.com/en-us/fabric/cicd/best-practices-cicd)
- [Actividad de Notebook con Workspace Identity](https://learn.microsoft.com/en-us/fabric/data-factory/notebook-activity#using-fabric-workspace-identity-wi-in-the-notebook-activity)
- [Administrar conexiones de Fabric](https://learn.microsoft.com/en-us/fabric/data-factory/data-source-management)

---

## Sobre esta traducción

Este documento es una traducción de [fabric-development-process.md](../../fabric-development-process.md). La versión en inglés es la fuente de referencia y puede estar más actualizada.

La actualización del 15-10-2026 se ha revisado con asistencia de IA, sin nueva validación por hablantes nativos. Se conservan las decisiones anteriores de [`GLOSARIO.md`](GLOSARIO.md) y se aplica [`GUIA-DE-ESTILO.md`](GUIA-DE-ESTILO.md).

Los enlaces externos apuntan a la documentación en inglés. Los errores pueden comunicarse mediante una incidencia que indique el idioma. Si el error también existe en inglés, debe corregirse primero allí; véanse [`REVISION.md`](REVISION.md) y [`TRANSLATION.md`](../../TRANSLATION.md).
