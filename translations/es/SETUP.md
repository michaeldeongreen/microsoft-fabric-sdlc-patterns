[English](../../SETUP.md) | **Español**

<!-- source: SETUP.md @ f7f949d | translated: 2026-10-15 -->

> 📄 **La versión en inglés de este documento es la de referencia.** En caso de discrepancia, [el original en inglés](../../SETUP.md) tiene precedencia.

# Configuración de este repositorio

Esta guía explica cómo configurar un *fork* nuevo para disponer de un flujo de
trabajo funcional de Dev a Test y a Prod. Se recomienda empezar con
`fabric-cicd`, el método de despliegue predeterminado, que no usa publicación
masiva. Los demás métodos comparten la configuración y el ciclo de lanzamiento,
pero tienen límites de validación adicionales.

Para aprender el patrón, deben usarse workspaces dedicados al ejemplo y datos
que no sean de producción.

## Qué se va a crear

| Rama de Git | Etapa de Fabric | Mecanismo de actualización |
|---|---|---|
| `dev` | Workspace Dev | Un operador designado del workspace Dev selecciona **Update all** |
| `test` | Workspace Test | El método de despliegue seleccionado de GitHub Actions |
| `main` | Workspace Prod | El método de despliegue seleccionado de GitHub Actions |

Cada workspace tiene:

- una *Workspace Identity* de Fabric;
- una conexión de Notebook que se autentica con esa Workspace Identity;
- una conexión de Power BI datasets para la actualización del Semantic Model,
  que se autentica con esa Workspace Identity; y
- un conjunto de valores de Variable Library y vinculaciones físicas de
  elementos específicos de la etapa.

El Data Pipeline de Fabric del ejemplo carga datos de demostración, los valida
y realiza la única actualización del Semantic Model.

## Quién realiza cada paso

| Actor | Responsabilidad durante la configuración |
|---|---|
| Administrador del repositorio de GitHub | Fork, ramas, Actions, entornos, reglas, secretos, variables, ciclo de vida del PAT y selección del método de despliegue |
| Administrador de identidades o grupos de Entra | Aplicación y Service principal de despliegue, ciclo de vida del secreto de cliente, grupo de Service principals autorizados y grupo de administradores de conexiones |
| Administrador del inquilino de Fabric | Configuración del inquilino para la integración de Git y los Service principals, limitada a los grupos adecuados |
| Administrador de workspaces de Fabric | Fabric Capacity, workspaces Dev/Test/Prod, Workspace Identities, roles de workspace y acceso de las Workspace Identities a los recursos |
| Administrador del workspace de feature o de conexiones | Workspace Identity de feature, su acceso a los recursos y sus dos conexiones |
| Desarrollador de feature | Credencial propia de Git, Branch Out, `.env` local, cambios de referencias, pruebas de feature y PR de feature a Dev |
| Operador del workspace Dev | Actualización de Dev desde Fabric Git, inspección de vinculaciones y ejecución manual del Data Pipeline de Dev |
| GitHub Actions | Creación o reutilización y verificación de las conexiones de Test/Prod, publicación y ejecución del Data Pipeline de Fabric |
| Responsable de verificación del lanzamiento o revisor de Prod | Aceptación en Test y autorización para Prod cuando se haya configurado la protección |

El *Service principal* de despliegue y la Workspace Identity tienen funciones
distintas. El Service principal publica definiciones y envía trabajos. La
Workspace Identity autentica las actividades de Notebook y de actualización
del Semantic Model. En un fork de ejemplo, una persona puede desempeñar varios
roles humanos, pero la autoridad y la responsabilidad necesarias siguen siendo
explícitas.

## Antes de empezar

### Herramientas locales

Instale:

- Git;
- Python 3.10 o posterior;
- `pip` y un entorno virtual de Python;
- Azure CLI para descubrir y validar los recursos del workspace de feature; y
- PowerShell si se quieren usar los comandos exactamente como se muestran.

Desde la raíz del repositorio:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements-dev.txt
```

Los scripts locales no necesitan el secreto del Service principal de
despliegue ni el PAT que se usa para las variables de los entornos de GitHub.

### Acceso necesario

Confirme que los administradores designados puedan:

- registrar una aplicación de Entra, crear su Service principal y su
  credencial, y administrar la pertenencia a grupos de seguridad;
- configurar las opciones del inquilino de Fabric;
- asignar Fabric Capacity y crear y administrar workspaces de Fabric;
- crear una Workspace Identity y concederle acceso al workspace y a los
  recursos;
- administrar el fork, GitHub Actions, entornos, variables, secretos y
  reglas; y
- crear y administrar conexiones de Fabric.

Para el método REST masivo directo, la importación de tipos de elemento de
Fabric requiere una SKU F o Fabric Trial. Verifique los requisitos actuales de
Fabric Capacity para cualquier otra ruta y para los tipos de elemento que se
añadan.

### Valores que deben registrarse

Mantenga este inventario fuera del control de versiones hasta que se haya
documentado el destino de cada valor:

| Valor | Dónde se usa |
|---|---|
| ID del inquilino de Entra | Secreto del entorno de GitHub |
| ID de cliente y secreto de la aplicación de despliegue | Secretos del entorno de GitHub |
| GUID de los workspaces Dev/Test/Prod | Secretos de los entornos de GitHub y entradas de configuración |
| IDs de objeto de las Workspace Identities de Dev/Test/Prod | Verificación de permisos |
| ID de objeto del grupo de administradores de conexiones | Variable del repositorio o del entorno |
| PAT de GitHub limitado al repositorio | Secreto del entorno de GitHub |
| GUID del Lakehouse, del Semantic Model y de las conexiones de Dev | Configuración de referencia inicial de Dev y `.env` local |
| GUID del workspace y de las conexiones de feature | `.env` del desarrollador, excluido de Git |

Los GUID son IDs, no credenciales, pero debe validarse su procedencia antes de
usarlos. Nunca deben guardarse credenciales, tokens de acceso ni PAT en `.env`,
el código fuente, los registros, los artefactos ni el chat.

## 1. Crear un fork e inicializar las ramas

1. Cree un fork de la revisión completa del repositorio y clónelo.
2. Mantenga GitHub Actions deshabilitado hasta que existan `dev`, `test` y los
   entornos de GitHub. Así se evita que la creación de una rama se interprete
   como un lanzamiento en Test o Prod.
3. Cree `dev` y `test` a partir del mismo *commit* revisado de `main`:

   ```powershell
   git checkout main
   git pull --ff-only
   git branch dev
   git branch test
   git push origin main
   git push origin dev
   git push origin test
   ```

4. Registre el commit inicial:

   ```powershell
   git rev-parse HEAD
   ```

Tras la inicialización, use la ruta de promoción del repositorio:

- feature branch -> `dev`
- `dev` -> `test`
- `test` -> `main`

## 2. Crear identidades, grupos y workspaces

### Service principal de despliegue y grupos

Cree o seleccione un Service principal de despliegue para el ejemplo. Si se
crea con Azure CLI, capture su salida de forma segura:

```powershell
az ad sp create-for-rbac --name "SPN-Fabric-SDLC-Patterns"
```

No conceda roles de suscripción de Azure ajenos a esta tarea solo porque
`create-for-rbac` lo permita. El rol de workspace de Fabric necesario se
configura en Fabric.

Use grupos de seguridad separados para responsabilidades distintas:

| Grupo | Miembros | Propósito |
|---|---|---|
| Fabric CI/CD service principals | Service principal de despliegue | Limitar la configuración del inquilino de Fabric para Service principals |
| Fabric Git users | Usuarios que conectan workspaces de Fabric a Git | Limitar la configuración del inquilino para la integración de Git cuando exista esa restricción |
| Connections-Admins | Administradores humanos de conexiones de confianza | Recibir el rol Owner en las dos conexiones de cada etapa |

No añada desarrolladores a un grupo con rol Owner sobre las conexiones de todos
los entornos solo para que puedan usar Dev. Comparta únicamente las
dependencias de Dev necesarias, con acceso User.

### Configuración del inquilino de Fabric

El administrador del inquilino de Fabric debe verificar las opciones actuales
y limitarlas a los grupos previstos. Este ejemplo requiere:

- integración de GitHub/Fabric Git para los usuarios que conectan los
  workspaces de Dev y de feature;
- **Service principals can call Fabric public APIs**; y
- **Service principals can create workspaces, connections, and deployment
  pipelines** para el grupo autorizado de Service principals de despliegue.

Los roles de workspace no anulan la configuración del inquilino. El
repositorio no modifica esa configuración ni la pertenencia a los grupos.

Consulte la documentación actual sobre la
[configuración del inquilino para desarrolladores de Fabric](https://learn.microsoft.com/en-us/fabric/admin/service-admin-portal-developer)
antes de aplicar cambios que afecten a todo el inquilino.

### Workspaces y Workspace Identities

Cree workspaces Dev, Test y Prod en una Fabric Capacity adecuada. Registre el
GUID que Fabric asigne a cada workspace.

Para cada workspace:

1. Conceda al Service principal de despliegue el rol Contributor, conservando
   cualquier asignación superior ya aprobada.
2. Abra **Workspace settings -> Workspace identity** y cree la Workspace
   Identity si no existe.
3. Abra **Manage access** y conceda a esa Workspace Identity el acceso al
   workspace y a los recursos que requieren las actividades de Notebook y de
   actualización del Semantic Model. Contributor es el rol de referencia para
   Notebook en este ejemplo, cuyos elementos están en el mismo workspace.
4. Registre el ID de objeto de la Workspace Identity y verifique la asignación.

Crear una Workspace Identity no crea sus conexiones. Las conexiones se crean
más adelante, de forma distinta según la etapa.

### Permisos para la actualización posterior al ETL

<a id="post-etl-refresh-permissions"></a>

| Actor o identidad | Acceso necesario | No implica |
|---|---|---|
| Administrador del workspace de Fabric | Admin para crear la Workspace Identity y asignar acceso | Acceso a las conexiones para todos los usuarios del workspace |
| Service principal de despliegue | Contributor en cada destino y autorización en la configuración de las API del inquilino | Autenticación de las actividades en tiempo de ejecución ni rol Admin del workspace |
| Workspace Identity | Permisos de Notebook, Semantic Model, OneLake y otros recursos necesarios para la etapa | Autoridad para publicar ni acceso a GitHub |
| Grupo Connections-Admins | Owner en las dos conexiones de la etapa | Rol Admin del workspace ni identidad de ejecución |
| Usuario o desarrollador | Contributor, Member o los permisos necesarios en Dev/feature; User en las dependencias que ejecuta | Owner de las conexiones de Test/Prod |
| Propietario del Semantic Model | Autorización sobre el origen y propiedad o toma de control del modelo cuando se requiera | Permisos de despliegue ni de ejecución de actividades |

El acceso a las conexiones es independiente del acceso al workspace. Una
publicación correcta no demuestra la propiedad del modelo, la autorización
sobre el origen, el acceso a los informes ni los permisos de los consumidores.

## 3. Configurar GitHub

<a id="5-configure-github"></a>

### Crear entornos de GitHub

Cree:

| Entorno de GitHub | Rama de despliegue permitida | Destino en Fabric |
|---|---|---|
| `Dev` | `dev` | Workspace Dev |
| `Test` | `test` | Workspace Test |
| `Prod` | `main` | Workspace Prod |

Configure un revisor obligatorio y una política de ramas de despliegue para
Prod antes del primer lanzamiento en Prod. Los archivos de flujo de trabajo no
crean esos controles ni demuestran que estén configurados.

### Secretos de los entornos

Añada estos secretos a cada entorno:

| Secreto | Valor |
|---|---|
| `AZURE_TENANT_ID` | ID del inquilino de Entra |
| `AZURE_CLIENT_ID` | ID de cliente de la aplicación de despliegue |
| `AZURE_CLIENT_SECRET` | Credencial de la aplicación de despliegue |
| `FABRIC_WORKSPACE_ID` | GUID del workspace correspondiente a ese entorno |
| `GH_ENV_VARIABLES_TOKEN` | PAT limitado al repositorio, con permisos Contents de lectura/escritura y Environments de lectura/escritura |

El PAT interviene en todos los lanzamientos seleccionados de Test/Prod. Se
limita a las comprobaciones previas de GitHub y a la persistencia de los IDs de
conexión; no autentica las llamadas a Fabric. Para las operaciones de Fabric
se usa el Service principal de despliegue.

El ejemplo de referencia puede usar un único *fine-grained PAT* (PAT de
permisos específicos) para Fabric Git y para escribir variables de los
entornos de GitHub, pero eso vincula la disponibilidad de ambos usos y concede
autoridad para administrar entornos más allá de dos nombres de variable.
Para un fork de producción, es preferible una credencial con vencimiento y un
responsable designado de su rotación, o una GitHub App con el ámbito adecuado.
Cada desarrollador usa su propia credencial de Fabric Git.

### Variables del entorno de GitHub y del repositorio

<a id="environment-variables"></a>

Configure una vez el grupo de administradores de conexiones como variable del
repositorio:

| Variable | Valor |
|---|---|
| `FABRIC_CONNECTION_ADMINS_GROUP_ID` | ID de objeto del grupo Connections-Admins |

Una variable del entorno de GitHub con el mismo nombre puede sustituirla
para usar grupos específicos de cada etapa.

No invente manualmente estas variables del entorno de GitHub:

| Variable | Quién la crea | Significado |
|---|---|---|
| `NOTEBOOK_CONNECTION_ID` | Acción de aprovisionamiento de Dev o lanzamiento seleccionado de Test/Prod | GUID de la conexión de Notebook de la etapa |
| `SEMANTIC_MODEL_REFRESH_CONNECTION_ID` | Acción de aprovisionamiento de Dev o lanzamiento seleccionado de Test/Prod | GUID de la conexión de Power BI datasets para la actualización del Semantic Model de la etapa |

Los valores que faltan se crean y se verifican. Si un valor existente es
distinto, la operación falla y no lo sobrescribe.

### Variables del método de despliegue

<a id="deployment-method-variables"></a>

Empiece por el método predeterminado:

| Método | `DEPLOY_METHOD` | `DEPLOYMENT_PLAN_PATH` | Estado inicial |
|---|---|---|---|
| fabric-cicd sin publicación masiva | Sin definir o `fabric-cicd` | No se usa | Recomendado; Test verificado con una ejecución real del método predeterminado |
| fabric-cicd sin publicación masiva, con plan interpretado por el adaptador | `fabric-cicd-plan` | `data/fabric/DeploymentPlan.DeploymentPlan/plan.yml` | Experimental; sin verificación mediante una ejecución real |
| fabric-cicd masivo, con plan interpretado por el adaptador | `fabric-cicd-bulk` | La misma ruta del plan | Experimental; sin verificación mediante una ejecución real |
| REST masivo directo | `bulk` | No se usa | Revalidar el comportamiento actual de la API y los requisitos de Fabric Capacity; sin verificación mediante una ejecución real |

<a id="fabric-cicd-bulk-settings"></a>

Los métodos de fabric-cicd usan `parameter.yml`. REST directo usa
`bulk-parameter.yml`. Los cuatro comparten la preparación de conexiones y el
mismo traspaso de control al Data Pipeline de Fabric.

<a id="before-switching-methods"></a>

Antes de cambiar de método:

1. Espere a que terminen los lanzamientos de Test y Prod en curso.
2. Promueva normalmente cualquier cambio necesario en los flujos de trabajo o
   scripts de ejecución.
3. Cambie `DEPLOY_METHOD`.
4. Inicie una ejecución manual desde `test` o `main`, o espere a la siguiente
   promoción que cumpla los filtros. Cambiar la variable no inicia ninguna
   ejecución por sí solo.
5. Considere la nueva ruta sin verificar hasta que se acepten las evidencias
   de sus propias pruebas en Test: una con recursos nuevos y otra que
   reutilice los recursos existentes.

### Reglas de las ramas

Después de hacer commit de la configuración de referencia inicial de Dev,
exija PR, bloquee los pushes forzados y la eliminación de ramas, y configure:

| Destino | Origen permitido | Comprobaciones obligatorias |
|---|---|---|
| `dev` | Feature branch | `Check for non-dev IDs in Fabric items`, `Run unit tests` |
| `test` | `dev` | `Enforce promotion path`, `Run unit tests` |
| `main` | `test` | `Enforce promotion path`, `Run unit tests` |

En un fork de ejemplo administrado por una sola persona, decida explícitamente
quién puede aprobar la inicialización o eludir las reglas durante ella. Retire
los permisos temporales de excepción después de la configuración.

Habilite GitHub Actions solo cuando estén configurados las ramas, los entornos,
los secretos, las variables y el selector de despliegue previsto.

## 4. Aprovisionar las conexiones de Dev

<a id="first-time-dev-bootstrap"></a>

El archivo `.github/workflows/bootstrap-dev.yml` aparece en Actions como
**Provision Fabric Connections**.

En el recorrido normal de configuración, ejecútelo solo para Dev:

1. Abra GitHub Actions y seleccione **Provision Fabric Connections**.
2. Seleccione la rama `dev`.
3. Seleccione la operación `provision`.
4. Confirme que el destino sea el entorno de GitHub `Dev` y ejecute el flujo
   de trabajo.
5. Verifique que el flujo de trabajo:
   - valida la Workspace Identity de Dev, que debe existir previamente;
   - crea o reutiliza conexiones distintas de Notebook y de Power BI datasets
     con autenticación Workspace Identity;
   - concede al grupo Connections-Admins el rol Owner, o lo eleva a ese rol,
     y vuelve a leer la asignación para comprobarla;
   - crea y verifica ambas variables de ID de conexión de Dev; y
   - no realiza operaciones sobre roles de workspace, publicación de
     elementos ni actividades del pipeline.

Los nombres siguen el formato
`Patterns-<Dev|Test|Prod|Feature>-<Purpose>-<full-workspace-GUID>`.
El GUID evita colisiones entre los nombres de conexiones de distintos forks
en un mismo inquilino.

Copie los dos IDs de Dev desde **Repository Settings -> Environments -> Dev ->
Environment variables**. Contraste cada valor en Fabric, en
**Settings -> Manage connections and gateways -> Connections**: abra la
conexión exacta de Dev, confirme el conector, la autenticación y el workspace,
y compare el GUID de la URL de detalles. No elija una conexión con un nombre
parecido.

No repita este paso manual en Test ni Prod durante el recorrido normal. El
primer lanzamiento seleccionado de Test/Prod crea o reutiliza y verifica las
conexiones automáticamente. Una ejecución manual para Test/Prod se reserva
para recuperación, migración o diagnóstico.

## 5. Inicializar Dev y sustituir las referencias de ejemplo

<a id="3-initialize-the-dev-workspace"></a>
<a id="4-replace-the-reference-environment"></a>

El repositorio contiene referencias físicas reales de su workspace Dev de
origen. Sustitúyalas una sola vez por las referencias canónicas de Dev del fork
antes del trabajo habitual de feature.

### Excluir temporalmente el Data Pipeline de la primera importación desde Git

Desde `dev`:

```powershell
python scripts\prepare_fabric_workspace.py --stage-initial-pipeline
```

Revise el traslado temporal de la carpeta de definición del Data Pipeline de
`data/fabric` a `data/fabric-initialization`. Después, haga commit y push. Así se
evita que la primera importación de toda la rama desde Fabric Git cree un
Data Pipeline cuyos IDs físicos del Semantic Model y de las conexiones todavía
apunten al inquilino del repositorio de origen.

### Conectar y configurar Dev

1. En Dev, abra **Workspace settings -> Git integration**.
2. Use su propia identidad de GitHub y seleccione el fork, la rama `dev` y
   la carpeta `data/fabric`.
3. Conecte y sincronice los elementos base. Revise la advertencia de que una
   actualización de toda la rama puede sustituir el contenido del workspace.
4. Abra cada elemento y registre el GUID de su URL de Fabric:
   - `PatternsLakehouse`
   - `Patterns_Semantic_Model`
   Compruebe que el segmento de workspace de la URL sea el GUID del workspace
   Dev.
5. Configure `Patterns_Variables`:

   | Conjunto de valores | Variable | Valor esperado |
   |---|---|---|
   | Default | `target_workspace_id` | GUID del workspace Dev |
   | Default | `target_workspace_name` | Nombre del workspace Dev |
   | Default | `target_lakehouse_id` | GUID de `PatternsLakehouse` de Dev |
   | Default | `target_lakehouse_name` | `PatternsLakehouse` |
   | Default | `minimum_patient_count` | Integer positivo; valor de referencia del ejemplo: `5` |
   | Test | Sustitución de `target_workspace_id` | GUID del workspace Test |
   | Prod | Sustitución de `target_workspace_id` | GUID del workspace Prod |

   Mantenga Default activo en Dev. Las reglas de despliegue sustituyen el ID
   de Lakehouse heredado para Test/Prod.
6. Abra `Import_Patterns_Data`, use su panel Lakehouse para añadir el
   `PatternsLakehouse` existente de Dev y guarde el Notebook.
7. Abra `Patterns_Semantic_Model` en el editor web de modelos de Fabric y
   confirme que su origen Direct Lake sea el Lakehouse de Dev. La expresión
   de conexión de OneLake almacenada debe contener los GUID del workspace y
   del Lakehouse de Dev. Véase el
   [modelado web de Direct Lake](https://learn.microsoft.com/en-us/fabric/fundamentals/direct-lake-web-modeling).
8. Confirme que el propietario del Semantic Model tenga autorización sobre el
   origen. Tome el control del modelo solo mediante el proceso de propiedad
   aprobado; véanse los
   [permisos de los propietarios de Direct Lake](https://learn.microsoft.com/en-us/fabric/fundamentals/direct-lake-security-integration#direct-lake-owners).
9. Guarde los cambios canónicos de Fabric, haga commit y después descárguelos
   en la copia local. Conserve todos los IDs lógicos de `.platform`.

### Registrar las vinculaciones canónicas de Dev

Copie [.env.sample](../../.env.sample) a `.env`, excluido de Git, y configure:

- `DEV_WORKSPACE_ID`
- `DEV_SEMANTIC_MODEL_ID`
- `DEV_NOTEBOOK_CONNECTION_ID`
- `DEV_REFRESH_CONNECTION_ID`

Use el Semantic Model real de Dev y las dos conexiones verificadas de Dev.
Después, ejecute:

```powershell
python scripts\prepare_fabric_workspace.py --dev --replace-dev-bindings
python scripts\prepare_fabric_workspace.py --restore-initial-pipeline
python scripts\workspace_swap.py --check-ready
```

El primer comando actualiza conjuntamente las referencias de ambos archivos
de reglas de parámetros y el Data Pipeline trasladado temporalmente. No llama
a Fabric. Revise los cambios exactos, limitados a GUID; no acepte reglas de
parámetros mal formadas ni discrepancias entre ellas.

Haga commit y push de la revisión canónica completa de Dev. En Fabric,
seleccione **Update all**, inspeccione las vinculaciones resueltas y ejecute
`Patterns_Load_Validate_And_Refresh`.

El control de Dev se completa cuando:

- la carga, la validación y la actualización nativa terminan correctamente;
- el conjunto de valores activo y los destinos físicos pertenecen a Dev;
- los campos de fecha necesarios del Semantic Model y el informe funcionan
  con el propietario previsto; y
- `python scripts\workspace_swap.py --check-ready` termina correctamente.

## 6. Completar un ciclo de feature

Siga el [Proceso de desarrollo](fabric-development-process.md). El recorrido
resumido es:

1. Haga Branch Out desde Dev con todos los elementos.
2. Cree la Workspace Identity de feature y sus dos conexiones con
   autenticación Workspace Identity.
3. Complete los valores de feature en `.env`.
4. Ejecute `/swap-to-feature`, haga commit y push, y actualice el workspace de
   feature.
5. Active el conjunto de valores de feature y ejecute el Data Pipeline de
   Fabric.
6. Ejecute `/swap-to-dev`, revise la restauración y abra el PR a `dev`.
7. Tras el merge, actualice Dev manualmente y vuelva a ejecutar su
   Data Pipeline.

No use fabric-cicd para publicar en un workspace de feature conectado a Git.

## 7. Ejecutar el primer lanzamiento en Test

No cree manualmente las dos conexiones de Test. Antes de la promoción,
confirme que:

- existen el workspace Test y su Workspace Identity;
- la Workspace Identity tiene el acceso necesario al workspace y a los
  recursos;
- el Service principal de despliegue tiene el rol Contributor;
- el entorno de GitHub Test tiene los cinco secretos;
- la variable del grupo de administradores de conexiones es correcta; y
- `DEPLOY_METHOD` no está definido o tiene el valor `fabric-cicd`.

Abra y revise un PR de `dev` a `test`. Tras el merge, el flujo de trabajo
seleccionado de Test:

1. valida la rama y el entorno Test, y el acceso del PAT a GitHub;
2. crea o reutiliza y verifica las dos conexiones de Workspace Identity de
   Test;
3. verifica que Connections-Admins tenga el rol Owner;
4. guarda las variables de ID que faltan, sin sustituir valores distintos;
5. publica con fabric-cicd;
6. inicia el Data Pipeline de Fabric de la misma revisión y consulta su estado
   hasta que termina.

Los flujos de trabajo de los otros métodos pueden aparecer con sus trabajos
omitidos. Verifique que haya terminado correctamente el flujo seleccionado,
no solo uno de los omitidos.

En un destino limpio, configure la vinculación local del Graph Model de
Ontology al Lakehouse si Fabric lo requiere. Después, verifique:

- las tablas esperadas del Lakehouse y los resultados de validación;
- las conexiones de destino del Data Pipeline y su vinculación al Semantic
  Model;
- la actualización del Semantic Model, su propiedad y el acceso al origen,
  los campos de fecha y los cálculos necesarios;
- la visualización del informe;
- el comportamiento de las entidades y relaciones de Ontology; y
- el comportamiento de Data Agent y el acceso de consumidores que requiera
  el lanzamiento.

La secuencia compartida y las evidencias actuales se documentan en el
[Proceso de lanzamiento](fabric-release-process.md).

## 8. Ejecutar el primer lanzamiento en Prod

Antes de la promoción:

1. Configure el revisor del entorno Prod y la política de ramas de
   despliegue.
2. Confirme el workspace Prod, la Workspace Identity, los permisos, los
   secretos y la configuración de grupos.
3. Adjunte las evidencias aceptadas de Test a la decisión de lanzamiento.
4. Abra y revise un PR de `test` a `main`.

Tras el merge y la aprobación, el trabajo seleccionado de Prod sigue la misma
secuencia automática de creación o reutilización y verificación de conexiones,
publicación y Data Pipeline, con la configuración específica de Prod.

Esta revisión del repositorio no se ha verificado mediante una ejecución real
en Prod. La primera promoción debe tratarse como un lanzamiento controlado,
con un punto de recuperación explícito y evidencias registradas después del
despliegue.

## Verificar la configuración

| Comprobación | Resultado esperado |
|---|---|
| Separación de actores | Usuarios, GitHub Actions, Service principal de despliegue, PAT, Workspace Identity y grupo de administradores de conexiones tienen responsabilidades distintas y documentadas |
| Conexiones | Dos conexiones distintas por etapa con autenticación Workspace Identity; rol Owner verificado para el grupo previsto |
| Dev | Conectado a Git, referencias locales canónicas, actualización y Data Pipeline manuales |
| Feature | Conexiones creadas por el administrador del workspace de feature o de conexiones, destinos físicos exclusivos de feature y conjunto de valores de feature activo |
| Test/Prod | El lanzamiento seleccionado prepara y verifica las conexiones antes de publicar y usa la misma revisión para el Data Pipeline |
| Persistencia | Se crean las variables de ID de conexión que faltan; los valores en conflicto provocan un fallo |
| Ejecución | Carga -> validación -> actualización nativa, sin un segundo responsable de la actualización |
| Protección | Comprobaciones obligatorias de PR y aprobación configurada en el entorno Prod |

## Solución de problemas

| Síntoma | Responsable y primera comprobación |
|---|---|
| No se ejecutó ningún despliegue | Administrador del repositorio: rama seleccionada, `DEPLOY_METHOD`, filtros de rutas y si se omitió el trabajo seleccionado |
| Espera de aprobación | Revisor de Prod: protección del entorno de GitHub y rama autorizada |
| Fallo en las comprobaciones previas del PAT o en la persistencia | Administrador del repositorio: vencimiento del token y permisos Contents/Environments del repositorio |
| Falta la Workspace Identity o no está disponible su token | Administrador del workspace o del inquilino de Fabric: creación de la Workspace Identity, Fabric Capacity, política del inquilino y permisos sobre los recursos |
| No se puede ver o usar una conexión | Administrador de conexiones: GUID exacto, tipo de autenticación, acceso compartido Owner/User y nuevo inicio de sesión |
| El ID existente entra en conflicto con el recurso preparado | Administrador del repositorio: detenerse y revisar la migración prevista; no sobrescribir |
| La preparación de feature informa de conexiones ausentes | Administrador del workspace de feature: crear primero ambas conexiones de feature y copiar sus GUID exactos |
| Discrepancia en la configuración de referencia de Dev | Administrador del repositorio: comparar ambos archivos de parámetros, `.env` y los elementos canónicos de Dev; volver a ejecutar el comando explícito de configuración de referencia |
| Fallo de publicación | Operador del lanzamiento: resultado por elemento del publicador seleccionado; el ETL no debería haberse iniciado |
| GitHub agotó el tiempo de espera, pero Fabric sigue ejecutándose | Operador del lanzamiento: inspeccionar la ejecución exacta de Fabric antes de reintentar |
| Fallo del Data Pipeline | Responsable de la carga de trabajo: actividad fallida, conjunto de valores activo, vinculaciones, permisos del origen y del Semantic Model, Fabric Capacity e historial de actualización |
| El informe o los cálculos son incorrectos tras una ejecución correcta | Propietario del Semantic Model o responsable de pruebas de negocio: autorización sobre el origen, propiedad, DAX/cálculos y acceso de los consumidores |

## Forks existentes y conexiones heredadas

El flujo de trabajo **Provision Fabric Connections** también tiene la
operación `share-existing`, exclusiva de Dev, para dos conexiones heredadas
aprobadas. Concede al grupo de administradores de conexiones el rol Owner; no
convierte credenciales, sobrescribe variables, publica elementos ni elimina
recursos.

Para una migración revisada:

1. Registre los GUID anteriores y sus referencias.
2. Elimine solo las entradas obsoletas de variables de GitHub, con aprobación
   explícita.
3. Aprovisione las conexiones de sustitución con Workspace Identity.
4. Actualice las referencias del código fuente canónico de Dev mediante
   revisión.
5. Ejecute Dev y la promoción normal a Test.
6. Conserve las conexiones anteriores hasta que la revisión promovida de
   `main` se acepte en Prod y se registre una aprobación independiente para
   eliminarlas.

Eliminar una variable no autoriza a eliminar su recurso de Fabric.

## Limpieza

Después de fusionar una feature y aceptar el workspace Dev actualizado:

| Orden | Actor | Acción |
|---|---|---|
| 1 | Desarrollador de feature | Registrar el workspace, la Workspace Identity, la rama y los GUID exactos de las conexiones; demostrar que no quedan referencias activas en el código fuente ni en pipelines |
| 2 | Responsable del lanzamiento o del repositorio | Conservar las evidencias necesarias y aprobar la eliminación de los recursos concretos |
| 3 | Administrador de conexiones | Eliminar las dos conexiones de feature del inquilino mientras siga disponible el contexto de su workspace e identidad |
| 4 | Administrador del workspace de Fabric | Eliminar el workspace de feature y registrar el efecto sobre el ciclo de vida de la Workspace Identity y la liberación de Fabric Capacity |
| 5 | Administrador del repositorio de GitHub | Eliminar la feature branch cuando lo permita la política de recuperación |
| 6 | Desarrollador de feature | Borrar los cinco valores de feature del `.env` local |

Eliminar un workspace no demuestra que se hayan eliminado las conexiones del
inquilino. La limpieza de referencias que realiza `/swap-to-dev` no constituye
una aprobación para eliminar recursos.

Para retirar todo el ejemplo:

| Orden | Actor | Acción |
|---|---|---|
| 1 | Administrador del repositorio de GitHub | Deshabilitar los puntos de entrada de lanzamiento programados y manuales, esperar a que terminen las ejecuciones activas y registrar las variables actuales de los entornos |
| 2 | Responsable del lanzamiento | Conservar el commit aceptado, las URL de ejecución, el inventario de recursos y los puntos necesarios de recuperación de definiciones o datos |
| 3 | Administrador de conexiones | Verificar que ningún pipeline use los GUID de conexión de Dev/Test/Prod y eliminar después los pares aprobados |
| 4 | Administrador del workspace de Fabric | Retirar las cargas de trabajo y los workspaces, registrar el ciclo de vida de cada Workspace Identity y liberar las asignaciones de Fabric Capacity dedicada |
| 5 | Administrador del repositorio de GitHub | Eliminar las variables de ID de conexión, los secretos, los entornos, las reglas y el PAT limitado al repositorio cuando dejen de ser necesarios |
| 6 | Administrador del inquilino de Entra/Fabric | Retirar los roles de workspace, revocar la credencial de despliegue, retirar el Service principal de los grupos de configuración del inquilino y eliminar la aplicación y los grupos solo cuando ninguna otra carga de trabajo los use |
| 7 | Cada desarrollador | Eliminar el `.env` local y las credenciales en caché de este ejemplo |

La limpieza de elementos huérfanos del publicador no sustituye la retirada
completa de un entorno.

---

## Sobre esta traducción

Este documento es una traducción de [SETUP.md](../../SETUP.md). La versión en
inglés es la fuente de referencia y puede estar más actualizada.

Esta traducción, nueva en la actualización del 15-10-2026, se ha elaborado con
asistencia de IA y no cuenta con validación de hablantes nativos. Se aplican las
decisiones de [`GLOSARIO.md`](GLOSARIO.md) y
[`GUIA-DE-ESTILO.md`](GUIA-DE-ESTILO.md).

Los enlaces externos apuntan a la documentación en inglés para conservar la
terminología de la interfaz; si se prefiere otro idioma, puede cambiarse desde
el selector de idioma del sitio de destino. Los errores pueden comunicarse
mediante una incidencia que indique el idioma. Si el error también existe en
inglés, debe corregirse primero allí; véanse [`REVISION.md`](REVISION.md) y
[`TRANSLATION.md`](../../TRANSLATION.md).
