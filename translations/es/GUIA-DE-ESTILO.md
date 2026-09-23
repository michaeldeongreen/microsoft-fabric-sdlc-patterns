[English](../../TRANSLATION.md) | **Español**

# Guía de estilo

Decisiones de estilo para la traducción al español de este repositorio. Junto con [`GLOSARIO.md`](GLOSARIO.md), es la referencia obligatoria antes de traducir.

---

## Variante: español neutro (internacional)

Se usa **español neutro**, no una variante nacional.

Microsoft publica cuatro guías de estilo para el español —neutro, México, España y Estados Unidos— y la [guía neutra](https://aka.ms/spanish-neutral-styleguide) es la escrita para productos que se distribuyen en todos los mercados hispanohablantes. Su propio argumento:

> «The term "neutral" or "international" Spanish does not refer to any specific dialect of the language… Rather, it refers to the process of finding terms or phrases that would be understood or best suited to a multinational target audience.»

La evidencia que lo confirma es que **Microsoft Learn publica un único español**: las URL `es-mx` se canonicalizan a `es-es` y sirven contenido idéntico. Microsoft no mantiene una documentación mexicana de Fabric y otra argentina.

En la práctica:

- Debe evitarse el vocabulario marcado regionalmente: **equipo** o **computadora**, nunca «ordenador» (marcado como España).
- Se evitan los modismos y coloquialismos de cualquier país.
- Se evita el voseo y cualquier forma verbal regional.
- Ante la duda entre dos equivalentes válidos, se prefiere el más extendido internacionalmente.

---

## Registro: impersonal

**No se tutea.** En documentación profesional el tratamiento es **impersonal**; cuando el trato directo resulta inevitable, se usa **usted**. Nunca *tú*.

Esta es también la práctica de la documentación en español de Microsoft. En las páginas de Fabric de Microsoft Learn conviven la construcción impersonal y el imperativo de cortesía:

> «La integración de Git en Fabric **permite** a los desarrolladores integrar sus procesos…»
> «La estructura del área de trabajo **se conserva** en el repositorio de Git.»
> «**Consulte** la lista de elementos admitidos.» · «**Obtenga** más información…» · «**Asegúrese** de revisar…»

### 1. Impersonal como opción preferente

Para describir comportamiento, procesos o reglas se emplea la pasiva refleja o una construcción impersonal:

```
✅ Los identificadores del workspace se revierten automáticamente.
✅ El script revierte los identificadores del workspace.
✅ La terminología procede de Microsoft Terminology.
❌ Tú revertirás los identificadores del workspace.
```

### 2. Usted cuando hay instrucción directa

En procedimientos paso a paso, donde hay que dirigirse a alguien, se usa el imperativo de cortesía:

```
✅ Para implementar el elemento, ejecute el script desde la raíz del repositorio.
✅ Cree un service principal y añádalo como colaborador.
❌ Para implementar el elemento, ejecuta el script desde la raíz del repositorio.
```

### 3. Reformular antes que tutear

Muchas frases con trato directo se resuelven mejor reformulando:

```
Original en inglés:  See the Development Process doc.
❌ Consulta el documento de proceso de desarrollo.
✅ Véase el documento de proceso de desarrollo.
✅ Más información en el documento de proceso de desarrollo.
```

**La coherencia es lo esencial.** Mezclar formas dentro de un mismo documento resulta más chocante que cualquiera de las dos opciones aplicada de forma sistemática.


---

## Extranjerismos (anglicismos)

Se sigue la norma de la RAE/ASALE en el [*Diccionario panhispánico de dudas*](https://www.rae.es/dpd/ayuda/tratamiento-de-los-extranjerismos):

1. **Extranjerismos superfluos** — si existe un equivalente español con plena vitalidad, se emplea este. Por eso *branch* → «rama» y *deployment* → «implementación».
2. **Extranjerismos necesarios o muy extendidos** — si el término está asentado en el uso internacional en su forma original, se mantiene, **pero debe escribirse con resalte tipográfico (cursiva)**:

   > «se advierte de su condición de extranjerismos crudos y de la obligación de escribirlos con resalte tipográfico (cursiva o comillas) para señalar su carácter ajeno a la ortografía del español»

### Reglas prácticas

- **Cursiva en la primera aparición por documento**: *commit*, *pull request*, *pipeline*, *feature branch*.
- **Nunca cursiva dentro de bloques de código ni de `código en línea`.** El resalte tipográfico es para la prosa.
- **No se inventan verbos híbridos**: «commitear», «deployar», «mergear» son incorrectos. En su lugar, «hacer *commit*», «implementar», «fusionar».
- **Glosa en la primera aparición** cuando el término tenga un equivalente reconocible: «*pull request* (solicitud de cambios)».

### Siglas

Las siglas de uso internacional no se traducen ni se desarrollan: API, CI/CD, JSON, YAML, SDLC, RBAC, PR, GUID.

Para las menos conocidas, se desarrolla en español y se añade la sigla inglesa entre paréntesis: «administración del ciclo de vida de las aplicaciones (ALM)».

---

## Términos técnicos y de producto: el inglés manda

**Regla general: ante la duda, se mantiene el término en inglés.**

Quien lee esta documentación trabaja a diario con Fabric, Git y GitHub, casi siempre con la interfaz en inglés. La traducción literal de un término técnico suele ser *menos* reconocible que el original, no más. El ejemplo canónico es *pipeline*: su traducción literal, «tubería», nadie la usaría jamás para hablar de CI/CD.

Esto afecta sobre todo a:

- **Tipos de elemento de Fabric** — *Lakehouse*, *Notebook*, *Semantic Model*, *Variable Library*, *Data Pipeline*, *Data Agent*, *Ontology*. Se mantienen en inglés siempre, también en prosa corrida.
- **Nombres de funciones y objetos del portal** — *Branch Out*, *workspace*, *Fabric capacity*. *Update from Git* es la excepción: se traduce.
- **Vocabulario de CI/CD sin equivalente asentado** — *pipeline*, *commit*, *pull request*, *feature branch*, *Trigger*, *Service principal*.

### Cuándo sí se traduce

Se traduce cuando el equivalente español está plenamente asentado y resulta transparente para cualquier profesional:

| Se traduce | No se traduce |
|---|---|
| branch → rama | *pipeline* |
| merge → fusionar | *commit*, *pull request* |
| repository → repositorio | *workspace* |
| deployment → despliegue | *Service principal* |
| environment → entorno | *Lakehouse*, *Notebook*, *Semantic Model* |
| trigger → *Trigger* *(no se traduce)* | *Fabric capacity* |

### El término oficial no siempre gana

**Microsoft Terminology es el punto de partida, no la autoridad final.** Recoge el término *oficial*, que no siempre coincide con el que usa quien trabaja a diario con el producto. Cuando difieren, gana el uso real:

| Inglés | Término oficial de Microsoft | Lo que se usa aquí |
|---|---|---|
| workspace | área de trabajo | ***workspace*** |
| service principal | entidad de servicio | ***Service principal*** |
| deployment pipeline | canalización de implementación | ***Pipeline* de despliegue** |

«Canalización» es el caso más claro: es el término oficial y, aun así, **no se entiende** en este contexto. Estas decisiones se marcan 👤 Revisión en [`GLOSARIO.md`](GLOSARIO.md).

### Glosa en la primera aparición

Cuando un término se mantiene en inglés y existe una forma española reconocible, puede glosarse entre paréntesis la primera vez:

```markdown
Cree un *Service principal* (entidad de servicio) con el rol de colaborador.
```

Después de esa primera aparición se usa solo la forma inglesa. Si la forma española **no** es reconocible —«canalización», «tubería»— no se glosa: solo añade ruido.


---

## Convenciones de escritura

### Títulos

- **Mayúscula solo en la primera palabra** y en nombres propios. El español no usa *title case*.
  ```
  ✅ ## Estrategia de configuración
  ❌ ## Estrategia De Configuración
  ```
- Los títulos determinan los anclajes de GitHub. Al traducir un título cambia su anclaje, así que **regenera los índices y las referencias cruzadas del documento**. Nunca copies los anclajes del original en inglés.

### Puntuación

- **Signos de apertura obligatorios**: ¿…? y ¡…!
- **Comillas**: se prefieren las angulares «…» para citas en prosa. Las comillas rectas se reservan para el código.
- **Espacio fino en números**: 61 956, no 61,956 ni 61.956.
- **Guion largo (—)** para incisos, igual que en el original.

### Números y unidades

- Decimales con coma: 2,5 GB.
- Los identificadores, versiones y rutas no se adaptan: `Python 3.12`, `v2.9.0`.

### Longitud

El español ocupa entre un **15 % y un 25 % más** que el inglés. Conviene tenerlo en cuenta en:

- **Tablas** — puede ser necesario reformular para que las celdas no se desborden.
- **Diagramas SVG** — las etiquetas viven en cajas de ancho fijo. Hay que acortar la etiqueta o ensanchar la caja; el texto no debe salirse.

---

## Qué no se toca

Véase [`../../TRANSLATION.md`](../../TRANSLATION.md) para la lista completa. En resumen: comandos, rutas, nombres de archivo, claves YAML/JSON, identificadores de Python, nombres de rama, variables de entorno, tipos de elemento de la API y salida literal de herramientas.

Si un bloque de código contiene **comentarios**, esos sí se traducen.

---

## Traducción automática

Se permite usar traducción automática o asistida por IA **como punto de partida, nunca como resultado final**. Toda traducción la revisa un hablante nativo antes de fusionarse.

Recomendación práctica: conviene pasar un corrector ortográfico de español antes de abrir el *pull request*.

---

## Referencias

- [Microsoft Spanish (Neutral) Style Guide](https://aka.ms/spanish-neutral-styleguide)
- [Microsoft Terminology](https://learn.microsoft.com/en-us/globalization/reference/microsoft-terminology)
- [RAE/ASALE — Tratamiento de los extranjerismos](https://www.rae.es/dpd/ayuda/tratamiento-de-los-extranjerismos)
- [Kubernetes — Localización](https://kubernetes.io/docs/contribute/localization/)
