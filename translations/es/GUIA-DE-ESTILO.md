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

- Evita vocabulario marcado regionalmente. Usa **equipo** o **computadora**, nunca «ordenador» (marcado como España).
- Evita modismos y coloquialismos de cualquier país.
- Evita el voseo y cualquier forma verbal regional.
- Ante la duda entre dos equivalentes válidos, elige el más extendido internacionalmente.

---

## Registro: tuteo (*tú*)

Se usa **tú**, no «usted».

Microsoft no impone una forma —su guía neutra reconoce que varía según el producto—, pero sus principios de voz apuntan al registro informal (*"Warm and relaxed… Less formal, more grounded in honest conversations"*), y los ejemplos aprobados en las guías de estilo usan sistemáticamente **tú**. Es además la norma en documentación para desarrolladores.

```
✅ Para implementar el elemento, ejecuta el script desde la raíz del repositorio.
❌ Para implementar el elemento, ejecute el script desde la raíz del repositorio.
```

### Prefiere construcciones impersonales

Cuando sea natural, usa impersonal o pasiva refleja. Reduce la fricción del registro y suele producir prosa más limpia:

```
✅ El script revierte los identificadores del área de trabajo.
✅ Los identificadores se revierten automáticamente.
⚠️ Tú revertirás los identificadores.   (correcto, pero innecesariamente personal)
```

**Lo importante es la coherencia.** Microsoft demuestra que el riesgo real no es elegir mal, sino mezclar formas dentro de un mismo documento.

---

## Extranjerismos (anglicismos)

Se sigue la norma de la RAE/ASALE en el [*Diccionario panhispánico de dudas*](https://www.rae.es/dpd/ayuda/tratamiento-de-los-extranjerismos):

1. **Extranjerismos superfluos** — si existe un equivalente español con plena vitalidad, **úsalo**. Por eso *branch* → «rama» y *deployment* → «implementación».
2. **Extranjerismos necesarios o muy extendidos** — si el término está asentado en el uso internacional en su forma original, se mantiene, **pero debe escribirse con resalte tipográfico (cursiva)**:

   > «se advierte de su condición de extranjerismos crudos y de la obligación de escribirlos con resalte tipográfico (cursiva o comillas) para señalar su carácter ajeno a la ortografía del español»

### Reglas prácticas

- **Cursiva en la primera aparición por documento**: *commit*, *pull request*, *pipeline*, *feature branch*.
- **Nunca cursiva dentro de bloques de código ni de `código en línea`.** El resalte tipográfico es para la prosa.
- **Nunca inventes verbos híbridos**: «commitear», «deployar», «mergear» son incorrectos. Usa «hacer *commit*», «implementar», «fusionar».
- **Glosa en la primera aparición** cuando el término tenga equivalente reconocible: «*pull request* (solicitud de cambios)».

### Siglas

Las siglas de uso internacional no se traducen ni se desarrollan: API, CI/CD, JSON, YAML, SDLC, RBAC, PR, GUID.

Para las menos conocidas, desarrolla en español y añade la sigla inglesa entre paréntesis: «administración del ciclo de vida de las aplicaciones (ALM)».

---

## Términos de la interfaz de Fabric

Los profesionales de Fabric suelen trabajar con el portal en inglés. Por eso, en la **primera aparición por documento**, se da el término español seguido del inglés en cursiva entre paréntesis:

```markdown
Las **canalizaciones de implementación** (*deployment pipelines*) permiten promover contenido entre áreas de trabajo.
```

Después de la primera aparición, usa solo el término español.

La terminología procede de **Microsoft Terminology**, no de `learn.microsoft.com/es-es` — consulta [`GLOSARIO.md`](GLOSARIO.md) y la advertencia que contiene.

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

El español ocupa entre un **15 % y un 25 % más** que el inglés. Tenlo en cuenta en:

- **Tablas** — considera reformular para que las celdas no se desborden.
- **Diagramas SVG** — las etiquetas viven en cajas de ancho fijo. Acorta la etiqueta o ensancha la caja; no dejes que el texto se salga.

---

## Qué no se toca

Consulta [`../../TRANSLATION.md`](../../TRANSLATION.md) para la lista completa. En resumen: comandos, rutas, nombres de archivo, claves YAML/JSON, identificadores de Python, nombres de rama, variables de entorno, tipos de elemento de la API y salida literal de herramientas.

Si un bloque de código contiene **comentarios**, esos sí se traducen.

---

## Traducción automática

Se permite usar traducción automática o asistida por IA **como punto de partida, nunca como resultado final**. Toda traducción la revisa un hablante nativo antes de fusionarse.

Recomendación práctica: usa un corrector ortográfico de español en el editor antes de abrir el *pull request*.

---

## Referencias

- [Microsoft Spanish (Neutral) Style Guide](https://aka.ms/spanish-neutral-styleguide)
- [Microsoft Terminology](https://learn.microsoft.com/en-us/globalization/reference/microsoft-terminology)
- [RAE/ASALE — Tratamiento de los extranjerismos](https://www.rae.es/dpd/ayuda/tratamiento-de-los-extranjerismos)
- [Kubernetes — Localización](https://kubernetes.io/docs/contribute/localization/)
