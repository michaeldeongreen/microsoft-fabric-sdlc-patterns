[English](../../TRANSLATION.md) | **Español**

# Glosario

Terminología acordada para la traducción al español de este repositorio. Es la referencia obligatoria antes de traducir cualquier documento: **la coherencia entre documentos importa más que la preferencia individual**.

## Procedencia de los términos

Cada entrada lleva una marca de origen:

| Marca | Significado |
|---|---|
| ✅ **MS** | Verificado en [Microsoft Terminology](https://learn.microsoft.com/en-us/globalization/reference/microsoft-terminology) (colección oficial `SPANISH.tbx`, 61 956 entradas). Es autoritativo. |
| 🟡 **Provisional** | No existe en Microsoft Terminology — normalmente por ser terminología reciente de Fabric. Propuesta pendiente de confirmación por un hablante nativo. |
| 📘 **Convención** | Uso establecido en documentación técnica; no procede de una fuente única. |

> ⚠️ **No debe tomarse terminología de `learn.microsoft.com/es-es`.** Esas páginas están traducidas automáticamente (`ms.translationtype: MT`) y son inconsistentes incluso dentro de una misma página: la de integración de Git usa «espacio de trabajo» y «área de trabajo» en el mismo párrafo. Otro ejemplo: Learn traduce *service principal* como «principal de servicio», mientras que Microsoft Terminology establece **entidad de servicio**.

---

## Principio general: ante la duda, en inglés

Quien lee esta documentación trabaja a diario con Fabric, Git y GitHub, casi siempre con la interfaz en inglés. **Un término técnico traducido literalmente suele ser menos reconocible que el original.** El caso claro es *pipeline*: su traducción literal, «tubería», nadie la usaría para hablar de CI/CD.

Por tanto, los **tipos de elemento de Fabric y los nombres de funciones del portal se mantienen en inglés**, también en prosa corrida. Solo se traduce cuando el equivalente español está plenamente asentado y resulta transparente (*branch* → rama, *repository* → repositorio).

---

## Fabric y Power BI

| Inglés | Español | Origen | Notas |
|---|---|---|---|
| workspace | **área de trabajo** | ✅ MS | Equivalente asentado y transparente. Definición coincidente: *"A container of Power BI content… designed for collaboration"*. No se usa «espacio de trabajo», que en la terminología de Microsoft designa otro concepto. |
| Lakehouse | ***Lakehouse*** | 📘 Convención | **No se traduce.** Microsoft Terminology ofrece «almacén de lago de datos», pero no es reconocible para quien trabaja con Fabric. |
| Notebook | ***Notebook*** | 📘 Convención | **No se traduce.** «Cuaderno» no se usa en este contexto. |
| Semantic Model | ***Semantic Model*** | 📘 Convención | **No se traduce.** Tipo de elemento de Fabric. |
| Variable Library | ***Variable Library*** | 📘 Convención | **No se traduce.** Tipo de elemento de Fabric. |
| Data Pipeline | ***Data Pipeline*** | 📘 Convención | **No se traduce.** Tipo de elemento de Fabric. |
| Data Agent | ***Data Agent*** | 📘 Convención | **No se traduce.** Tipo de elemento de Fabric. |
| Ontology | ***Ontology*** | 📘 Convención | **No se traduce.** Tipo de elemento de Fabric. |
| Deployment Pipelines | ***Deployment Pipelines*** | 📘 Convención | **No se traduce.** En la primera aparición puede glosarse: «canalizaciones de implementación en el portal en español», que es el término oficial de Microsoft Terminology. |
| Branch Out | **Branch Out** | 📘 Convención | Función del portal de Fabric; no se traduce. |
| Update from Git | **Update from Git** | 📘 Convención | Operación del portal y de la API; no se traduce. |
| Git integration | **integración de Git** | 📘 Convención | Transparente y de uso general; sí se traduce. |
| capacity | **capacidad** | ✅ MS | |
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
| deploy *(verbo)* | **implementar** | ✅ MS | Equivalente asentado. |
| deployment | **implementación** | ✅ MS | |
| build | **compilación** | ✅ MS | |
| release | **versión** / **lanzamiento** | ✅ MS | Según contexto. |
| rollback | **reversión** | ✅ MS | |
| environment | **entorno** | ✅ MS | Nunca «ambiente». |
| pipeline | ***pipeline*** | 📘 Convención | **No se traduce nunca.** «Tubería» es la traducción literal y resulta absurda en CI/CD; «canalización» solo aparece como glosa del término del portal en español. En cursiva. |
| workflow *(GitHub Actions)* | **flujo de trabajo** | 📘 Convención | El nombre del archivo (`deploy-test.yml`) no se traduce. |
| feature branch | ***feature branch*** | 📘 Convención | Nombre de metodología establecido. |
| trunk-based development | ***trunk-based development*** | 📘 Convención | |

---

## Identidad, seguridad y gobernanza

| Inglés | Español | Origen | Notas |
|---|---|---|---|
| service principal | **entidad de servicio** | ✅ MS | ⚠️ Learn traduce «principal de servicio»; **Microsoft Terminology dice «entidad de servicio»** y es la forma correcta. |
| role | **rol** | ✅ MS | |
| permission | **permiso** | ✅ MS | |
| approval | **aprobación** | ✅ MS | |
| audit | **auditoría** | ✅ MS | |
| secret | **secreto** | 📘 Convención | El nombre del secreto (`AZURE_CLIENT_ID`) no se traduce. |
| least privilege | **privilegio mínimo** | 📘 Convención | |
| branch protection | **protección de ramas** | 📘 Convención | |

---

## Términos que NUNCA se traducen

Estos elementos no se traducen en ningún contexto, ni siquiera dentro de prosa:

- **Nombres de producto**: Microsoft Fabric, Power BI, GitHub Actions, fabric-cicd, Direct Lake, Azure
- **Tipos de elemento de Fabric**: *Lakehouse*, *Notebook*, *Semantic Model*, *Variable Library*, *Data Pipeline*, *Data Agent*, *Ontology*
- **Identificadores de la API**: `SemanticModel`, `Notebook`, `VariableLibrary`, `DataAgent`, `Ontology`, `Lakehouse`, `Report`
- **Funciones del portal**: *Branch Out*, *Update from Git*, *Deployment Pipelines*
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
