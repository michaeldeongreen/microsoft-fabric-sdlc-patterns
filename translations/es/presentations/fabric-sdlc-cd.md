---
# Preview locally from the repository root:
# npx --yes @marp-team/marp-cli@4.5.1 presentations/fabric-sdlc-cd.md --preview --allow-local-files
marp: true
theme: default
paginate: true
size: 16:9
header: "Entrega continua en Microsoft Fabric"
footer: "[Michael D. Green - Fabric SDLC Patterns](https://github.com/michaeldeongreen/microsoft-fabric-sdlc-patterns)"
style: |
  section {
    font-family: "Segoe UI", Arial, sans-serif;
    font-size: 27px;
    padding: 52px 64px;
    color: #201f1e;
    background: #ffffff;
  }
  h1 {
    color: #004578;
    font-size: 1.65em;
    margin-bottom: 0.45em;
  }
  h2 {
    color: #0078d4;
  }
  h3 {
    color: #004578;
    margin-bottom: 0.3em;
  }
  strong {
    color: #004578;
  }
  a {
    color: #0067b8;
  }
  blockquote {
    border-left: 8px solid #0078d4;
    background: #eff6fc;
    padding: 0.5em 0.8em;
    margin: 0.7em 0;
  }
  table {
    font-size: 0.72em;
    width: 100%;
  }
  th {
    background: #e5f1fb;
    color: #004578;
  }
  td,
  th {
    border-color: #d2d0ce;
  }
  code {
    background: #f3f2f1;
  }
  header, footer {
    color: #605e5c;
    font-size: 0.55em;
  }
  footer a {
    color: inherit;
    text-decoration: none;
  }
  section.title {
    text-align: center;
    justify-content: center;
    background: linear-gradient(135deg, #ffffff 0%, #eff6fc 100%);
    border-top: 10px solid #0078d4;
    box-shadow: inset 0 -7px 0 #ffb900;
  }
  section.title h1 {
    font-size: 2.25em;
  }
  section.divider {
    text-align: center;
    justify-content: center;
    color: white;
    background: linear-gradient(135deg, #004578 0%, #0078d4 100%);
    box-shadow: inset 0 -7px 0 #ffb900;
  }
  section.divider h1,
  section.divider h2,
  section.divider strong {
    color: white;
  }
  section.compact {
    font-size: 23px;
  }
  section.dense {
    font-size: 20px;
  }
  section.diagram {
    font-size: 19px;
    padding: 40px 52px;
  }
  section.diagram h1 {
    max-width: 52%;
    margin: 0.2em 0;
  }
  section.diagram h2 {
    font-size: 1.35em;
    margin: 0.2em 0 0.45em;
  }
  section.diagram p,
  section.diagram ul {
    margin-top: 0.35em;
    margin-bottom: 0.35em;
  }
  section.customer-challenges {
    background: #faf9f8;
  }
  section.customer-challenges table {
    border-collapse: separate;
    border-spacing: 12px;
    font-size: 0.73em;
  }
  section.customer-challenges thead {
    display: none;
  }
  section.customer-challenges td {
    width: 50%;
    vertical-align: top;
    padding: 12px 14px;
    background: #ffffff;
    border: 1px solid #d2d0ce;
    border-top: 5px solid #0078d4;
    border-radius: 5px;
  }
  section.customer-challenges tbody tr:nth-child(2) td {
    border-top-color: #ffb900;
  }
  section.customer-challenges tbody tr:nth-child(3) td {
    border-top-color: #d83b01;
  }
  section.ownership table {
    font-size: 0.7em;
  }
  section.ownership th,
  section.ownership td {
    vertical-align: top;
    padding: 12px;
  }
  section.ownership th:nth-child(1) {
    background: #e5f1fb;
  }
  section.ownership th:nth-child(2) {
    background: #e8ebfa;
  }
  section.ownership th:nth-child(3) {
    background: #e7f5e7;
  }
  section.dependency-contract table {
    font-size: 0.67em;
  }
  section.dependency-contract td {
    vertical-align: top;
  }
---

<!-- source: presentations/fabric-sdlc-cd.md @ f7f949d | translated: 2026-10-15 -->

<!-- _class: title -->
<!-- _paginate: false -->
<!-- _header: "" -->
<!-- _footer: "" -->

# Entrega continua en Microsoft Fabric

## Por qué es difícil, qué opciones hay y una implementación real en GitHub

**Michael Green**<br/>
*[CSA / DevSquad / MCSA]*

Octubre de 2026

[Implementación de referencia](https://github.com/michaeldeongreen/microsoft-fabric-sdlc-patterns)

Estado operativo: Dev `a417191`; lanzamiento de Test verificado en `e87f435`
el 2026-10-14.

<!--
Presentar la sesión como la continuación sobre CD de la presentación anterior sobre CI e introducir a quien expone.
La documentación oficial de Microsoft es la canónica; este repositorio presenta una implementación en GitHub con decisiones de diseño propias.
-->

---

# El problema de la entrega en Fabric

Un workspace de Fabric es, a la vez, un **entorno de desarrollo y de ejecución**.

Una sola solución puede abarcar:

- *Notebooks* y *pipelines*
- *Lakehouses* y datos
- *Semantic Models* e informes
- *Variable Libraries* y conexiones
- *Ontologies* y agentes

> **¿Cómo reproducir una solución funcional en Test y Prod sin reconstruirla a mano ni convertir cada workspace en una fuente de verdad independiente?**

<!--
No definir CD de forma genérica. Empezar por el problema operativo concreto de Fabric.
Editar directamente en el navegador es potente, pero por eso mismo hace falta una ruta de promoción disciplinada.
-->

---

<!-- _class: customer-challenges dense -->

# Por qué CI/CD en Fabric es difícil

**Para clientes y partners:** la entrega de datos e IA abarca infraestructura, elementos de plataforma, datos y estado, vinculaciones, identidades y operaciones, no solo código. Ese acoplamiento hace que la elección de plataforma tenga consecuencias: cambiar más adelante suele ser un programa de migración, no un cambio de herramienta.

| | |
|---|---|
| **Compatibilidad desigual del ciclo de vida**<br>Git, los *pipelines* de despliegue, `fabric-cicd` y las API admiten conjuntos de elementos distintos. | **Las dependencias se convierten en lógica de despliegue**<br>Los elementos base deben existir antes de que se resuelvan los IDs de destino y las definiciones dependientes. |
| **La configuración está fragmentada**<br>Variables en tiempo de ejecución, metadatos, conexiones, reglas y secretos tienen responsables y momentos de aplicación distintos. | **Las definiciones no son todo el entorno**<br>Datos, credenciales, permisos, programaciones y vinculaciones del primer despliegue necesitan planes aparte. |
| **Varias vías de actualización generan desviación**<br>Las ediciones directas, la sincronización con Fabric Git y el despliegue por API no deberían competir por el mismo workspace. | **La seguridad y la gobernanza abarcan varios sistemas**<br>Los roles de Fabric y la configuración de inquilino deben encajar con la identidad de Entra, los controles de GitHub, las aprobaciones, la auditoría y la gobernanza de datos corporativa. |

<!--
Esta es la diapositiva central del problema del cliente. La CD en Fabric es difícil porque el workspace es heterogéneo, no porque el YAML sea complicado.
El reto no es solo si Fabric es seguro: tiene que encajar en el modelo de control corporativo existente sin crear un proceso paralelo.
Usar «dependencia del proveedor» con cuidado: toda plataforma de datos e IA genera acoplamiento por gravedad de los datos, metadatos propietarios, configuración de seguridad y gobernanza, capacidades operativas e integración del ecosistema.
La idea no es que no se pueda cambiar, sino que migrar es un programa estratégico, no un cambio de herramienta de despliegue.
-->

---

<!-- _class: dense -->

# Antes de elegir herramientas de CI/CD, definir el alcance de la entrega

**Empezar por la solución, no por la herramienta de despliegue.**

| Pregunta | Qué decidir |
|---|---|
| **¿Qué forma parte de la solución?** | Inventariar los elementos de Fabric y la configuración o el estado necesarios para que funcione. |
| **¿Qué puede mover cada mecanismo?** | Registrar por separado la compatibilidad con Git, el publicador o API, los pipelines nativos y la identidad para cada elemento o subtipo. |
| **¿Cómo de portables son las referencias?** | Distinguir entre valores de ejecución, IDs lógicos e IDs físicos que hay que sustituir. |
| **¿Qué hay que aprovisionar?** | Inventariar las instancias de Fabric Capacity, los workspaces, vínculos privados, accesos directos y conexiones, roles y configuración de inquilino; elegir Bicep, Terraform o API según la cobertura. |
| **¿Qué se mueve más allá de las definiciones?** | Planificar datos, credenciales, permisos, conexiones, programaciones, vinculaciones y configuración del destino. |
| **¿Quién es responsable del destino y del resultado?** | Establecer una única vía activa de actualización de definiciones, el ETL o la actualización posterior al despliegue, la validación y las evidencias del lanzamiento. |

> **Compatible no significa completo:** las definiciones de los elementos son solo una parte de un entorno utilizable. Deben conservarse cuando sea posible, aunque el publicador elegido no pueda desplegar el elemento.

<!--
Esta lista resume los conceptos clave del README sobre las capacidades de seguimiento y despliegue de elementos y los metadatos dinámicos frente a estáticos.
Las listas de elementos compatibles evolucionan, así que conviene enlazar a las oficiales en lugar de congelar una matriz detallada en la presentación.
El seguimiento en Git y la compatibilidad del publicador son independientes: una carencia de publicación no implica que no haya Git o historial de versiones.
Bicep y ARM cubren sobre todo el plano de control de Azure, incluida la Fabric Capacity. El proveedor de Terraform para Fabric tiene más cobertura del plano de Fabric, pero también evoluciona.
Los accesos directos, las conexiones y la red privada pueden cruzar las superficies de contenido, workspace, administración de Fabric y red de Azure; conviene verificar la cobertura actual del proveedor o del API antes de elegir la ruta de IaC.
-->

---

<!-- _class: dependency-contract compact -->

# Un reto en detalle: las dependencias se convierten en lógica de despliegue

Dentro de los problemas generales de CD, las dependencias muestran por qué copiar definiciones no basta. Las referencias determinan el orden de despliegue y la parametrización.

| Referencias portables o lógicas | Referencias físicas que hay que sustituir |
|---|---|
| *Report* → *Semantic Model* mediante [`definition.pbir`](../../../data/fabric/Patterns_Report.Report/definition.pbir)<br><br>*Ontology* → ID lógico del *Lakehouse* mediante su [vinculación de datos](../../../data/fabric/Patterns_Ontology.Ontology/EntityTypes/2525121373138/DataBindings/6e4524f9-ea6d-4535-ab49-a72f73fc08a0.json)<br><br>*Data Agent* → ID lógico de la *Ontology* mediante [`datasource.json`](../../../data/fabric/Patterns_Data_Agent.DataAgent/Files/Config/draft/ontology-Patterns_Ontology/datasource.json) | Modelo Direct Lake → ruta física de OneLake en [`expressions.tmdl`](../../../data/fabric/Patterns_Semantic_Model.SemanticModel/definition/expressions.tmdl)<br><br>*Notebook* → IDs de workspace y *Lakehouse* en [`notebook-content.py`](../../../data/fabric/Import_Patterns_Data.Notebook/notebook-content.py)<br><br>DataPipeline → IDs físicos de modelo y conexiones |

```text
Fase 1:   Lakehouse ──▶ Variable Library / Notebooks / Semantic Model
          Ontology  ──▶ Data Agent

Fase 2:   Publicar los elementos dependientes salvo el DataPipeline
Fase 3:   Consultar de nuevo los IDs de Notebook/SemanticModel → publicar DataPipeline
```

<!--
Abrir los archivos enlazados si resulta útil. El Data Agent referencia directamente la Ontology, no el Lakehouse.
El Lakehouse y la Ontology son elementos base de la fase 1 para cadenas de dependencia distintas.
El SDK conserva el estado en caché durante una llamada; la fase 3 vuelve a consultar los IDs de las dependencias del DataPipeline creadas en la fase 2.
Este es un ejemplo concreto de los retos generales de la diapositiva anterior, no un tema nuevo.
-->

---

<!-- _class: divider -->
<!-- _paginate: false -->
<!-- _header: "" -->
<!-- _footer: "" -->

# Tres opciones de entrega en Fabric

## Cada una optimiza un modelo operativo distinto

---

<!-- _class: diagram -->

# Opción 1

## Pipelines de despliegue de Fabric

![bg right:46% contain](../../../assets/es/fabric-deployment-pipelines-flow.svg)

**Puntos fuertes**

- Interfaz del portal, automatización por API REST, comparación e historial
- El menor coste de configuración
- Despliegue completo o selectivo
- Reglas de despliegue y enlace automático

**Contrapartidas**

- Git no es necesariamente el origen directo de Test y Prod
- Topología de etapas lineal
- Las reglas no cubren todos los valores propios del destino
- El despliegue selectivo por API exige planificar las dependencias

**Encaje ideal:** operaciones nativas de Fabric con poca automatización propia.

<!--
Los pipelines de despliegue están disponibles desde el portal de Fabric y desde las API REST. Las API pueden crear y gestionar pipelines, asignar workspaces a etapas, desplegar el contenido de una etapa e inspeccionar operaciones.
Conviene tratar las API como la superficie de automatización de esta opción, no como una cuarta opción de entrega.
-->

---

<!-- _class: diagram -->

# Opción 2

## Integración de Git de Fabric en todas las etapas

![bg right:46% contain](../../../assets/es/git-based-deployments-flow.svg)

**Puntos fuertes**

- Fabric Git representa directamente todas las etapas
- Un único modelo de ramas y PR para desarrollo y promoción
- Sin biblioteca de despliegue aparte

**Contrapartidas**

- La sincronización con Fabric Git pasa a formar parte de la ruta de despliegue a producción
- Todos los workspaces de destino deben estar conectados a Fabric Git y gobernados
- Algunos clientes reportan cambios de definición generados por la plataforma o sin significado semántico («*ghost commits*»)
- Las ramas de larga duración, la desviación y las vías de actualización en conflicto aumentan la complejidad operativa

**Encaje ideal:** equipos cómodos operando todas las etapas con la integración de Git de Fabric.

<!--
Presentar los «ghost commits» como una preocupación comunicada por clientes y equipos de campo, no como una afirmación oficial universal de la plataforma:
algunos clientes reportan cambios de definición sin significado semántico o generados por la plataforma en el control de código fuente.
-->

---

<!-- _class: diagram -->

# Opción 3

## Despliegue basado en Git: Dev con Fabric Git y API para Test y Prod

![bg right:48% contain](../../../assets/es/fabric-git-actions-deployments-flow.svg)

**Puntos fuertes**

- Dev puede seguir sincronizado con Fabric Git para desarrollar
- Test y Prod se despliegan desde ramas de etapa mediante API
- Parametrización en el momento de la compilación
- Aprobaciones, secretos y registros de la plataforma de CI/CD
- El despliegue, el ETL y la validación pueden encadenarse

**Contrapartidas**

- La mayor responsabilidad de ingeniería
- El equipo se hace cargo de la identidad, el diagnóstico y la gestión de fallos
- La compatibilidad de herramientas y API sigue variando
- Desplegar el estado completo puede ser más lento que una diferencia pequeña

**Encaje ideal:** equipos que necesitan repetibilidad y control de la configuración.

<!--
La opción 3 puede usar un entorno de compilación en todas las etapas. Este repositorio usa una variante de desarrollo y lanzamiento basada en Git:
Dev está sincronizado con Fabric Git; Test y Prod se despliegan por API.
Esta separación no es un híbrido de varios publicadores. El publicador predeterminado es fabric-cicd no masivo.
Otro publicador solo es una ampliación arquitectónica opcional si se ha verificado la compatibilidad de elementos e identidades y se ha implementado la coordinación; este repositorio no incluye Pipelines de despliegue nativos.
-->

---

<!-- _class: dense -->

# Comparar los modelos operativos

| | Pipelines de despliegue | Fabric Git por etapa | Entorno de compilación / API |
|---|---|---|---|
| Origen de Test y Prod | Etapa anterior del workspace | Rama de la etapa | Rama de la etapa + configuración de despliegue |
| Comparación integrada | Etapas de Fabric adyacentes | Workspace ↔ rama conectada | Ninguna |
| Transformación en compilación | Reglas limitadas | No | **Sí** |
| Conexión de Fabric Git en Test y Prod | No | **Sí** | No |
| Esfuerzo de ingeniería | Bajo | Medio | Alto |
| Quién opera la publicación | Personas operadoras del workspace y la publicación | Responsables de la solución + de mantener el repositorio | DevOps/DevSecOps + responsables de la solución |
| Evidencia del despliegue | Historial de despliegues de Fabric; Git si se usa | Historial de Git + estado de Fabric Git del workspace | Historial de Git + registros de ejecución de CI/CD |

**Elegir según la fuente de verdad, la configuración, los elementos compatibles, la gobernanza y cuánto código de despliegue quiera mantener el equipo.**

> La automatización no elimina la necesidad de conocer Fabric: cambia dónde se codifica ese conocimiento y quién lo mantiene.

<!--
Pipelines de despliegue: reglas de Fabric, enlaces y conocimiento operativo.
Fabric Git: definiciones, ramas y estado de Git del workspace.
Compilación y API: parametrización, fases del despliegue, validación y procedimientos.
La comparación integrada no es igual en todas las columnas: los pipelines de despliegue comparan etapas adyacentes, mientras que Fabric Git compara un workspace con su rama conectada.
El historial de Git sirve para cualquier opción respaldada por Git; la fila de evidencias destaca la prueba adicional de que una revisión llegó a su destino.
-->

---

<!-- _class: dense -->

# Opción 3: `fabric-cicd` frente a las API masivas

| Aspecto | `fabric-cicd` no masivo | `fabric-cicd` masivo | API masivas directas |
|---|---|---|---|
| Transporte | API por elemento, en orden | **Masivo estricto; sustituciones dinámicas filtradas (1.4.x)** | Llamadas Bulk Import gestionadas por el cliente |
| Vinculación y parámetros | Todas las funciones de `parameter.yml` | fabric-cicd: sustituciones de `parameter.yml` y activación del conjunto de valores | Sin configuración incorporada; el cliente reescribe y configura tras importar |
| Dependencias | Orden de la biblioteca + fases del cliente | Dependencias de fabric-cicd + grupos del plan en adaptador independiente | Grafo lógico admitido; cliente: IDs físicos y orden explícito |
| Limpieza de huérfanos | `unpublish_all_orphan_items()` | Limpieza aparte; Bulk Import solo publica | Llamadas Delete Item aparte |
| Este repositorio | Tres llamadas con DataPipeline; estado actualizado | Grupos del plan; un fallo detiene las llamadas posteriores | Tres lotes: base → dependientes → DataPipeline |

**Predeterminado y recomendado:** `fabric-cicd` no masivo.

Planes experimentales. Bulk Import v1 no documenta `?beta=true`; el cliente
REST aún lo usa y no está verificado con una ejecución real.

**Vincular ≠ eliminar:** corregir referencias no borra elementos ausentes del origen.

<!--
El repositorio limita fabric-cicd a >=1.4.0,<1.5.0. El retorno a la publicación estándar por variables dinámicas anterior a 1.4 es histórico; la mera presencia de un archivo de parámetros no provoca ese retorno en 1.4.0.
Las pruebas sin conexión con fabric-cicd real y HTTP simulado comprueban las sustituciones, los resultados masivos y la ausencia de POST de definiciones estándar. No son evidencia real de las rutas masivas o con plan.
La ordenación masiva es un adaptador independiente del repositorio, no un plan nativo adjunto. Library, Import, Validation y Model son requisitos previos explícitos del DataPipeline. La muestra actual de 11 elementos tiene lotes declarados de [1,5,2] elementos y otros 3 restantes: cuatro selecciones y cuatro POST masivos de importación de definiciones esperados en el contrato sin conexión, no cuatro solicitudes HTTP totales ni evidencia real. Debe previsualizarse tras cambiar el plan o inventario. Las vinculaciones byPath del Report aún necesitan validación real.
El script REST directo obtiene primero los IDs de Lakehouse/Ontology, después el ID del modelo y, por último, publica el DataPipeline. Estos tres lotes gestionan las referencias físicas; las dependencias por ID lógico admitidas son otra capacidad del servicio.
-->

---

<!-- _class: divider -->
<!-- _paginate: false -->
<!-- _header: "" -->
<!-- _footer: "" -->

# Qué implementa este repositorio

## Dev con Fabric Git; Test y Prod con GitHub Actions

---

<!-- _class: diagram -->

# Dev usa Fabric Git; Test y Prod usan API

![bg right:52% contain](../../../assets/es/fabric-git-actions-deployments-flow.svg)

| Rama | Workspace | Entrega |
|---|---|---|
| `dev` | Dev | Integración de Git de Fabric |
| `test` | Test | GitHub Actions |
| `main` | Prod | GitHub Actions |

Una única vía activa de actualización de definiciones por workspace

- Dev lo gestiona Fabric Git.
- Las definiciones de Test y Prod se gestionan por API.
- Los trabajos seleccionados de Test/Prod crean o reutilizan las conexiones
  de Workspace Identity antes de publicar.
- GitHub inicia un único DataPipeline de Fabric: carga → validación →
  actualización nativa.

---

<!-- _class: dense -->

# El conocimiento de Fabric queda codificado en el contrato de entrega

| | Variable Libraries | `parameter.yml` |
|---|---|---|
| Se aplica | En tiempo de ejecución | Antes de subir |
| Se ocupa de | Valores que las cargas de trabajo pueden resolver de forma dinámica | IDs físicos y metadatos que no se pueden diferir |
| Ejemplos | Valores de la carga; vinculación del mínimo de pacientes en la Library | IDs de Notebook/Direct Lake; modelo y conexiones del DataPipeline |

```text
Publicación 1: Lakehouse + Ontology
Publicación 2: Variable Library + Notebooks + Semantic Model + Report + Data Agent
Publicación 3: DataPipeline (nueva consulta de IDs de Notebook/SemanticModel)
          ↓ limpieza de los huérfanos que corresponda
Después: un DataPipeline — carga → validación → actualización nativa
```

También queda codificado: el ámbito de elementos, la creación o reutilización
de conexiones de Workspace Identity, la verificación de Owner, la persistencia
de IDs solo si faltan, la búsqueda del DataPipeline por nombre, las dependencias
de éxito y el comportamiento ante fallos. Un DeploymentPlan ordena la
publicación, no las actividades de la carga de trabajo ni la configuración de conexiones.

> El *pipeline* deja de depender del conocimiento no documentado del equipo cuando ese conocimiento queda explícito y verificable en el repositorio.

---

<!-- _class: dense -->

# Cuatro rutas de despliegue

[Comparación de métodos](../README.md#elegir-un-método-de-despliegue) ·
[Flujos de trabajo](../fabric-release-process.md#flujos-de-trabajo-de-github-actions)

| `DEPLOY_METHOD` | Resultado |
|---|---|
| sin definir o `fabric-cicd` | No masivo: predeterminado y recomendado |
| `fabric-cicd-bulk` | Masivo experimental + plan interpretado por el adaptador; exige `DEPLOYMENT_PLAN_PATH` |
| `bulk` | REST directo de Bulk Import; revalidar el endpoint actual |
| `fabric-cicd-plan` | Adaptador secuencial no masivo + plan; independiente y experimental |
| cualquier otro valor | Se omiten todos los trabajos de despliegue |

ETL común tras éxito; planes solo de ordenación, no ejecución nativa.
Sin Pipelines de despliegue nativos: otro publicador exige compatibilidad
verificada de elementos/identidades y coordinación compartida del lanzamiento.

### Por qué REST directo exige más código

El cliente empaqueta definiciones, sustituye IDs, sondea importaciones, activa
conjuntos de valores y comprueba resultados por elemento. No implementa todo
`parameter.yml` ni elimina huérfanos.

---

<!-- _class: divider -->
<!-- _paginate: false -->
<!-- _header: "" -->
<!-- _footer: "" -->

# Recorrido en vivo

## Seguir un lanzamiento desde `main` hasta Prod

<!--
Pasar de la presentación a GitHub después de la siguiente diapositiva de flujo.
-->

---

<!-- _class: dense -->

# Del *pull request* a un workspace utilizable

**fabric-cicd no masivo**, predeterminado; otros métodos, otros flujos.

```text
PR test → main: controles de rama + pruebas unitarias; merge/push
DEPLOY_METHOD elige publicador; entorno Prod: identidad/workspace
PAT: comprobar acceso e IDs de conexiones guardados
SP: crear/reutilizar el par WI; verificar Owner del grupo
PAT: crear variables ausentes → IDs actuales al publicador
Plantilla: revisión + autenticación → script + parameter.yml → API
3 llamadas de publicación → limpieza de huérfanos
Éxito → ETL inicia/sondea DataPipeline; controles de lanzamiento aparte
```

### Archivos que seguir

1. [`enforce-promotion-path.yml`](../../../.github/workflows/enforce-promotion-path.yml): exige `test → main`.
2. [`run-tests.yml`](../../../.github/workflows/run-tests.yml): dependencias y pytest en cada PR.
3. [`deploy-prod.yml`](../../../.github/workflows/deploy-prod.yml): ruta estándar seleccionada, destino Prod.
4. [`reusable-deploy-fabric-cicd.yml`](../../../.github/workflows/reusable-deploy-fabric-cicd.yml): comprobaciones, conexiones, IDs y publicación.
5. [`deploy_fabric_cicd_non_bulk.py`](../../../scripts/deploy_fabric_cicd_non_bulk.py): fases y limpieza de huérfanos.
   - [`parameter.yml`](../../../data/fabric/parameter.yml): sustituye IDs de workspace/elementos antes de publicar.
6. [`reusable-fabric-etl.yml`](../../../.github/workflows/reusable-fabric-etl.yml): `run-etl` dependiente; inicia el DataPipeline solo tras publicar con éxito.

---

<!-- _class: dense -->

# La gobernanza aparece en cada paso

| Paso | Control |
|---|---|
| Promover a `main` | Reglas de rama, comprobaciones de estado y origen permitido |
| Seleccionar el despliegue | Variable de repositorio `DEPLOY_METHOD` |
| Entrar en Prod | Secretos del entorno de GitHub y revisores opcionales |
| Gestionar las conexiones de Fabric | Service principal de despliegue de ámbito de entorno |
| Guardar los IDs de conexión | PAT de GitHub de ámbito de entorno |
| Ejecutar las actividades | Workspace Identity de Prod |
| Ejecutar el flujo | `GITHUB_TOKEN` de solo lectura, acciones fijadas |
| Demostrar el resultado | SHA de *commit*, registros, resultado del ETL y auditoría de Fabric |

### Postura en producción

- Una identidad de despliegue por entorno siempre que sea viable
- Rol Contributor únicamente en el workspace de destino
- Restringir los despliegues a Prod a la rama `main`
- Añadir revisores de Prod donde se requiera aprobación previa al despliegue
- Evaluar OIDC de GitHub en lugar de un secreto de cliente almacenado

<!--
Antes de mostrar Settings en una sesión en vivo, volver a comprobar las reglas
de rama, la protección de los entornos y DEPLOY_METHOD. No presentar como actual
una configuración de una demostración anterior.
-->

---

<!-- _class: dense -->

# El despliegue no es el final

El trabajo dependiente `run-etl` del flujo de despliegue inicia y sondea
`Patterns_Load_Validate_And_Refresh` después de publicar correctamente, desde
la misma revisión del flujo de trabajo.

- Fabric se encarga de **carga → validación de solo lectura → actualización nativa**. No hay una segunda actualización.
- `minimum_patient_count` de la Library: política Integer positiva, valor de referencia `5`.
- `run_label` del DataPipeline: entrada String independiente, `manual` de forma predeterminada, sustituible desde CI.

```text
Publicar definiciones + vinculaciones de destino
  → éxito final del DataPipeline, incluida la actualización nativa
  → comprobaciones aparte de fechas del modelo, DAX y consumidores
```

> Verificado el 2026-10-14: conexiones de Test del método predeterminado,
> publicación y DataPipeline de la misma revisión. Prod, los publicadores
> alternativos y el ciclo Branch Out completo de la revisión actual aún
> necesitan verificación real.

<!--
El acceso al origen del propietario del modelo y las comprobaciones de fechas/DAX
de los consumidores siguen siendo independientes. La cadena needs de la misma
revisión sustituye a los flujos workflow_run de la rama predeterminada.
Los flujos ETL independientes siguen siendo herramientas manuales de recuperación;
los nombres actualizados de los flujos de despliegue evitan que los flujos
antiguos que recibían esos eventos inicien trabajos duplicados del DataPipeline
durante la transición.
-->

---

<!-- _class: compact -->

# El hilo de auditoría es el SHA del commit

| Pregunta | Evidencia |
|---|---|
| ¿Qué cambió y por qué? | Diferencia de Git, *commit*, *pull request* |
| ¿Quién lo revisó y promovió? | Historial del PR y de las reglas de rama |
| ¿Qué revisión se desplegó? | SHA de *commit* de la ejecución de Actions |
| ¿Quién autorizó el despliegue? | Revisión del entorno, cuando está habilitada |
| ¿Qué hizo la automatización? | Registros del flujo de trabajo y del script |
| ¿La preparación de datos funcionó? | Resultado del ETL |
| ¿Qué ocurrió dentro de Fabric? | Fuentes de auditoría de Fabric y de la organización |

GitHub Actions aporta evidencia del despliegue. No sustituye:

- la auditoría del workspace de Fabric;
- la validación de la calidad de los datos;
- la política de retención de registros de la organización.

---

<!-- _class: divider -->
<!-- _paginate: false -->
<!-- _header: "" -->
<!-- _footer: "" -->

# Reversión

## Las definiciones son más fáciles de revertir que los datos

---

# Llevar las definiciones a un estado correcto conocido

```text
Identificar el cambio incorrecto
  → crear un commit con git revert
  → revisarlo y promoverlo
  → ejecutar la misma ruta de despliegue
  → validar el destino
```

La reversión conserva el historial y usa los mismos controles que cualquier otro lanzamiento.

### La recuperación de datos va aparte

Git no puede deshacer las modificaciones de un *Lakehouse*, el estado de una actualización, los efectos colaterales aguas abajo ni las escrituras en sistemas externos.

Hay que planificar el reprocesamiento, las instantáneas, la retención, las capacidades de restauración a un momento dado o los procedimientos de marcha atrás propios de cada carga de trabajo.

---

<!-- _class: title compact -->
<!-- _paginate: false -->
<!-- _header: "" -->
<!-- _footer: "" -->

# Lo difícil no es subir archivos

Es reproducir una solución de Fabric que funcione, entre tipos de elemento cuyas definiciones, dependencias, vinculaciones de entorno, datos y compatibilidad con la automatización no se comportan de forma uniforme.

## Elegir de forma deliberada

- Etapas nativas de Fabric: **pipelines de despliegue**
- Etapas conectadas a Fabric Git: **Fabric Git por workspace**
- Control en la compilación: **Git + API**

## Y después hacer que el lanzamiento sea fácil de demostrar y seguro de repetir

**¿Preguntas?**

[Repositorio](https://github.com/michaeldeongreen/microsoft-fabric-sdlc-patterns)

---

<!-- _class: dense -->

# Apéndice: prácticas recomendadas y referencias

### Prácticas que conviene llevarse

- Establecer una única fuente de verdad y una única vía activa de actualización de definiciones por workspace.
- Preferir despliegues completos y repetibles; usar el despliegue selectivo solo con conciencia de las dependencias.
- Separar la entrega de elementos, la vinculación de entorno, la identidad y los permisos, y la validación de datos.
- Usar identidades de ámbito de entorno, controles de aprobación y el SHA del *commit* como hilo del lanzamiento.

**Novedad del grupo de producto de Fabric:** [centro de recursos de CI/CD](https://learn.microsoft.com/en-us/fabric/cicd/cicd-overview) · [anuncio de los recursos](https://community.fabric.microsoft.com/blog/fbc_fabricupdatesblogs/new-cicd-resources-for-microsoft-fabric-from-concepts-to-end-to-end-automation/5358502)

| Guía oficial | Este repositorio |
|---|---|
| [Planificar CI/CD para soluciones de Fabric](https://learn.microsoft.com/en-us/fabric/fundamentals/understand-best-practices-fabric-cicd)<br>[Elegir un flujo de CI/CD para Fabric](https://learn.microsoft.com/en-us/fabric/cicd/manage-deployment)<br>[Tutorial de automatización de principio a fin](https://learn.microsoft.com/en-us/fabric/cicd/tutorial-end-to-end-automation) | [Configuración](../SETUP.md)<br>[Proceso de desarrollo](../fabric-development-process.md)<br>[Proceso de lanzamiento](../fabric-release-process.md)<br>[Controles de calidad y recuperación](../fabric-cicd-quality-gates-and-release-controls.md) |
| [Parametrización de `fabric-cicd`](https://microsoft.github.io/fabric-cicd/1.4.0/how_to/parameterization/)<br>[Funciones opcionales y selectivas](https://microsoft.github.io/fabric-cicd/1.4.0/how_to/optional_feature/)<br>[Referencia de código](https://microsoft.github.io/fabric-cicd/1.4.0/reference/code_reference/) | [Implementación directa con la API masiva](../fabric-bulk-cicd-guide.md)<br>[Adaptadores de Deployment Plan](../fabric-deployment-plan-guide.md)<br>[Implementación de referencia](https://github.com/michaeldeongreen/microsoft-fabric-sdlc-patterns) |
