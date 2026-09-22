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

> ⚠️ **No tomes terminología de `learn.microsoft.com/es-es`.** Esas páginas están traducidas automáticamente (`ms.translationtype: MT`) y son inconsistentes incluso dentro de una misma página. Ejemplo real: Learn traduce *service principal* como «principal de servicio», mientras que Microsoft Terminology establece **entidad de servicio**.

---

## Fabric y Power BI

| Inglés | Español | Origen | Notas |
|---|---|---|---|
| workspace | **área de trabajo** | ✅ MS | Definición coincidente: *"A container of Power BI content… designed for collaboration"*. No uses «espacio de trabajo», que en la terminología de Microsoft designa otro concepto. |
| deployment pipeline | **canalización de implementación** | ✅ MS | Término único y sin ambigüedad en la colección. |
| capacity | **capacidad** | ✅ MS | |
| tenant | **inquilino** | ✅ MS | La colección admite varias formas; «inquilino» es la habitual en Azure/Entra. |
| dataset | **conjunto de datos** | ✅ MS | |
| report | **informe** | ✅ MS | |
| dataflow | **flujo de datos** | ✅ MS | |
| lakehouse | **Lakehouse** *(tipo de elemento)* | 📘 Convención | Como **tipo de elemento de Fabric no se traduce** (aparece así en la API y en `data/fabric/`). En prosa genérica, Microsoft Terminology ofrece «almacén de lago de datos». |
| notebook | **Notebook** *(tipo de elemento)* | 📘 Convención | Igual que Lakehouse: es un tipo de elemento de la API. En prosa genérica, «cuaderno». |
| semantic model | **modelo semántico** | 🟡 Provisional | No está en Microsoft Terminology (terminología reciente). Como tipo de elemento se mantiene `SemanticModel`. |
| variable library | **biblioteca de variables** | 🟡 Provisional | No está en Microsoft Terminology. Como tipo de elemento se mantiene `VariableLibrary`. |
| data pipeline | **canalización de datos** | 🟡 Provisional | No está en Microsoft Terminology. Coherente con *deployment pipeline* → «canalización». |
| Git integration | **integración de Git** | 🟡 Provisional | No está en Microsoft Terminology. |
| Data Agent | **Data Agent** | 📘 Convención | Tipo de elemento de Fabric; no se traduce. |
| Ontology | **Ontology** | 📘 Convención | Tipo de elemento de Fabric; no se traduce. |
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
| merge | **fusionar** / **combinar** | ✅ MS | Elige una y mantenla dentro del documento. |
| commit *(sustantivo)* | ***commit*** | ✅ MS | Microsoft Terminology admite «commit» además de «confirmación». Se mantiene el anglicismo por ser el uso real entre desarrolladores. En cursiva. |
| commit *(verbo)* | **hacer *commit*** / **confirmar** | ✅ MS | Nunca «commitear». |
| pull request | ***pull request*** (PR) | ✅ MS | La colección admite «pull request», «PR» y «solicitud de cambios». Se mantiene el anglicismo por ser el término de la interfaz de GitHub. Glosa en la primera aparición: «*pull request* (solicitud de cambios)». |
| deploy *(verbo)* | **implementar** | ✅ MS | Coherente con *deployment pipeline* → «canalización de implementación». |
| deployment | **implementación** | ✅ MS | |
| build | **compilación** | ✅ MS | |
| release | **versión** / **lanzamiento** | ✅ MS | Según contexto. |
| rollback | **reversión** | ✅ MS | |
| environment | **entorno** | ✅ MS | Nunca «ambiente». |
| pipeline *(genérico de CI/CD)* | ***pipeline*** | 📘 Convención | En cursiva. Cuando designa el elemento de Fabric, usa «canalización». |
| workflow *(GitHub Actions)* | **flujo de trabajo** | 📘 Convención | El nombre del archivo (`deploy-test.yml`) no se traduce. |
| feature branch | ***feature branch*** | 📘 Convención | Nombre de metodología establecido. |
| trunk-based development | ***trunk-based development*** | 📘 Convención | |
| Branch Out | **Branch Out** | 📘 Convención | Función de la interfaz de Fabric; no se traduce. |

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

No traduzcas estos elementos en ningún contexto, ni siquiera dentro de prosa:

- **Nombres de producto**: Microsoft Fabric, Power BI, GitHub Actions, fabric-cicd, Direct Lake, Azure
- **Tipos de elemento de la API**: `SemanticModel`, `Notebook`, `VariableLibrary`, `DataAgent`, `Ontology`, `Lakehouse`, `Report`
- **Nombres de rama**: `dev`, `test`, `main`, `feature/*`
- **Variables y secretos**: `FABRIC_WORKSPACE_ID`, `AZURE_CLIENT_ID`, `AZURE_TENANT_ID`, `AZURE_CLIENT_SECRET`, `DEPLOY_METHOD`
- **Valores de configuración**: `fabric-cicd`, `fabric-cicd-bulk`, `bulk`
- **Rutas y nombres de archivo**: `data/fabric/`, `scripts/workspace_swap.py`, `parameter.yml`, `deploy-test.yml`
- **Funciones y claves**: `publish_all_items()`, `unpublish_all_orphan_items()`, `find_replace`, `$workspace.$id`
- **Salida literal de herramientas y mensajes de error** — el lector los verá en inglés en su pantalla

---

## Cómo ampliar este glosario

1. Busca primero en **Microsoft Terminology**. Si el término existe, úsalo y márcalo ✅ MS.
2. Si no existe, propón una traducción, márcala 🟡 Provisional y explica el razonamiento.
3. Añade la entrada **en el mismo *pull request*** que la traducción que la motivó, para que el siguiente traductor herede la decisión.
4. Si un revisor nativo corrige un término, actualiza la entrada y cambia su marca a 📘 Convención o ✅ MS según corresponda.

Consulta también [`GUIA-DE-ESTILO.md`](GUIA-DE-ESTILO.md) para variante, registro y tratamiento de extranjerismos.
