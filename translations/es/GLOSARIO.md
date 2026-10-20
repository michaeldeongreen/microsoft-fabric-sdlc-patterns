[English](../../TRANSLATION.md) | **Español**

# Glosario

Terminología acordada para la traducción al español de este repositorio. Es la referencia obligatoria antes de traducir cualquier documento: **la coherencia entre documentos importa más que la preferencia individual**.

> 👥 **Revisión lingüística:** hablantes nativos del equipo, con confirmación terminológica adicional para los términos de producto de Fabric.
> Las entradas marcadas 👤 Revisión proceden de esa revisión y **prevalecen sobre la terminología oficial de Microsoft**.

## Antes de traducir un documento nuevo

1. Lea la tabla **[Falsos amigos y trampas recurrentes](#falsos-amigos-y-trampas-recurrentes)**: son los errores que ya se detectaron una vez y que se repiten.
2. Aplique las entradas 👤 Revisión sin reabrir el debate: ya se decidieron.
3. Consulte [`GUIA-DE-ESTILO.md`](GUIA-DE-ESTILO.md) para registro (impersonal/usted) y tratamiento de anglicismos.
4. Si aparece un término nuevo, siga [Cómo ampliar este glosario](#cómo-ampliar-este-glosario).

## Procedencia de los términos

Cada entrada lleva una marca de origen:

| Marca | Significado |
|---|---|
| 👤 **Revisión** | Decidido por revisión de un hablante nativo, **con prioridad sobre Microsoft Terminology**. Cuando el término oficial no coincide con el uso real de quien trabaja con Fabric, manda el uso real. |
| ✅ **MS** | Verificado en [Microsoft Terminology](https://learn.microsoft.com/en-us/globalization/reference/microsoft-terminology) (colección oficial `SPANISH.tbx`, 61 956 entradas). |
| 🟡 **Provisional** | No existe en Microsoft Terminology — normalmente por ser terminología reciente de Fabric. Propuesta pendiente de confirmación por un hablante nativo. |
| 📘 **Convención** | Uso establecido en documentación técnica; no procede de una fuente única. |

Las [convenciones de la actualización del 15-10-2026](#convenciones-de-la-actualización-del-15-10-2026) se acordaron en una revisión con asistencia de IA. No se atribuyen a hablantes nativos ni se marcan 👤 Revisión. Se conservan las decisiones humanas anteriores.

> 📌 **La revisión nativa tiene la última palabra.** Microsoft Terminology es el punto de partida, no la autoridad final: recoge el término *oficial*, que no siempre es el que usa quien trabaja a diario con el producto. Cuando ambos difieren, gana el uso real y la entrada se marca 👤 Revisión.

> ⚠️ **No debe tomarse terminología de `learn.microsoft.com/es-es`.** Esas páginas están traducidas automáticamente (`ms.translationtype: MT`) y son inconsistentes incluso dentro de una misma página: la de integración de Git alterna «espacio de trabajo» y «área de trabajo» en el mismo párrafo, y traduce *service principal* como «principal de servicio», mientras que Microsoft Terminology registra «entidad de servicio». Este repositorio no usa ninguna de las dos: usa ***Service principal***.

> 🔗 **Los enlaces a documentación externa apuntan siempre al inglés** (`/en-us/`), no a `/es-es/`. La documentación en inglés es la versión de referencia, se actualiza antes y su terminología coincide con la del portal, que la mayoría usa en inglés. Enviar al lector a una versión traducida con terminología distinta de la de este glosario genera confusión sobre qué término es el correcto.

---

## Principio general: ante la duda, en inglés

Quien lee esta documentación trabaja a diario con Fabric, Git y GitHub, casi siempre con la interfaz en inglés. **Un término técnico traducido literalmente suele ser menos reconocible que el original.** El caso claro es *pipeline*: su traducción literal, «tubería», nadie la usaría para hablar de CI/CD.

Por tanto, los **tipos de elemento de Fabric y los nombres de objetos del portal se mantienen en inglés**, también en prosa corrida. Solo se traduce cuando el equivalente español está plenamente asentado y resulta transparente (*branch* → rama, *repository* → repositorio).

Este principio se confirmó de forma independiente en dos revisiones nativas. La primera, sobre el reconocimiento del término:

> «La traducción literal de un término técnico suele ser *menos* reconocible que el original. **Pipeline** es «tubería» y nadie diría «tubería» para hablar de CI/CD.»

La segunda, sobre la ambigüedad que introduce traducir:

> «Normalmente en español usamos los términos en inglés (la mayoría de las veces). En Fabric nos referimos a **Fabric Capacity** porque resulta confuso para el cliente, ya que usamos el mismo término para muchas cosas.»

El segundo motivo es importante y va más allá del reconocimiento: **traducir puede introducir ambigüedad donde el inglés no la tiene.** «Capacidad» se usa en español para demasiadas cosas; *Fabric Capacity* designa una sola.

### Dónde está el límite

«Ante la duda, en inglés» aplica a **nombres propios de producto**, no al vocabulario técnico corriente. La prueba es si el término designa *una cosa concreta dentro de una interfaz* o *un concepto general del desarrollo de software*:

| | Criterio | Decisión | Ejemplos |
|---|---|---|---|
| **Nombre de producto o función** | Designa un objeto concreto del portal; se busca por ese nombre en la interfaz | **Inglés** | *Lakehouse*, *Notebook*, *Semantic Model*, *Variable Library*, *Branch Out*, *workspace*, *Fabric Capacity*, *Service principal*, *Trigger*, *pipeline* |
| **Vocabulario técnico general** | Concepto del desarrollo de software, no propiedad de ningún producto | **Español** | despliegue, entorno, rama, repositorio, flujo de trabajo |
| **Texto literal de la interfaz** | Cadena exacta sobre la que hay que hacer clic | **Inglés, sin alterar** | `Settings → Environments`, `Settings → Secrets and variables → Actions → Variables` |

La tercera fila es la que concilia las dos primeras. El concepto va en español y la ruta que hay que pulsar va en inglés, en la misma frase:

> «Cree dos entornos de GitHub en la configuración del repositorio (`Settings → Environments`)»

Así se entiende la idea en español y se encuentra el botón en la interfaz.

> **Resuelto en revisión (28-09-2026).** Los cinco términos de la fila central se mantienen en español. La evidencia es directa: aparecen 57 veces en el `README.md` que revisaron dos hablantes nativos, y quien editó el texto reescribió las dos frases que los contienen —cambió «implementar despliegues» por «despliegues» y corrigió el género de *pipeline*— **sin tocar ninguno de los cinco**. En esa misma revisión sí se corrigieron «área de trabajo», «entidad de servicio», «canalización» y el tuteo, de modo que no fue falta de atención: se estaba revisando terminología activamente. Coincide además con la documentación en español de GitHub, que usa «flujo de trabajo» para los *workflows* de Actions.

---

## Fabric y Power BI

| Inglés | Español | Origen | Notas |
|---|---|---|---|
| workspace | ***workspace*** | 👤 Revisión | **No se traduce.** Microsoft Terminology ofrece «área de trabajo», pero la revisión nativa determinó que quien trabaja con Fabric usa «workspace». Prevalece el uso real sobre la terminología oficial. |
| Lakehouse | ***Lakehouse*** | 👤 Revisión | **No se traduce.** Microsoft Terminology ofrece «almacén de lago de datos», pero no es reconocible para quien trabaja con Fabric. |
| Notebook | ***Notebook*** | 📘 Convención | **No se traduce.** «Cuaderno» no se usa en este contexto. |
| Semantic Model | ***Semantic Model*** | 📘 Convención | **No se traduce.** Tipo de elemento de Fabric. |
| Variable Library | ***Variable Library*** | 📘 Convención | **No se traduce.** Tipo de elemento de Fabric. |
| Data Pipeline | ***Data Pipeline*** | 📘 Convención | **No se traduce.** Tipo de elemento de Fabric. |
| Data Agent | ***Data Agent*** | 📘 Convención | **No se traduce.** Tipo de elemento de Fabric. |
| Ontology | ***Ontology*** | 📘 Convención | **No se traduce.** Tipo de elemento de Fabric. |
| Deployment Pipelines | ***Pipelines* de despliegue** | 👤 Revisión | Microsoft Terminology ofrece «canalizaciones de implementación», pero **«canalización» no se entiende** en este contexto. Se mantiene *pipeline* y se traduce solo el complemento. En singular: «*Pipeline* de despliegue de Fabric». |
| Branch Out | **Branch Out** | 📘 Convención | Función del portal de Fabric; no se traduce. |
| Update from Git | **Actualización desde Git** | 👤 Revisión | Se traduce, tanto si designa el botón del portal como la API. Al hablar de la API: «Actualización desde el API de Git». |
| Git integration | **integración de Git** | 📘 Convención | Transparente y de uso general; sí se traduce. |
| Fabric Capacity | **Fabric Capacity** | 👤 Revisión | **No se traduce.** Confirmado en revisión terminológica: en Fabric se usa «Fabric Capacity» en inglés porque «capacidad» resulta confuso para el cliente — el mismo término se usa para muchas cosas distintas. |
| capacity | **capacidad** | ✅ MS | Solo en uso genérico, fuera del nombre del producto. |
| tenant | **inquilino** | ✅ MS | Forma habitual en Azure y Entra. |
| dataset | **conjunto de datos** | ✅ MS | |
| report | **informe** | ✅ MS | Como tipo de elemento de la API se mantiene `Report`. |
| dataflow | **flujo de datos** | ✅ MS | |
| item | **elemento** | ✅ MS | *Elemento de Fabric* — nunca «artículo». |
| ID / IDs | **ID / IDs** | 📘 Convención | Se usa la forma inglesa, no «identificador». Es la habitual en documentación técnica y coincide con los nombres de variable (`FABRIC_WORKSPACE_ID`). |
| feature | ***feature*** | 📘 Convención | Se mantiene en inglés por coherencia con *feature branch*. **No se alterna con «característica»** dentro de un mismo documento. |
| feature workspace | **workspace de feature** | 📘 Convención | Construcción española con los dos términos ingleses del glosario. |
| value set | **conjunto de valores** | 📘 Convención | Elemento de una *Variable Library*. |
| Git Sync | **Git Sync** | 📘 Convención | Nombre de la función de Fabric; no se traduce. |
| workspace drift | **desviación del workspace** (*workspace drift*) | 📘 Convención | Se glosa el término inglés en la primera aparición. |
| slash command | **comando de barra** | 📘 Convención | Transparente; se refiere a los comandos `/...` de Copilot Chat. |
| hardcoded | **definido directamente** | 👤 Revisión | Nunca «codificado». Véase «Falsos amigos». |


---

## CI/CD y control de versiones

| Inglés | Español | Origen | Notas |
|---|---|---|---|
| repository | **repositorio** | ✅ MS | |
| version control | **control de versiones** | ✅ MS | |
| source control | **control de código fuente** | ✅ MS | |
| branch *(sustantivo)* | **rama** | ✅ MS | Equivalente plenamente asentado. |
| branch *(verbo)* | **crear una rama** | ✅ MS | |
| merge | **fusionar** / **combinar** | ✅ MS | Debe elegirse una forma y mantenerse dentro del documento. |
| commit *(sustantivo)* | ***commit*** | ✅ MS | Microsoft Terminology admite «commit» además de «confirmación». Se mantiene el anglicismo por ser el uso real entre desarrolladores. En cursiva. |
| commit *(verbo)* | **hacer *commit*** / **confirmar** | ✅ MS | Nunca «commitear». |
| pull request | ***pull request*** (PR) | ✅ MS | La colección admite «pull request», «PR» y «solicitud de cambios». Se mantiene el anglicismo por ser el término de la interfaz de GitHub. Glosa en la primera aparición: «*pull request* (solicitud de cambios)». |
| deploy *(verbo)* | **desplegar** | 👤 Revisión | Se prefiere sobre «implementar» para no colisionar con *implementation*. |
| deployment | **despliegue** | 👤 Revisión | ⚠️ **No «implementación».** El inglés usa *implementation* y *deployment* con sentidos distintos que en español colisionarían. Véase «Falsos amigos». |
| implementation | **implementación** | 📘 Convención | Solo en el sentido de *implementación de referencia* o *guía de implementación*, nunca para el acto de desplegar. |
| build | **compilación** | ✅ MS | |
| release | **versión** / **lanzamiento** | ✅ MS | Según contexto: «versión» para el resultado y «lanzamiento» para el proceso. La actualización con IA del 15-10-2026 distingue «lanzamiento» de la «publicación» de definiciones; no modifica el origen de esta entrada. |
| rollback | **reversión** | ✅ MS | |
| environment | **entorno** | ✅ MS | Nunca «ambiente». |
| pipeline | ***pipeline*** | 👤 Revisión | **No se traduce nunca.** «Tubería» es la traducción literal y resulta absurda en CI/CD. **«Canalización» tampoco se usa**: no se entiende en este contexto, aunque sea el término de Microsoft Terminology. En cursiva y **en masculino**: «el *pipeline*», «los *pipelines*». |
| merge *(sustantivo, en un PR)* | ***Merge* del PR** | 👤 Revisión | Se prefiere sobre «PR fusionado» o «Fusión de PR», que suenan forzados. |
| workflow *(GitHub Actions)* | **flujo de trabajo** | 📘 Convención | El nombre del archivo (`deploy-test.yml`) no se traduce. |
| feature branch | ***feature branch*** | 📘 Convención | Nombre de metodología establecido. |
| trunk-based development | ***trunk-based development*** | 📘 Convención | |

---

## Identidad, seguridad y gobernanza

| Inglés | Español | Origen | Notas |
|---|---|---|---|
| service principal | ***Service principal*** | 👤 Revisión | **No se traduce.** Microsoft Terminology ofrece «entidad de servicio» (y Learn, «principal de servicio»), pero la revisión nativa determinó que se usa el término inglés. |
| trigger | ***Trigger*** | 👤 Revisión | **No se traduce.** «Desencadenador» resulta forzado. |
| role | **rol** | ✅ MS | |
| permission | **permiso** | ✅ MS | |
| approval | **aprobación** | ✅ MS | |
| audit | **auditoría** | ✅ MS | |
| secret | **secreto** | 📘 Convención | El nombre del secreto (`AZURE_CLIENT_ID`) no se traduce. |
| least privilege | **privilegio mínimo** | 📘 Convención | |
| branch protection | **protección de ramas** | 📘 Convención | |

---

## Falsos amigos y trampas recurrentes

Errores detectados en la revisión de la primera traducción. **Conviene revisarlos en cada documento nuevo**, porque se repiten.

| Trampa | ❌ Incorrecto | ✅ Correcto | Por qué |
|---|---|---|---|
| **equipo** | «desde el **equipo** de un desarrollador» | «desde la **laptop** de un desarrollador» | «Equipo» significa *team*. En este repositorio aparece constantemente «equipos de ingeniería», así que usarlo también para *laptop* hace que la misma palabra signifique dos cosas en una frase. Alternativas: *laptop*, *PC*, *computador*. |
| **implementación** | «método de **implementación**» | «método de **despliegue**» | El inglés distingue *implementation* (la implementación de referencia) de *deployment* (el acto de desplegar). En español colisionan. |
| **canalización** | «**canalización** de implementación» | «***pipeline*** de despliegue» | Es el término oficial de Microsoft y aun así no se entiende en contexto de CI/CD. |
| **género de *pipeline*** | «**la** *pipeline*» | «**el** *pipeline*» | *Pipeline* es masculino en español técnico. |
| **codificado** | «GUID **codificados** en sus definiciones» | «GUID **definidos directamente** en el elemento» | «Codificado» sugiere *encoded* o *cifrado*, no *hardcoded*. |
| **conmutar** | «**conmuta** el contexto del entorno» | «**alterna** el contexto del entorno» | «Conmutar» es innecesariamente técnico; *alternar* es lo natural. |
| **orden de la subordinada** | «cómo **gestiona este repositorio** ambos casos» | «cómo **este repositorio gestiona** ambos casos» | Correcto pero suena raro: el español prefiere sujeto antes del verbo en subordinadas. |
| **concordancia de género tras un cambio de término** | «de un **workspace** a otr**a**» | «de un **workspace** a otr**o**» | ⚠️ **Riesgo alto en búsqueda y reemplazo.** Al sustituir «área de trabajo» (femenino) por «workspace» (masculino), los artículos, pronombres y adjetivos cercanos **no** se actualizan solos. Tras cualquier cambio de terminología, hay que revisar la concordancia en todo el párrafo. |
| **citas textuales** | Reemplazar términos dentro de una cita de Microsoft Learn | Dejar la cita intacta | Las citas literales no se tocan, aunque usen terminología que este repositorio ha descartado. |
| **librería** | «la **librería** de Python» | «la **biblioteca** de Python» | *Library* es «biblioteca»; «librería» es *bookshop*. |
| **soportar** | «Fabric **soporta** estos elementos» | «Fabric **admite** estos elementos» | *Support* es «admitir» o «ser compatible con»; «soportar» es *to endure*. |
| **mezclar *feature* y «característica»** | «desarrollo de **características**» junto a «***feature branch***» | «desarrollo de ***features***» | Si *feature branch* se mantiene en inglés, alternar con «característica» en la misma página resulta incoherente. Debe elegirse una forma por documento. |
| **registro impersonal a medias** | «**La persona desarrolladora** crea una rama» en una lista cuyos demás pasos dicen «**Se crea**…» | «**Se crea** una rama» | Dentro de una misma lista o procedimiento, todos los pasos deben usar la misma construcción. |

---

## Términos que NUNCA se traducen

Estos elementos no se traducen en ningún contexto, ni siquiera dentro de prosa:

- **Nombres de producto**: Microsoft Fabric, Power BI, GitHub Actions, fabric-cicd, Direct Lake, Azure
- **Tipos de elemento de Fabric**: *Lakehouse*, *Notebook*, *Semantic Model*, *Variable Library*, *Data Pipeline*, *Data Agent*, *Ontology*
- **Identificadores de la API**: `SemanticModel`, `Notebook`, `VariableLibrary`, `DataAgent`, `Ontology`, `Lakehouse`, `Report`
- **Objetos y funciones del portal**: *Branch Out*, *workspace*, *Fabric Capacity*
- **Vocabulario de CI/CD**: *pipeline*, *commit*, *pull request*, *feature branch*, *Trigger*, *Service principal*
- **Nombres de rama**: `dev`, `test`, `main`, `feature/*`
- **Variables y secretos**: `FABRIC_WORKSPACE_ID`, `AZURE_CLIENT_ID`, `AZURE_TENANT_ID`, `AZURE_CLIENT_SECRET`, `DEPLOY_METHOD`
- **Valores de configuración**: `fabric-cicd`, `fabric-cicd-plan`, `fabric-cicd-bulk`, `bulk`
- **Rutas y nombres de archivo**: `data/fabric/`, `scripts/workspace_swap.py`, `parameter.yml`, `deploy-test.yml`
- **Funciones y claves**: `publish_all_items()`, `unpublish_all_orphan_items()`, `find_replace`, `$workspace.$id`
- **Salida literal de herramientas y mensajes de error** — el lector los verá en inglés en su pantalla

---

## Convenciones de la actualización del 15-10-2026

Acuerdos de redacción de la actualización asistida por IA, **sin atribuirlos a una revisión de hablantes nativos**. Se aplican a la documentación nueva o actualizada; no autorizan a cambiar citas, cadenas de interfaz, claves ni identificadores. Las filas desde «endpoint» proceden de la pasada final del 20-10-2026, igualmente asistida por IA.

| Inglés o contexto | Forma acordada | Criterio |
|---|---|---|
| Workspace Identity | **Workspace Identity** | Nombre de producto y autenticación; no se traduce. Designa una identidad: «la Workspace Identity», «las Workspace Identities»; el sustantivo *workspace* sigue siendo masculino. Las rutas de interfaz conservan su grafía exacta, como `Workspace settings -> Workspace identity`. |
| Deployment Plan / DeploymentPlan | **Deployment Plan** / `DeploymentPlan` | Nombre de producto frente a identificador del tipo de elemento. No es un Data Pipeline ni un Pipeline de despliegue. |
| client-read plan | **plan interpretado por el adaptador** | El adaptador del repositorio lee el plan y calcula el orden de publicación; Fabric no ejecuta el plan de forma nativa en estas rutas. Se evita confundir «cliente» con la empresa cliente. Los sentidos válidos de «cliente REST», «cliente OAuth» y «cliente de Microsoft» no cambian. |
| non-bulk | **sin publicación masiva**; **no masivo** como forma breve | Ambas formas designan el mismo modo de publicación. La forma breve es válida cuando el contexto es claro, especialmente en diapositivas y diagramas; no se alteran valores como `fabric-cicd`. |
| Data Pipeline / DataPipeline | **Data Pipeline** / `DataPipeline` | Tipo de elemento en prosa frente a identificador de API, ruta o configuración. Ejecuta la carga de trabajo; no promueve contenido entre workspaces. Los rótulos de diagramas con espacio limitado, como «Fabric DataPipeline» en `fabric-git-actions-deployments-flow.svg`, conservan la grafía del original. |
| Environment *(tipo de elemento de Fabric)* | **Environment** | Se conserva como tipo de producto. El concepto general y los entornos de GitHub siguen siendo «entorno»; los nombres `Dev`, `Test` y `Prod` no cambian. |
| Owner / Contributor / Admin / Member / Viewer / User | **Se conservan cuando nombran roles literales** | En instrucciones de interfaz y tablas de permisos se mantienen las etiquetas que hay que localizar. No se traducen rutas de navegación ni tipos de conector como `Power BI datasets`. |
| fine-grained PAT | ***fine-grained PAT*** (PAT de permisos específicos) | Categoría de token de GitHub; se mantiene el término reconocible con una glosa en la primera aparición. |
| preflight | **comprobaciones previas** | Describe verificaciones anteriores a una operación, no una fase de aprovisionamiento por sí misma. |
| feature-target preparation | **preparación del destino de feature** | Valida el workspace y las conexiones existentes y descubre los IDs de los elementos. No crea las conexiones ni aprovisiona la Workspace Identity. No debe confundirse con la comprobación de referencias para el PR. |
| readiness check / `--check-ready` | **comprobación de referencias para el PR** | Comprueba las referencias canónicas registradas de Dev y los conjuntos de valores permitidos. No aprovisiona recursos ni certifica toda la carga de trabajo. También se usa durante la configuración inicial de Dev. Los nombres literales de las comprobaciones de GitHub no se traducen. |
| binding | **vinculación** | Para referencias de ejecución, modelos y conexiones. «Enlace» sigue siendo válido para hipervínculos; los nombres literales como `semantic_model_binding` no cambian. |
| runtime | **en tiempo de ejecución** | En compuestos puede reformularse: «identidad de ejecución», «conexiones de ejecución». |
| framing *(Direct Lake)* | ***framing*** | Término técnico de Direct Lake. La actualización realiza el framing de las referencias Delta; no es una nueva carga de datos. Se evita el calco «creación de marcos». |
| candidate | **versión candidata** | Para una candidata de lanzamiento. No se usa «candidato» sin expresar qué objeto es. |
| release process | **proceso de lanzamiento** | Se distingue de desplegar y de publicar definiciones. |
| publish *(definiciones)* | **publicar** | La publicación no implica ejecutar la carga de trabajo, validar a quienes consumen los datos ni aprobar un lanzamiento. |
| writer *(de definiciones)* | **vía de actualización de definiciones** | Designa el mecanismo que modifica las definiciones, no al autor ni únicamente a un responsable humano. La regla es «una única vía activa de actualización de definiciones por workspace». Puede abreviarse a «vía de actualización» cuando el contexto sea claro. Los procesos que escriben datos siguen siendo «procesos de escritura». |
| quality gate / exit criterion | **control de calidad** / **criterio de salida** | Un control aplica la comprobación; el criterio especifica qué debe cumplirse para continuar. No se traducen estados literales de herramientas. |
| smoke checks | **pruebas básicas de funcionamiento** | Forma explícita y neutral, sin el calco «pruebas de humo». |
| baseline | **estado, configuración o valores de referencia** | Según el objeto. Para Dev: «configuración de referencia de Dev» o «IDs canónicos de Dev» cuando se trata específicamente de IDs. |
| connection ensure | **preparación y verificación de conexiones** | Explicitar «crea o reutiliza y verifica las conexiones» solo si la operación puede crearlas. La preparación de feature valida conexiones existentes y no las crea. |
| create-only persistence | **crear las variables que falten, sin sobrescribir valores en conflicto** | Debe expresarse el comportamiento real, no prometer una actualización incondicional. |
| fail closed | **detener la operación si falla una comprobación** | Indicar qué no se publica o sobrescribe. No implica deshacer escrituras anteriores ni que todas las fases sean de solo lectura. |
| tenant-level connections | **conexiones de ámbito de inquilino** | No se presupone que eliminarlas forme parte de borrar un workspace. |
| skill *(Copilot)* | ***skill*** | Función de Copilot; se conserva por correspondencia con el producto. No debe describirse como un antiguo archivo de prompt ni atribuirle acciones que no realiza. |
| fallback *(publicación masiva de fabric-cicd)* | **vuelta a la publicación estándar** | Expresa el cambio concreto de modo. En otras situaciones debe describirse la alternativa real; se evitan «repliegue» y «retorno». |
| foundations *(dependencias de publicación)* | **elementos base** / **dependencias previas** | No «fundaciones». Se refiere a los elementos que deben existir antes de publicar sus dependientes. |
| compromise *(seguridad)* | **vulneración de seguridad** | No «un compromiso en Test». En *sample compromise* el sentido es distinto: «simplificación deliberada del ejemplo». Esa simplificación no implica aislamiento de entornos ni una recomendación de producción. |
| endpoint | ***endpoint*** | Término técnico habitual; se escribe en cursiva en la primera aparición de cada documento. No se usa el calco «extremo». Los nombres literales, como *SQL analytics endpoint*, no cambian. |
| swap *(de referencias)* | **cambio** / **cambiar** | Reescribir las referencias físicas de Dev por las de feature y a la inversa. No se usa «intercambiar», que sugiere un intercambio mutuo. Los nombres literales, como `/swap-to-feature` o `workspace_swap.py`, no cambian. |
| live *(verificación)* | **en un entorno real** / **verificación en un entorno real** | Distingue lo comprobado en una ejecución real de lo verificado solo sin conexión. «Evidencia» se reserva para registros de auditoría o de pruebas; no se emplea como calco de *evidence* cuando basta «verificación» o «demuestra». |
| shortcut *(OneLake)* | ***Shortcut*** | Función de Fabric; se conserva el nombre de la interfaz en inglés. Los identificadores, como `ShortcutConfig`, no cambian. |
| desdoblamientos con «persona» | «usuario», «aprobadores», «operadores» o «quien…» | Se evitan formas como «persona usuaria» o «personas aprobadoras», igual que «persona desarrolladora»: mezcladas con el masculino genérico del resto del corpus resultan forzadas. Siguen siendo válidas las construcciones con adjetivos invariables, como «persona designada» o «persona responsable». |
| variantes regionales | **encabezado**, **costo**, **hacer clic en** / **seleccionar**, **vencimiento** | Español neutro: no se usan «cabecera», «coste» ni «pulsar», marcados regionalmente. Para *expiration* de credenciales se usa «vencimiento», la forma dominante del corpus. |
| fechas en prosa | **14 de octubre de 2026** | Forma larga y sin ambigüedad. Las marcas de procedencia (`2026-10-15`) y los valores de configuración conservan el formato ISO. Las etiquetas «actualización del 15-10-2026» y «20-10-2026» designan revisiones asistidas por IA. |

Estas decisiones son contextuales, no reglas de sustitución ciega. «Contenido codificado en base64» y «conocimiento codificado en un contrato» conservan el sentido correcto de *encoded*; no deben confundirse con el falso amigo de *hardcoded*.

---

## Cómo ampliar este glosario

1. Ante la duda, **se mantiene el término en inglés**. La traducción literal de un término técnico suele ser menos reconocible que el original.
2. Si existe un equivalente español asentado, se busca primero en **Microsoft Terminology**. Si el término aparece allí, se usa y se marca ✅ MS.
3. Si no aparece, se propone una traducción, se marca 🟡 Provisional y se explica el razonamiento.
4. La entrada se añade **en el mismo *pull request*** que la traducción que la motivó, para que el siguiente traductor herede la decisión.
5. Si un revisor nativo corrige un término, se registra la decisión como 👤 Revisión, con su procedencia cuando conste. Una decisión asistida por IA se identifica como tal y nunca recibe esa marca.

Véase también [`GUIA-DE-ESTILO.md`](GUIA-DE-ESTILO.md) para variante, registro y tratamiento de extranjerismos.
