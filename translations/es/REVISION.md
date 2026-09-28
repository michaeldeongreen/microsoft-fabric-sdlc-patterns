[English](../../TRANSLATION.md) | **Español**

# Guía de revisión

Cómo revisar un *pull request* de traducción en este repositorio. Está dirigida al revisor hispanohablante, no al traductor.

La regla general: **importa la naturalidad, no la literalidad**. Una traducción correcta palabra por palabra que suene rara en español es peor que una que se aparte del original y suene natural. El inglés es la fuente autorizada para los *hechos*, no para la *redacción*.

---

## Qué hay en esta revisión

La primera traducción (`README.md`) se revisó documento a documento. A partir de ahí se ha traducido **el resto del repositorio de una sola vez**: seis documentos más, dos presentaciones y siete diagramas, unas 35.000 palabras.

El cambio de método es deliberado. Revisar un archivo cada vez obligaba a volver sobre el mismo material en cada entrega; entregarlo completo permite decidir la terminología una vez y aplicarla en bloque.

**No se espera una lectura completa.** El volumen no lo justifica y la revisión exhaustiva no es el objetivo. Lo que se pide son **comprobaciones puntuales**:

1. **Abrir dos o tres documentos al azar** y leer unos párrafos de cada uno. Lo que se busca es si *suena* a español escrito por una persona.
2. **Revisar los diagramas** ([`assets/es/`](../../assets/es)), que son rápidos de ver y donde un texto desbordado o una etiqueta a medio traducir se detecta de inmediato.
3. **Responder la pregunta abierta** del apartado siguiente, que es lo único que bloquea el cierre.

Todo lo mecánico —enlaces, anclas, bloques de código, términos rechazados, tuteo, concordancia de género— ya está comprobado de forma automática. No hace falta dedicarle atención.

Si aparece un problema de terminología, basta con señalarlo **una vez**: la corrección se aplica después a todos los documentos a la vez.

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
- Funciones del portal (*Branch Out*, *workspace*, *Fabric Capacity*)
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

> Resueltas en revisión nativa (22-09-2026), con confirmación terminológica adicional (23-09-2026). Se documentan aquí para no reabrirlas en cada PR.

| Decisión | Resultado |
|---|---|
| **Registro** | Impersonal por defecto; **usted** cuando hay instrucción directa. **Nunca tú.** |
| **Tipos de elemento de Fabric** | Se mantienen en inglés, también en prosa (*Lakehouse*, *Notebook*, *Semantic Model*, *Variable Library*, *Data Pipeline*). |
| **pipeline** | Nunca se traduce, y es **masculino**: «el *pipeline*», no «la *pipeline*». |
| **canalización** | No se usa nunca, aunque sea el término oficial de Microsoft: no se entiende en este contexto. |
| **Deployment Pipelines** | «*Pipelines* de despliegue». En singular: «*Pipeline* de despliegue de Fabric». |
| **workspace** | En inglés. No «área de trabajo», pese a ser el término de Microsoft Terminology. |
| **Service principal** | En inglés. No «entidad de servicio». |
| **Trigger** | En inglés. No «desencadenador». |
| **Merge del PR** | Preferido sobre «PR fusionado» o «Fusión de PR». |
| **Update from Git** | **Se traduce** («Actualización desde Git»), tanto el botón como la API, para que el diagrama sea coherente. |
| **equipo** | No se usa para *laptop* — colisiona con «equipos de ingeniería». Se usa «laptop». |
| **Fabric Capacity** | En inglés. Confirmado en revisión terminológica: «capacidad» resulta confuso porque el término se usa para demasiadas cosas. |
| **Enlaces externos** | Apuntan **siempre al inglés** (`/en-us/`), no a `/es-es/`. Véase el apartado «Sobre esta traducción» del README para los motivos. |
| **Autoridad terminológica** | La revisión nativa **prevalece sobre Microsoft Terminology**. El término oficial no siempre es el que se usa. |

---

## Preguntas abiertas

### A. Alcance del principio «ante la duda, en inglés»

Es la única pregunta que bloquea el cierre de esta entrega. Tras aplicar *workspace* y *Service principal* en inglés, estos cinco siguen en español en todos los documentos. ¿Son correctos, o también deberían ir en inglés?

| Término | Traducción actual | ¿Correcto? |
|---|---|---|
| deployment | despliegue | |
| environment | entorno | |
| branch | rama | |
| repository | repositorio | |
| workflow *(GitHub Actions)* | flujo de trabajo | |

Una respuesta de una línea basta. Si alguno debe cambiar, el cambio se aplica en bloque a los once documentos, no archivo por archivo.

> Indicio a favor de dejarlos en español: en la revisión del `README.md` se editaron frases que contenían *despliegue*, *rama* y *repositorio* sin tocar esos términos. No es una confirmación explícita, pero apunta a que no chirrían.

### B. Citas textuales en inglés

Hay **cuatro citas literales** de documentación de Microsoft y de `fabric-cicd`, en dos documentos ([`fabric-development-process.md`](fabric-development-process.md) y [`fabric-hybrid-cicd-guide.md`](fabric-hybrid-cicd-guide.md)). Se han dejado **en inglés y sin alterar**, con la traducción justo debajo precedida de «Traducción:», porque una cita traducida deja de poder contrastarse con la fuente que se enlaza.

¿Es la decisión correcta, o resulta más incómodo de leer que útil?

### C. Fabric Capacity ✅ *Resuelto*

Confirmado en revisión terminológica (23-09-2026): se usa **Fabric Capacity** en inglés, porque «capacidad» resulta confuso para el cliente — el mismo término se usa para demasiadas cosas. Ya aplicado.

### D. Registro y cursiva ✅ *Resuelto*

La conversión a impersonal y **usted** y el uso de cursiva en los anglicismos crudos se validaron en la revisión del `README.md` y se han aplicado de forma sistemática al resto. No es necesario volver sobre ello salvo que algún punto concreto suene forzado.

---

## Cómo dejar constancia

Los comentarios pueden dejarse directamente en el *pull request*. Al tratarse de una entrega en bloque, conviene indicar en cada observación de terminología si la corrección afecta **solo al documento donde se detectó** o **a todas las traducciones**: en el segundo caso se actualiza [`GLOSARIO.md`](GLOSARIO.md) y el cambio se aplica a los once documentos de una vez.

Si el acceso al *pull request* está restringido, el mismo comentario por cualquier otro medio sirve igual: lo que importa es la observación, no dónde quede registrada.
