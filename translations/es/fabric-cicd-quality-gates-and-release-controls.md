[English](../../fabric-cicd-quality-gates-and-release-controls.md) | **Español**

<!-- source: fabric-cicd-quality-gates-and-release-controls.md @ f7f949d | translated: 2026-10-15 -->

> La versión en inglés es la fuente autorizada. Si existe alguna discrepancia,
> [el original en inglés](../../fabric-cicd-quality-gates-and-release-controls.md)
> tiene precedencia.

# Controles de calidad y de lanzamiento de Fabric CI/CD

Esta guía propone una base de controles para lanzar cargas de trabajo de
Fabric, a partir de la documentación pública enlazada más adelante. No es una
lista de comprobación obligatoria de Microsoft ni un validador integrado para
todos los elementos.

En esta guía, desarrollo, pruebas y producción indican la finalidad de los
entornos dentro del ciclo de vida. La etapa de pruebas puede denominarse
«Certification», «UAT» o «Staging», según la organización.
Elija rutas de Git, de Pipelines de despliegue nativos o de API/biblioteca que
sean compatibles con la carga de trabajo; los pipelines nativos y Deployment
Plans no son requisitos universales.

- Comprobaciones automáticas: CI ejecuta las comprobaciones, conserva los
  resultados y bloquea el avance si fallan.
- Verificación manual: una persona realiza una comprobación obligatoria para
  la que no puede usarse automatización aprobada.
- Aprobación: un responsable autoriza un cambio o lanzamiento revisado; CI
  puede hacer cumplir esa decisión, pero no sustituirla.
- Excepciones: registre el responsable, el ámbito afectado, el riesgo, la
  mitigación y el vencimiento. La ausencia de evidencias, las comprobaciones
  omitidas y los fallos de autenticación no equivalen a pruebas superadas.

## Contenido

- [Controles por etapa](#1-controles-de-calidad-por-etapa)
- [Comprobaciones por artefacto](#2-comprobaciones-por-artefacto)
- [Pruebas automáticas esenciales](#3-pruebas-automáticas-esenciales)
- [Aprobaciones y controles de lanzamiento](#4-aprobaciones-y-controles-de-lanzamiento)
- [Inventario de compatibilidad y excepciones](#5-inventario-de-compatibilidad-y-excepciones)
- [Gestión de fallos y recuperación](#6-gestión-de-fallos-y-recuperación)
- [Patrones empresariales y referencias](#7-patrones-empresariales-y-referencias)

## 1. Controles de calidad por etapa

Aplique los controles a la carga de trabajo modificada y a sus dependencias.
Acuerde los resultados esperados y los umbrales de bloqueo antes del
lanzamiento; no deduzca que está listo solo porque se haya publicado.

### En el PR o la revisión del código fuente

- Comprobaciones automáticas: valide las definiciones versionadas, las
  referencias de entorno permitidas, la calidad del código y las pruebas
  unitarias aplicables; busque credenciales guardadas en el código fuente.
- Revisión manual: evalúe la lógica de negocio, las dependencias, los cambios
  de permisos y los cambios destructivos de esquema o datos. Exija los
  revisores pertinentes mediante la protección de ramas.
- Criterio de salida: se superan las comprobaciones y revisiones de PR
  obligatorias. Aprobar el PR no autoriza el despliegue en producción.

### Antes del despliegue en cada destino

- Comprobaciones automáticas: inventaríe los elementos y confirme la
  compatibilidad de la ruta, la versión y la identidad; verifique el workspace
  de destino, la Fabric Capacity, los recursos previos, las conexiones y la
  configuración efectiva del entorno.
- Verificación manual: resuelva las comprobaciones sin automatización
  compatible. Los responsables de la plataforma aprueban el acceso y la
  configuración previos; las eliminaciones significativas y los cambios
  incompatibles requieren una revisión del riesgo.
- Criterio de salida: el ámbito previsto, el destino, las dependencias y la
  configuración son válidos. Repita las comprobaciones previas para
  producción; no vuelva a crear recursos existentes solo para validarlos.

### Después del despliegue en Test y antes de la promoción a producción

- Comprobaciones automáticas: confirme que la publicación y la configuración
  terminaron correctamente; después, ejecute los recorridos críticos de la
  carga de trabajo y las pruebas de esquema, calidad de datos, resultados de
  negocio y acceso de los consumidores.
- Verificación manual: realice las comprobaciones necesarias de los
  recorridos de los consumidores que no tengan automatización conforme a las
  políticas. Los responsables de negocio aportan evidencias de UAT/aceptación
  para los cambios significativos de comportamiento.
- Criterio de salida: los resultados corresponden a esta versión candidata,
  no a una definición anterior. Los fallos de despliegue o de comprobaciones
  en tiempo de ejecución, y la ausencia de evidencias de aceptación
  obligatorias, bloquean la promoción.

### Antes y durante el despliegue en producción

- Comprobaciones automáticas: verifique la versión candidata aprobada y las
  comprobaciones previas de producción; haga cumplir el acceso protegido al
  despliegue y los
  [controles de lanzamiento](#4-aprobaciones-y-controles-de-lanzamiento).
- Comprobaciones automáticas: valide las vinculaciones desplegadas antes de
  habilitar procesos de escritura o programaciones nuevos o modificados.
- Aprobación manual: el responsable designado del lanzamiento revisa las
  evidencias de Test, el ámbito, el riesgo y la preparación para la
  recuperación. Añada la aprobación de especialistas o una aprobación
  independiente de activación cuando el riesgo lo justifique.
- Criterio de salida: la autorización cubre esta versión candidata y este
  destino; todas las operaciones obligatorias de publicación y configuración
  terminan correctamente. El lanzamiento aún no está completo.

### Después del despliegue en producción

- Comprobaciones automáticas: verifique las vinculaciones reales, las
  conexiones, la configuración activa, la disponibilidad de los datos
  necesarios y los recorridos críticos de los consumidores. Use datos
  existentes aprobados y pruebas básicas de funcionamiento de solo lectura;
  nunca cargue datos de ejemplo en tablas de negocio para validar.
- Verificación manual: registre evidencias de las comprobaciones esenciales
  para las que no pueda usarse automatización aprobada.
- Criterio de salida: registre el estado de referencia correcto de producción
  solo cuando se superen las pruebas básicas obligatorias. En caso contrario,
  mantenga el lanzamiento incompleto y decida qué medidas de gestión del
  fallo y recuperación deben aplicarse.

## 2. Comprobaciones por artefacto

En el PR se inspeccionan las definiciones y el código fuente. Después de la
publicación, se inspecciona la configuración efectiva del destino. Ejecute
las pruebas de la carga de trabajo en Test y un subconjunto adecuado de
pruebas básicas de funcionamiento en producción. Automatice cuando lo
permitan la API y la identidad; para las carencias, conserve evidencias
manuales o una excepción aprobada.

### Variable Libraries

- Verifique que el conjunto de valores activo y los valores resueltos por un
  consumidor apunten a IDs de workspace y de elemento aprobados. Compruebe
  también las vinculaciones literales: un conjunto de valores no reescribe
  todas las definiciones.
- Un despliegue nativo en una etapa vacía activa `Default`. Configure y valide
  el conjunto activo previsto antes de ejecutar; no suponga que la comparación
  de Git o del despliegue transfiere esa configuración del workspace.
  [Guía del ciclo de vida](https://learn.microsoft.com/en-us/fabric/cicd/variable-library/variable-library-cicd).

### Data Pipelines

- Valide la estructura de la definición, las conexiones, los parámetros y las
  referencias a dependencias frente a la configuración del destino.
- Ejecute los recorridos críticos con entradas controladas de Test; compruebe
  el estado final, la gestión de fallos y las salidas esperadas. Verifique la
  identidad usada en tiempo de ejecución para el origen y el destino, no solo
  el acceso de quien despliega.
  [Conexiones](https://learn.microsoft.com/en-us/fabric/data-factory/data-source-management).
- En este ejemplo, las actividades de Notebook y de actualización requieren
  conexiones con autenticación Workspace Identity. Verifique el tipo de
  conector, la autenticación Workspace Identity, el workspace de destino, el
  rol Owner del grupo de administradores de conexiones, las sustituciones
  físicas del Semantic Model y del workspace, el mínimo de tipo Integer
  positivo de la Variable Library activa y la etiqueta de ejecución
  independiente de tipo String. El Service principal de despliegue publica
  e inicia el DataPipeline, pero no es la identidad de ejecución de las
  actividades.

### Notebooks y entornos de Spark

- Analice el código fuente con herramientas de calidad y pruebe la lógica
  reutilizable mediante pruebas unitarias; verifique la referencia al
  Lakehouse, los parámetros, el entorno de ejecución publicado y las
  bibliotecas.
- Ejecute en Test y compruebe las tablas, los archivos y los resultados
  esperados. Inspeccione las vinculaciones resueltas en lugar de reescribir
  todos los GUID; puede haber compatibilidad con vinculaciones lógicas.
  [Ciclo de vida de Notebook](https://learn.microsoft.com/en-us/fabric/data-engineering/notebook-source-control-deployment).

### Lakehouses

- Tras la ingesta o transformación prevista, lea las salidas existentes para
  verificar las tablas necesarias, los tipos de columna, las claves, los
  shortcuts, los recuentos y los totales conciliados.
- Git registra metadatos, no los esquemas físicos de las tablas ni sus datos.
  Versione el esquema esperado y la carga de trabajo que lo crea; no añada
  columnas ni modifique datos solo para validar.
  [Ciclo de vida de Lakehouse](https://learn.microsoft.com/en-us/fabric/data-engineering/lakehouse-git-deployment-pipelines).

### Warehouses

- Valide las dependencias de SQL y de objetos, y compare el esquema desplegado
  con el contrato revisado. Compile y compare un proyecto SQL cuando ese sea
  el flujo de trabajo elegido.
- Pruebe las vistas y los procedimientos críticos con entradas controladas en
  Test; las consultas básicas de producción siguen siendo de solo lectura.
  Los objetos ausentes, las referencias no válidas y los resultados
  incorrectos hacen fallar la comprobación.
  [Desarrollo y despliegue](https://learn.microsoft.com/en-us/fabric/data-warehouse/development-deployment).

### Semantic Models e informes

- Compruebe la estructura, las conexiones, las relaciones y las medidas
  críticas; revise los objetos visuales y las métricas modificados. Los
  ejemplos de comprobación estática usan herramientas como Tabular Editor
  Best Practice Analyzer y PBI Inspector, no un validador universal de Fabric.
  [Ejemplo de validación](https://learn.microsoft.com/en-us/power-bi/developer/projects/projects-build-pipelines).
- Para Semantic Models de Import, espere a que la actualización termine
  correctamente antes de comprobar los resultados. Para Direct Lake, espere
  al [framing](https://learn.microsoft.com/en-us/fabric/fundamentals/direct-lake-how-it-works#framing)
  necesario después del ETL de origen y consulte después los datos actuales
  previstos. El framing no es otro ETL ni una copia de datos, y su finalización
  correcta no valida DAX ni el acceso de los consumidores. Pruebe los cálculos
  y la seguridad con las identidades de consumidor compatibles descritas más
  adelante.
  [API de actualización](https://learn.microsoft.com/en-us/rest/api/power-bi/datasets/refresh-dataset-in-group).

### Dataflows Gen2

- Asegúrese de que la definición candidata se publique mediante la ruta de
  CI/CD compatible antes de actualizar los datos; actualizar una definición
  anterior no valida este lanzamiento.
- Espere a que termine la actualización y compruebe los tipos de destino, los
  recuentos, los valores obligatorios y los errores o advertencias pertinentes.
  Confirme la compatibilidad de identidad del elemento y de la API.
  [Ciclo de vida](https://learn.microsoft.com/en-us/fabric/data-factory/dataflow-gen2-cicd-and-git-integration)
  y [API de trabajos](https://learn.microsoft.com/en-us/fabric/data-factory/dataflow-gen2-public-apis).

### Data Agents de Fabric

- Verifique los orígenes aprobados y las relaciones de Ontology cuando se
  usen. Evalúe el agente publicado en Test con acceso compatible de nivel de
  consumidor.
- Exija que cada caso crítico de respuesta conocida y de denegación de acceso
  se supere individualmente; inspeccione las consultas generadas. Un resultado
  de publicación o una puntuación media favorable de IA no bastan por sí
  solos. Las herramientas de evaluación están en versión preliminar: valide
  su versión y su compatibilidad con la identidad.
  [Guía de evaluación](https://learn.microsoft.com/en-us/fabric/data-science/evaluate-data-agent).

## 3. Pruebas automáticas esenciales

Las pruebas basadas exclusivamente en los archivos del repositorio se ejecutan
en el PR. Las pruebas de integración, datos y consumidores se ejecutan después
del despliegue en Test y antes de la promoción a producción; las pruebas
básicas de funcionamiento verifican el resultado en producción.

- Suite de referencia: comprobaciones de definiciones y referencias,
  compatibilidad de esquema, ejecución crítica de extremo a extremo,
  resultados esperados de negocio y datos determinados de forma independiente,
  configuración efectiva y acceso permitido y denegado de los consumidores.
- Pruebas unitarias: cubren el código reutilizable modificado, las entradas no
  válidas, los límites y las regresiones; complementan las pruebas en tiempo
  de ejecución de Fabric, pero no las sustituyen.
- Pruebas de repetición: para los procesos de escritura, repita una entrada
  controlada de Test y exija el resultado idempotente previsto, sin duplicados.
- Pruebas de rendimiento: para las consultas, actualizaciones o procesos ETL
  críticos afectados, compare los objetivos o valores de referencia acordados
  en condiciones representativas de datos y Fabric Capacity fuera de
  producción.
- Pruebas de consumidores: use la autenticación aprobada del usuario previsto.
  La RLS del Semantic Model no se aplica a las identidades con los roles
  Admin, Member o Contributor en el workspace; la identidad de despliegue no
  sustituye al usuario.
  [Comportamiento de RLS](https://learn.microsoft.com/en-us/fabric/security/service-admin-row-level-security).
- Límites de acceso: verifique los resultados permitidos y denegados en cada
  recorrido pertinente de Semantic Model, informe, SQL, OneLake y agente. La
  RLS del Semantic Model no protege por sí sola el acceso directo a los datos;
  un inicio de sesión fallido o un tiempo de espera agotado no constituye una
  prueba de denegación superada.
  [Modelo de permisos](https://learn.microsoft.com/en-us/fabric/security/permission-model).
- Power BI Execute Queries no puede usar Service principals con Semantic
  Models que tengan RLS o SSO habilitados. Use una ruta compatible basada en
  usuarios o una verificación manual registrada; nunca debilite MFA ni el
  acceso condicional para que funcione la automatización.
  [Limitaciones de la API](https://learn.microsoft.com/en-us/rest/api/power-bi/datasets/execute-queries).
- Comprobaciones del sistema de pruebas: espere al estado final correcto
  específico de cada operación, trabajo o actualización, e inspeccione los
  resultados por elemento y los errores del cuerpo de respuesta. CI debe
  fallar ante resultados obligatorios fallidos o ausentes, cancelación, tiempo
  de espera agotado o comprobaciones incumplidas; aceptar una solicitud,
  registrar errores u omitir comprobaciones no equivale a superar la prueba.
  [API de trabajos](https://learn.microsoft.com/en-us/rest/api/fabric/core/job-scheduler/run-on-demand-item-job).

## 4. Aprobaciones y controles de lanzamiento

### Autorización humana

- Haga cumplir las aprobaciones de despliegue mediante
  [entornos de GitHub](https://docs.github.com/en/actions/how-tos/deploy/configure-and-manage-deployments/manage-environments)
  protegidos o
  [comprobaciones de recursos de Azure DevOps](https://learn.microsoft.com/en-us/azure/devops/pipelines/process/approvals?view=azure-devops),
  fuera de la lógica de despliegue editable. Verifique la disponibilidad de
  esas funciones y restrinja la autoaprobación y la omisión de controles.
- Asigne responsables de aprobación según el riesgo; no todos los cambios
  rutinarios requieren revisión de arquitectura, negocio o seguridad.
- Si se enumeran varios revisores en un entorno de GitHub, basta con una
  aprobación. Si la política exige varias aprobaciones independientes,
  configure controles adicionales que se puedan hacer cumplir.

### Identidad de la versión candidata y evidencias

- Vincule la aprobación a la instantánea exacta del código fuente, los
  elementos seleccionados, el destino, los resultados de Test y las
  sustituciones de entorno revisadas. Cambiar la versión candidata invalida
  las evidencias y la autorización anteriores.
- Para lanzamientos basados en archivos, conserve el paquete de definiciones
  probado, el commit de origen, la versión de la herramienta y la suma de
  comprobación del paquete antes de las sustituciones. Producción consume el
  mismo paquete y verifica su identidad; no lo reconstruya desde una copia
  más reciente del repositorio.
- Para los pipelines nativos, inmovilice y revise el contenido de la etapa
  de origen, y conserve el inventario de origen y destino, el
  [registro de la operación de despliegue](https://learn.microsoft.com/en-us/rest/api/fabric/core/deployment-pipelines/get-deployment-pipeline-operation)
  con los resultados por elemento y los resultados de las pruebas. Registre
  el SHA de Git sincronizado cuando corresponda. El historial de operaciones
  no es un hash del paquete ni una copia de seguridad de las definiciones.
- Use etiquetas de lanzamiento protegidas y versionadas cuando corresponda,
  no etiquetas de PR ni una etiqueta `prod` que cambie de destino. Verifique
  los SHA registrados; conserve las definiciones y las evidencias de un estado
  correcto más allá del vencimiento de los artefactos de CI.

### Ejecución y finalización

- En el
  [seguimiento compartido de Test/Prod](fabric-release-process.md#actualización-del-semantic-model-posterior-al-etl)
  de este repositorio, GitHub solo inicia y consulta el estado de
  `Patterns_Load_Validate_And_Refresh`. Fabric controla la carga -> validación
  de solo lectura -> actualización nativa; si falla la validación, se omite
  la actualización, y si falla la actualización, falla el pipeline. No se ha
  conectado ningún mecanismo alternativo externo de actualización ni un
  segundo ETL. Las comprobaciones de esquema, claves, referencias, fechas del
  origen y mínimo de pacientes no son la suite completa de validación del
  Semantic Model, los resultados de negocio o los consumidores.
- La espera del trabajo de pipeline está limitada a 60 minutos; los límites
  de las actividades de carga, validación y actualización son de 20, 10 y
  10 minutos, respectivamente. Que GitHub agote el tiempo de consulta no
  cancela el trabajo en el servidor. Compruebe el pipeline, la actividad y el
  historial de actualización concretos antes de reintentar; un flujo de
  trabajo fallido puede dejar tareas en ejecución.
- Comparta una política de bloqueo o concurrencia entre todas las rutas
  dirigidas al mismo workspace; manténgala durante el despliegue, la ejecución
  obligatoria de la carga de trabajo y las pruebas básicas de funcionamiento.
  No interrumpa un lanzamiento en curso con otro que compita con él.
- Limite las escrituras en producción a las identidades operativas o de
  despliegue aprobadas. Mantenga los secretos fuera del código; separe el
  acceso de despliegue, de ejecución y de los consumidores. Véanse las
  [Consideraciones de gobernanza](fabric-cicd-governance-considerations.md)
  para los controles de identidad.
- Prefiera OIDC o la federación de identidades de carga de trabajo para CI
  cuando sean compatibles; limite la confianza y las políticas de ramas de
  despliegue, y verifique los permisos de Fabric. Este repositorio usa
  actualmente autenticación con secreto de cliente; el
  [ejemplo de OIDC está previsto](https://github.com/michaeldeongreen/microsoft-fabric-sdlc-patterns/issues/84).
- Conserve las aprobaciones, la configuración de destino, los resultados por
  elemento, los IDs de trabajo, actualización y prueba, las eliminaciones y
  los enlaces de ejecución, con acceso restringido y resultados enmascarados.
  Mantenga separados los intentos fallidos o parciales del último lanzamiento
  de producción completamente validado.

### Demostración breve de un fallo

Use un destino de feature aislado o un destino aprobado fuera de producción,
con datos de ejemplo desechables, no producción: el proceso de carga de este
pipeline escribe en las tablas del ejemplo.

1. Registre el `minimum_patient_count` de la Variable Library activa y
   auméntelo por encima del recuento de pacientes observado, manteniéndolo
   como Integer positivo. Ejecute el pipeline.
2. Confirme que falle la actividad de validación y se omita la actualización
   nativa. Inspeccione el umbral recibido y el `run_label` independiente; no
   exija recuentos exactos de los datos iniciales en el control de ejecución.
3. Restaure el mínimo original y vuelva a ejecutar una vez. Exija la
   finalización real de la actualización nativa y, por separado, consulte los
   campos de fecha del Semantic Model y compruebe los resultados de los
   consumidores.

Esto demuestra la diferencia entre una política de entorno y una entrada por
ejecución, no una certificación empresarial. El lanzamiento predeterminado
de fabric-cicd en Test se ha verificado con una ejecución real que abarca la
preparación de conexiones, la publicación y el DataPipeline de la misma
revisión. Prod, los tres publicadores alternativos, Branch Out de la revisión
actual, los resultados de negocio del Semantic Model y los informes, y el
acceso de los consumidores siguen siendo controles independientes. Véase la
[matriz de verificación](fabric-release-process.md#estado-de-la-verificación).

## 5. Inventario de compatibilidad y excepciones

La compatibilidad depende de la ruta de despliegue, el subtipo de elemento, la
versión de la herramienta, la identidad y el estado de versión preliminar.
La disponibilidad de una API REST no demuestra por sí sola que un elemento
admita el despliegue de sus definiciones.

- Inventario automático: enumere el workspace real mediante
  [List Items](https://learn.microsoft.com/en-us/rest/api/fabric/core/items/list-items),
  recorra todas las páginas de continuación y concilie los elementos con las
  definiciones de origen o las excepciones aprobadas. Las carpetas de Git
  por sí solas no incluyen los elementos que Git no exporta.
- Confirme la visibilidad del inventario y complételo con API específicas de
  la carga de trabajo cuando sea necesario. Los fallos de autenticación o
  permisos, un inventario incompleto y las respuestas `403` no demuestran que
  un elemento no sea compatible.
- Mantenga una tabla revisada de compatibilidad por tipo y subtipo, basada
  en las listas de
  [Git](https://learn.microsoft.com/en-us/fabric/cicd/git-integration/intro-to-git-integration#supported-items),
  [pipelines nativos](https://learn.microsoft.com/en-us/fabric/cicd/deployment-pipelines/intro-to-deployment-pipelines#supported-items)
  y [fabric-cicd](https://microsoft.github.io/fabric-cicd/latest/). Registre las
  versiones probadas de las herramientas, las identidades y la ruta elegida;
  revise la tabla al actualizar herramientas o cambiar tipos.
- Control automático: exija una ruta aprobada para cada elemento incluido
  en el ámbito, no compatibilidad con los tres mecanismos. Bloquee los tipos
  desconocidos, los requisitos previos ausentes y las excepciones vencidas o
  sin aprobar.
- Excepción manual: indique la ruta alternativa, el responsable, las
  evidencias necesarias y el vencimiento. Que una ruta no admita un elemento
  no significa que no pueda usarse en Fabric; nunca lo omita en silencio.

## 6. Gestión de fallos y recuperación

- Detenga cualquier promoción posterior cuando fallen las comprobaciones
  obligatorias; registre el estado parcial y avise al responsable. El
  despliegue de Fabric no es una transacción de todo el workspace, y rechazar
  una aprobación posterior no deshace los cambios publicados.
- Reversión de definiciones: autorice un nuevo despliegue selectivo del
  contenido y la configuración conservados de un estado correcto. Compruebe
  la compatibilidad con los datos y el esquema actuales y revise el
  comportamiento de eliminación; el contenido actual de Test no tiene por
  qué ser el lanzamiento anterior de producción.
  [Guía de recuperación del ciclo de vida](https://learn.microsoft.com/en-us/fabric/cicd/best-practices-cicd).
- Recuperación de datos: una reversión de Git o de definiciones no restaura
  datos. Antes de cambios arriesgados, registre versiones recuperables de
  Delta o puntos de restauración de Warehouse, y las posiciones pertinentes
  de ingesta u origen —marcas de agua—; verifique el período de conservación
  para la recuperación.
- La [restauración de Delta](https://learn.microsoft.com/en-us/fabric/data-engineering/delta-lake-restore)
  usa Spark, no el SQL analytics endpoint; la
  [restauración de Warehouse](https://learn.microsoft.com/en-us/fabric/data-warehouse/restore-in-place-portal)
  sobrescribe el estado actual.
- La recuperación destructiva necesita autorización explícita. Compruebe la
  conservación, pause los procesos de escritura afectados, coordine las
  tablas dependientes y concilie o vuelva a procesar los datos legítimos
  posteriores antes de reanudar el acceso de los consumidores.
- Ensaye la recuperación en Test; mida los objetivos de tiempo de recuperación
  y pérdida de datos, y vuelva a validar la configuración, los cálculos y el
  aislamiento de los consumidores antes de registrar un resultado correcto.

## 7. Patrones empresariales y referencias

- Versione las definiciones compatibles, la configuración y los contratos de
  validación; use feature branches y comprobaciones y revisiones obligatorias
  de PR.
- Mantenga separados los workspaces de cada entorno y elija un responsable y
  una ruta de despliegue por elemento. El aislamiento de Fabric Capacity es
  una decisión independiente: las pruebas de carga fuera de producción no
  deben degradar producción.
- Los tutoriales son puntos de partida, no certificaciones de preparación
  para producción.

| Referencia pública | Para qué sirve |
|---|---|
| [Introducción a CI/CD de Fabric](https://learn.microsoft.com/en-us/fabric/cicd/cicd-overview) | Opciones de rutas de despliegue y una arquitectura de referencia de CI/CD. |
| [Planificar CI/CD para soluciones de Fabric](https://learn.microsoft.com/en-us/fabric/fundamentals/understand-best-practices-fabric-cicd) | Control de código fuente, diseño de entornos y planificación de la automatización. |
| [Prácticas recomendadas del ciclo de vida](https://learn.microsoft.com/en-us/fabric/cicd/best-practices-cicd) | Responsabilidades de desarrollo, pruebas y producción, y límites de recuperación. |
| [Elegir un patrón de despliegue de Fabric](https://learn.microsoft.com/en-us/azure/architecture/data-guide/technology-choices/fabric-deployment-patterns) | Equilibrios entre topologías de inquilinos, Fabric Capacity y workspaces. |
| [Fabric Well-Architected](https://learn.microsoft.com/en-us/azure/well-architected/microsoft-fabric/overview) | Fiabilidad, seguridad, rendimiento, costo y preparación operativa. |
| [Tutorial de fabric-cicd y Azure DevOps](https://learn.microsoft.com/en-us/fabric/cicd/tutorial-fabric-cicd-azure-devops) | Un ejemplo de automatización basada en archivos que puede ampliarse con estos controles de lanzamiento. |
| [Ejemplo de automatización de pipelines nativos](https://github.com/microsoft/fabric-toolbox/tree/main/accelerators/CICD/Deploy-using-Fabric-deployment-pipelines) | Un punto de partida alternativo con la ruta nativa, sujeto a la compatibilidad de elementos e identidades. |

---

*Este documento es una traducción de
[fabric-cicd-quality-gates-and-release-controls.md](../../fabric-cicd-quality-gates-and-release-controls.md).
El original en inglés es la fuente autorizada. Los errores pueden comunicarse
mediante una incidencia, indicando el idioma.*

*Los enlaces a documentación externa apuntan al inglés para conservar la
referencia y la terminología de la interfaz. Si se prefiere otro idioma, puede
cambiarse desde el selector de idioma del sitio de destino.*
