[English](../../TRANSLATION.md) | **Español**

# Glosario

Terminología acordada para la traducción al español de este repositorio. Es la referencia obligatoria antes de traducir cualquier documento: **la coherencia entre documentos importa más que la preferencia individual**.

> 👥 **Revisión lingüística:** [Ana Franco](https://github.com/michaeldeongreen/microsoft-fabric-sdlc-patterns/pull/61) y [Marlon Ramos](https://github.com/michaeldeongreen/microsoft-fabric-sdlc-patterns/pull/62).
> Las entradas marcadas 👤 Revisión son decisiones suyas y **prevalecen sobre la terminología oficial de Microsoft**.

## Antes de traducir un documento nuevo

1. Lee la tabla **[Falsos amigos y trampas recurrentes](#falsos-amigos-y-trampas-recurrentes)**: son los errores que ya se detectaron una vez y que se repiten.
2. Aplica las entradas 👤 Revisión sin reabrir el debate: ya se decidieron.
3. Consulta [`GUIA-DE-ESTILO.md`](GUIA-DE-ESTILO.md) para registro (impersonal/usted) y tratamiento de anglicismos.
4. Si aparece un término nuevo, sigue [Cómo ampliar este glosario](#cómo-ampliar-este-glosario).

## Procedencia de los términos

Cada entrada lleva una marca de origen:

| Marca | Significado |
|---|---|
| 👤 **Revisión** | Decidido por revisión de un hablante nativo, **con prioridad sobre Microsoft Terminology**. Cuando el término oficial no coincide con el uso real de quien trabaja con Fabric, manda el uso real. |
| ✅ **MS** | Verificado en [Microsoft Terminology](https://learn.microsoft.com/en-us/globalization/reference/microsoft-terminology) (colección oficial `SPANISH.tbx`, 61 956 entradas). |
| 🟡 **Provisional** | No existe en Microsoft Terminology — normalmente por ser terminología reciente de Fabric. Propuesta pendiente de confirmación por un hablante nativo. |
| 📘 **Convención** | Uso establecido en documentación técnica; no procede de una fuente única. |

> 📌 **La revisión nativa tiene la última palabra.** Microsoft Terminology es el punto de partida, no la autoridad final: recoge el término *oficial*, que no siempre es el que usa quien trabaja a diario con el producto. Cuando ambos difieren, gana el uso real y la entrada se marca 👤 Revisión.

> ⚠️ **No debe tomarse terminología de `learn.microsoft.com/es-es`.** Esas páginas están traducidas automáticamente (`ms.translationtype: MT`) y son inconsistentes incluso dentro de una misma página: la de integración de Git usa «espacio de trabajo» y «workspace» en el mismo párrafo. Otro ejemplo: Learn traduce *service principal* como «principal de servicio», mientras que Microsoft Terminology establece **service principal**.

---

## Principio general: ante la duda, en inglés

Quien lee esta documentación trabaja a diario con Fabric, Git y GitHub, casi siempre con la interfaz en inglés. **Un término técnico traducido literalmente suele ser menos reconocible que el original.** El caso claro es *pipeline*: su traducción literal, «tubería», nadie la usaría para hablar de CI/CD.

Por tanto, los **tipos de elemento de Fabric y los nombres de funciones del portal se mantienen en inglés**, también en prosa corrida. Solo se traduce cuando el equivalente español está plenamente asentado y resulta transparente (*branch* → rama, *repository* → repositorio).

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
| Update from Git | **Update from Git** | 📘 Convención | Nombre del botón del portal. Cuando se habla de la **API**, sí se traduce: «Actualización desde el API de Git». |
| Git integration | **integración de Git** | 📘 Convención | Transparente y de uso general; sí se traduce. |
| Fabric capacity | **Fabric capacity** | 👤 Revisión | No se traduce. *(Pendiente de confirmación definitiva.)* |
| capacity | **capacidad** | ✅ MS | Solo en uso genérico, fuera del nombre del producto. |
| tenant | **inquilino** | ✅ MS | Forma habitual en Azure y Entra. |
| dataset | **conjunto de datos** | ✅ MS | |
| report | **informe** | ✅ MS | Como tipo de elemento de la API se mantiene `Report`. |
| dataflow | **flujo de datos** | ✅ MS | |
| item | **elemento** | ✅ MS | *Elemento de Fabric* — nunca «artículo». |


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
| release | **versión** / **lanzamiento** | ✅ MS | Según contexto. |
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
| **librería** | «la **librería** de Python» | «la **biblioteca** de Python» | *Library* es «biblioteca»; «librería» es *bookshop*. |
| **soportar** | «Fabric **soporta** estos elementos» | «Fabric **admite** estos elementos» | *Support* es «admitir» o «ser compatible con»; «soportar» es *to endure*. |

---

## Términos que NUNCA se traducen

Estos elementos no se traducen en ningún contexto, ni siquiera dentro de prosa:

- **Nombres de producto**: Microsoft Fabric, Power BI, GitHub Actions, fabric-cicd, Direct Lake, Azure
- **Tipos de elemento de Fabric**: *Lakehouse*, *Notebook*, *Semantic Model*, *Variable Library*, *Data Pipeline*, *Data Agent*, *Ontology*
- **Identificadores de la API**: `SemanticModel`, `Notebook`, `VariableLibrary`, `DataAgent`, `Ontology`, `Lakehouse`, `Report`
- **Objetos y funciones del portal**: *Branch Out*, *Update from Git*, *workspace*, *Fabric capacity*
- **Vocabulario de CI/CD**: *pipeline*, *commit*, *pull request*, *feature branch*, *Trigger*, *Service principal*
- **Nombres de rama**: `dev`, `test`, `main`, `feature/*`
- **Variables y secretos**: `FABRIC_WORKSPACE_ID`, `AZURE_CLIENT_ID`, `AZURE_TENANT_ID`, `AZURE_CLIENT_SECRET`, `DEPLOY_METHOD`
- **Valores de configuración**: `fabric-cicd`, `fabric-cicd-bulk`, `bulk`
- **Rutas y nombres de archivo**: `data/fabric/`, `scripts/workspace_swap.py`, `parameter.yml`, `deploy-test.yml`
- **Funciones y claves**: `publish_all_items()`, `unpublish_all_orphan_items()`, `find_replace`, `$workspace.$id`
- **Salida literal de herramientas y mensajes de error** — el lector los verá en inglés en su pantalla

---

## Cómo ampliar este glosario

1. Ante la duda, **se mantiene el término en inglés**. La traducción literal de un término técnico suele ser menos reconocible que el original.
2. Si existe un equivalente español asentado, se busca primero en **Microsoft Terminology**. Si el término aparece allí, se usa y se marca ✅ MS.
3. Si no aparece, se propone una traducción, se marca 🟡 Provisional y se explica el razonamiento.
4. La entrada se añade **en el mismo *pull request*** que la traducción que la motivó, para que el siguiente traductor herede la decisión.
5. Si un revisor nativo corrige un término, se actualiza la entrada y su marca pasa a 📘 Convención o ✅ MS según corresponda.

Véase también [`GUIA-DE-ESTILO.md`](GUIA-DE-ESTILO.md) para variante, registro y tratamiento de extranjerismos.
