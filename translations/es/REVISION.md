[English](../../TRANSLATION.md) | **Español**

# Guía de revisión

Cómo revisar un *pull request* de traducción en este repositorio. Está dirigida al revisor hispanohablante, no al traductor.

La regla general: **revisa la naturalidad, no la literalidad**. Una traducción correcta palabra por palabra que suene rara en español es peor que una que se aparte del original y suene natural. El inglés es la fuente autorizada para los *hechos*, no para la *redacción*.

---

## Qué revisar

### 1. Terminología (lo más importante)

Comprueba que el documento sigue [`GLOSARIO.md`](GLOSARIO.md). Presta especial atención a las entradas marcadas 🟡 **Provisional**: no proceden de Microsoft Terminology, son propuestas pendientes de tu confirmación.

Si corriges un término:

1. Actualiza la entrada en [`GLOSARIO.md`](GLOSARIO.md) **en el mismo PR**.
2. Cambia su marca de 🟡 Provisional a 📘 Convención.
3. Aplica la corrección en todo el documento, no solo donde la viste.

### 2. Registro y estilo

Consulta [`GUIA-DE-ESTILO.md`](GUIA-DE-ESTILO.md). En concreto:

- **Tuteo coherente.** El riesgo real no es elegir mal, sino mezclar *tú* y *usted* dentro de un mismo documento.
- **Español neutro.** Marca cualquier vocabulario que suene marcado regionalmente.
- **Anglicismos en cursiva** en la primera aparición por documento, nunca dentro de bloques de código.

### 3. Naturalidad

Léelo como si nadie te hubiera dicho que es una traducción. Señala:

- Calcos del inglés («soporta» por *supports*, «librería» por *library*).
- Frases largas que en inglés funcionan y en español se atascan.
- Voz pasiva innecesaria donde el español preferiría una construcción impersonal.

### 4. Integridad técnica

- Los **enlaces internos** deben llevar a la versión española cuando exista, y al original en inglés marcado *(solo en inglés)* cuando no.
- Los **índices y referencias cruzadas** deben estar regenerados contra los títulos traducidos, no copiados del inglés.
- Los **diagramas** no deben tener texto desbordado fuera de su caja.

---

## Qué NO revisar

Estos elementos están sin traducir **a propósito**. Señalarlos consume tu atención sin aportar valor:

- Comandos, rutas, nombres de archivo y claves YAML o JSON
- Nombres de rama (`dev`, `test`, `main`, `feature/*`)
- Variables y secretos (`FABRIC_WORKSPACE_ID`, `DEPLOY_METHOD` y sus valores)
- Tipos de elemento de la API (`SemanticModel`, `Notebook`, `VariableLibrary`, `DataAgent`, `Ontology`)
- Nombres de producto (Microsoft Fabric, fabric-cicd, GitHub Actions)
- Salida literal de herramientas y mensajes de error
- Las marcas *(solo en inglés)*, que son deliberadas

La lista completa está en [`TRANSLATION.md`](../../TRANSLATION.md).

---

## Si encuentras un error de fondo

Si el problema **también existe en el original en inglés**, no lo arregles solo en la traducción: eso crea una divergencia silenciosa que nadie detectará después.

Corrige primero el inglés y después replica la corrección. Consulta [`TRANSLATION.md`](../../TRANSLATION.md).

---

## Preguntas abiertas del PR piloto

> Esta sección es específica de la primera traducción (`README.md`). Una vez resueltas las preguntas, se puede eliminar.

### A. Términos provisionales

Ninguno de estos aparece en Microsoft Terminology: son terminología reciente de Fabric y las traducciones son propuestas. ¿Las confirmas?

| Inglés | Propuesta | ¿Confirmas? |
|---|---|---|
| semantic model | modelo semántico | |
| variable library | biblioteca de variables | |
| data pipeline | canalización de datos | |
| Git integration | integración de Git | |

### B. Tipos de elemento en prosa

`Lakehouse` y `Notebook` se han dejado **sin traducir incluso en prosa**, por ser tipos de elemento de la API que el lector verá así en el portal y en `data/fabric/`. Microsoft Terminology ofrece «almacén de lago de datos» y «cuaderno» para el uso genérico.

¿Es la decisión correcta, o resulta forzada al leer?

### C. Enlaces a Microsoft Learn

Los enlaces a `learn.microsoft.com` apuntan a `/es-es/`. Esas páginas están **traducidas automáticamente** por Microsoft (`ms.translationtype: MT`) y su calidad es desigual.

¿Prefieres mantenerlas en español por comodidad del lector, o apuntar al inglés por precisión técnica? Es un cambio de una línea.

### D. Registro

¿El tuteo resulta natural para esta audiencia técnica, o esperarías «usted» en documentación de este tipo?

### E. Anglicismos

¿El tratamiento de *commit*, *pull request* y *pipeline* en cursiva resulta natural, o excesivo para alguien que trabaja a diario con estas herramientas?

---

## Cómo dejar constancia

Comenta directamente en el *pull request*. Para las decisiones de terminología, indica si la corrección debe aplicarse solo a este documento o a todas las traducciones futuras: en el segundo caso, se actualiza [`GLOSARIO.md`](GLOSARIO.md) antes de continuar con el resto de documentos.
