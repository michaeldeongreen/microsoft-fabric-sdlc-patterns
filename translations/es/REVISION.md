[English](../../TRANSLATION.md) | **Español**

# Guía de revisión

Cómo revisar un *pull request* de traducción en este repositorio. Está dirigida al revisor hispanohablante, no al traductor.

La regla general: **importa la naturalidad, no la literalidad**. Una traducción correcta palabra por palabra que suene rara en español es peor que una que se aparte del original y suene natural. El inglés es la fuente autorizada para los *hechos*, no para la *redacción*.

---

## Qué revisar

### 1. Terminología (lo más importante)

Debe comprobarse que el documento sigue [`GLOSARIO.md`](GLOSARIO.md). El principio rector es **ante la duda, en inglés**: los tipos de elemento de Fabric y los nombres de funciones del portal no se traducen, porque la traducción literal de un término técnico suele ser menos reconocible que el original.

Si se corrige un término:

1. Se actualiza la entrada en [`GLOSARIO.md`](GLOSARIO.md) **en el mismo PR**.
2. Su marca pasa de 🟡 Provisional a 📘 Convención.
3. La corrección se aplica en todo el documento, no solo donde se detectó.

### 2. Registro y estilo

Véase [`GUIA-DE-ESTILO.md`](GUIA-DE-ESTILO.md). En concreto:

- **No se tutea.** El tratamiento es impersonal; cuando hay instrucción directa, se usa **usted**.
- **Coherencia.** Mezclar formas dentro de un mismo documento resulta más chocante que cualquiera de ellas aplicada de forma sistemática.
- **Español neutro.** Debe señalarse cualquier vocabulario que suene marcado regionalmente.
- **Anglicismos en cursiva** en la primera aparición por documento, nunca dentro de bloques de código.

### 3. Naturalidad

Conviene leerlo como si nadie hubiera advertido que es una traducción. Deben señalarse:

- Calcos del inglés («soporta» por *supports*, «librería» por *library*).
- Frases largas que en inglés funcionan y en español se atascan.
- Voz pasiva innecesaria donde el español preferiría una construcción impersonal.

### 4. Integridad técnica

- Los **enlaces internos** deben llevar a la versión española cuando exista, y al original en inglés marcado *(solo en inglés)* cuando no.
- Los **índices y referencias cruzadas** deben estar regenerados contra los títulos traducidos, no copiados del inglés.
- Los **diagramas** no deben tener texto desbordado fuera de su caja.

---

## Qué NO revisar

Estos elementos están sin traducir **a propósito**. Señalarlos consume atención sin aportar valor:

- Comandos, rutas, nombres de archivo y claves YAML o JSON
- Nombres de rama (`dev`, `test`, `main`, `feature/*`)
- Variables y secretos (`FABRIC_WORKSPACE_ID`, `DEPLOY_METHOD` y sus valores)
- Tipos de elemento de Fabric (*Lakehouse*, *Notebook*, *Semantic Model*, *Variable Library*, *Data Pipeline*, *Data Agent*, *Ontology*)
- Funciones del portal (*Branch Out*, *Update from Git*, *Deployment Pipelines*)
- Nombres de producto (Microsoft Fabric, fabric-cicd, GitHub Actions)
- Salida literal de herramientas y mensajes de error
- Las marcas *(solo en inglés)*, que son deliberadas

La lista completa está en [`TRANSLATION.md`](../../TRANSLATION.md).

---

## Si aparece un error de fondo

Si el problema **existe también en el original en inglés**, no debe corregirse solo en la traducción: eso crea una divergencia silenciosa que nadie detectará después.

Se corrige primero el inglés y después se replica la corrección. Véase [`TRANSLATION.md`](../../TRANSLATION.md).

---

## Decisiones ya tomadas

> Resueltas a partir de la primera revisión (Ana Franco, 22-09-2026). Se documentan aquí para no reabrirlas en cada PR.

| Decisión | Resultado |
|---|---|
| **Registro** | Impersonal por defecto; **usted** cuando hay instrucción directa. **Nunca tú.** |
| **Tipos de elemento de Fabric** | Se mantienen en inglés, también en prosa (*Lakehouse*, *Notebook*, *Semantic Model*, *Variable Library*, *Data Pipeline*). |
| **pipeline** | Nunca se traduce. «Tubería» es la traducción literal y resulta absurda en CI/CD. |
| **Deployment Pipelines** | En inglés, con glosa «canalizaciones de implementación en el portal en español» la primera vez. |

---

## Preguntas abiertas

> Específicas de la primera traducción (`README.md`). Una vez resueltas, esta sección puede eliminarse.

### A. Alcance del principio «ante la duda, en inglés»

Se mantienen en español algunos términos por considerarse transparentes y de uso general. ¿Son correctos, o también deberían ir en inglés?

| Término | Traducción actual | ¿Correcto? |
|---|---|---|
| workspace | área de trabajo | |
| service principal | entidad de servicio | |
| deployment | implementación | |
| environment | entorno | |
| branch | rama | |

### B. Enlaces a Microsoft Learn

Los enlaces a `learn.microsoft.com` apuntan a `/es-es/`. Esas páginas están **traducidas automáticamente** por Microsoft (`ms.translationtype: MT`) y su calidad es desigual: la página de integración de Git usa «espacio de trabajo» y «área de trabajo» en el mismo párrafo.

¿Conviene mantenerlas en español por comodidad del lector, o apuntar al inglés por precisión técnica? Es un cambio de una línea.

### C. Naturalidad del resultado impersonal

La conversión de tuteo a impersonal y usted se ha hecho en todo el documento. ¿Suena natural, o ha quedado algún punto forzado o telegráfico?

### D. Cursiva en los anglicismos

El uso de cursiva en *commit*, *pull request* y *pipeline* sigue la norma de la RAE para extranjerismos crudos. ¿Resulta natural, o excesivo para quien trabaja a diario con estas herramientas?

---

## Cómo dejar constancia

Los comentarios pueden dejarse directamente en el *pull request*. Para las decisiones de terminología conviene indicar si la corrección debe aplicarse solo a este documento o a todas las traducciones futuras: en el segundo caso se actualiza [`GLOSARIO.md`](GLOSARIO.md) antes de continuar con el resto de documentos.
