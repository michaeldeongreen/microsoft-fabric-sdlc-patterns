[English](../../README.md) | **Español**

<!-- source: README.md @ 46ec32f | translated: 2026-09-22 -->

> 📄 **La versión en inglés de este documento es la autoritativa.** Si encuentras una discrepancia, [el original en inglés](../../README.md) tiene precedencia.

# Patrones de SDLC para Microsoft Fabric

Implementación de referencia y acelerador de soluciones para el flujo de trabajo del desarrollador y la *pipeline* de CI/CD en Microsoft Fabric. Muestra cómo elegir una estrategia de publicación, implementar despliegues, trabajar día a día en *feature branches* y gobernar la *pipeline* para desarrollo, pruebas y producción con GitHub Actions y la biblioteca de Python [fabric-cicd](https://microsoft.github.io/fabric-cicd). Tanto el flujo de trabajo del desarrollador como la *pipeline* de implementación están implementados de principio a fin, de modo que el repositorio funciona como una referencia completa y no como ejemplos aislados.

*Basado en la experiencia de campo con clientes y partners de Microsoft Fabric. Las opiniones aquí expresadas son propias y no representan la guía oficial de Microsoft.*

---

## ¿A quién está dirigido?

A los equipos de ingeniería y de plataforma responsables de llevar las cargas de trabajo de Microsoft Fabric desde el equipo de un desarrollador hasta producción de forma segura y repetible, abarcando el flujo de trabajo del desarrollador, la propia *pipeline* de implementación y la gobernanza que se superpone a ambos.

Los arquitectos y responsables de decisión que estén evaluando Fabric encontrarán útiles [Opciones de publicación de CI/CD](../../fabric-cicd-release-options.md) *(solo en inglés)* y [Consideraciones de gobernanza](../../fabric-cicd-governance-considerations.md) *(solo en inglés)* para entender el modelo operativo antes de comprometerse.

---

## Arquitectura

```
Rama de característica (feature/*)
  │
  │  PR → rama dev
  ▼
Repositorio Git (rama dev)
  │
  │  Fusión de PR → rama test (el origen debe ser dev)
  ▼
┌──────────────────────────────────────────────┐
│  deploy-test.yml                             │
│    └─ fabric-cicd: publish_all_items()       │
│                    ↓ si tiene éxito           │
│  etl-test.yml                                │
│    └─ API REST de Fabric: ejecuta notebook   │
└──────────────────────────────────────────────┘
  │
  │  Fusión de PR → rama main (el origen debe ser test)
  ▼
┌──────────────────────────────────────────────┐
│  deploy-prod.yml                             │
│    └─ fabric-cicd: publish_all_items()       │
│                    ↓ si tiene éxito           │
│  etl-prod.yml                                │
│    └─ API REST de Fabric: ejecuta notebook   │
└──────────────────────────────────────────────┘
```

La protección de ramas (PR obligatorio, restricciones de rama de origen, comprobaciones de estado) se aplica mediante los *rulesets* de ramas de GitHub y el flujo de trabajo [enforce-promotion-path.yml](../../.github/workflows/enforce-promotion-path.yml); consulta las [Consideraciones de gobernanza](../../fabric-cicd-governance-considerations.md) *(solo en inglés)*.

![Flujo recomendado del enfoque híbrido](../../assets/es/hybrid-recommendation-flow.svg)

> Este repositorio demuestra fabric-cicd (la biblioteca de Python GA recomendada por defecto) junto con un conjunto paralelo de flujos de trabajo basados en las API de importación y exportación masiva (*Bulk Import / Export*, en versión preliminar) para su evaluación y comparación. La selección se controla con la variable de repositorio `DEPLOY_METHOD`; consulta [Inicio rápido](#inicio-rápido) para ver todos los métodos y cómo cambiar entre ellos, y [Opciones de publicación de CI/CD](../../fabric-cicd-release-options.md#tooling-within-option-3-fabric-cicd-vs-bulk-apis) *(solo en inglés)* para la comparación completa.

---

## Documentación

Los documentos siguientes todavía no están traducidos. Los enlaces apuntan al original en inglés.

| Documento | Descripción |
|---|---|
| [Opciones de publicación de CI/CD](../../fabric-cicd-release-options.md) *(solo en inglés)* | Evalúa todas las opciones de publicación de CI/CD para Fabric (canalizaciones de implementación, basadas en Git, basadas en compilación, híbrida) y recomienda el enfoque híbrido. Incluye una [comparación entre fabric-cicd y las nuevas API de importación y exportación masiva](../../fabric-cicd-release-options.md#tooling-within-option-3-fabric-cicd-vs-bulk-apis) (versión preliminar) dentro de la opción 3. **Empieza aquí** si estás decidiendo una estrategia. |
| [Guía de implementación híbrida de CI/CD](../../fabric-hybrid-cicd-guide.md) *(solo en inglés)* | Análisis detallado de la implementación recomendada con fabric-cicd: estructura de los flujos de trabajo, estrategia de configuración, requisitos previos, pasos de configuración y problemas habituales. |
| [Guía de implementación de CI/CD masivo](../../fabric-bulk-cicd-guide.md) *(solo en inglés)* | Guía de implementación de la ruta alternativa de despliegue con la API de importación masiva (versión preliminar). Cubre las soluciones alternativas que salvan las carencias (sustitución, activación de conjuntos de valores), la decisión de los dos despliegues, los patrones de extensión y las limitaciones que no se resuelven. |
| [Proceso de desarrollo](../../fabric-development-process.md) *(solo en inglés)* | Cómo trabajan los desarrolladores día a día: flujo de trabajo de Branch Out, el script de cambio de área de trabajo y la comprobación de preparación del PR. |
| [Consideraciones de gobernanza de CI/CD](../../fabric-cicd-governance-considerations.md) *(solo en inglés)* | Consideraciones sobre identidades, RBAC, protección de ramas y puertas de aprobación para la *pipeline* de CI/CD. Incluye referencias a controles adyacentes que se gestionan fuera de la *pipeline* (temas de seguridad y cumplimiento). |

---

## Conceptos clave

Antes de elegir un enfoque de CI/CD o un flujo de trabajo de desarrollo, conviene entender estas dos realidades sobre los elementos de Fabric.

### Categorías de seguimiento de elementos

No todos los elementos de Fabric se pueden gestionar igual. Desde el punto de vista de la administración del ciclo de vida, se dividen en tres categorías:

| Categoría | Descripción | Ejemplos |
|---|---|---|
| **Con seguimiento en Git** | Elementos compatibles con la [integración de Git de Fabric](https://learn.microsoft.com/es-es/fabric/cicd/git-integration/intro-to-git-integration#supported-items). Sus definiciones se serializan en archivos dentro del repositorio, lo que permite control de versiones, ramificación y flujos de revisión de código. | Notebooks, modelos semánticos, Lakehouses, informes, bibliotecas de variables, canalizaciones de datos, entornos |
| **Solo canalizaciones de implementación** | Elementos no compatibles con la integración de Git ni con fabric-cicd, pero sí con las [canalizaciones de implementación de Fabric](https://learn.microsoft.com/es-es/fabric/cicd/deployment-pipelines/intro-to-deployment-pipelines#supported-items). Se pueden promover de un área de trabajo a otra, pero no se pueden versionar en Git. | Consulta las listas oficiales de elementos compatibles: esta categoría cambia a medida que Microsoft añade capacidades |
| **Manuales** | Elementos que no admiten ni la integración de Git ni las canalizaciones de implementación. Deben crearse y configurarse manualmente en cada área de trabajo. | Varía según Microsoft amplía la compatibilidad; consulta siempre las listas oficiales de elementos compatibles |

> **Importante:** ambas listas de elementos compatibles evolucionan a medida que Microsoft añade capacidades. Verifica siempre la documentación oficial antes de dar por hecho que un elemento pertenece a una categoría concreta.

Esta categorización afecta directamente a tu estrategia de CI/CD. La [Guía de implementación híbrida de CI/CD](../../fabric-hybrid-cicd-guide.md) *(solo en inglés)* describe cómo abordar la diferencia entre los elementos con seguimiento en Git y los que solo admiten canalizaciones de implementación, si tu área de trabajo incluye tipos no compatibles. Actualmente, todos los elementos de este repositorio se implementan mediante fabric-cicd.

### Bibliotecas de variables: metadatos dinámicos frente a estáticos

Algunos elementos de Fabric resuelven los valores específicos de cada entorno **en tiempo de ejecución** mediante [bibliotecas de variables](https://learn.microsoft.com/es-es/fabric/cicd/variable-library/variable-library-cicd), mientras que otros tienen los identificadores específicos del entorno **codificados en sus definiciones**.

| Tipo | Cómo funciona | Ejemplos |
|---|---|---|
| **Dinámico (biblioteca de variables)** | El elemento lee los identificadores de la biblioteca de variables en tiempo de ejecución. Cambiar el conjunto de valores activo conmuta automáticamente el contexto del entorno, sin modificar archivos. | Notebooks que usan `notebookutils.variableLibrary.getLibrary()` |
| **Estático (codificado)** | La definición del elemento contiene GUID literales de área de trabajo o de Lakehouse que deben reescribirse en cada entorno, ya sea en el momento del despliegue (mediante `parameter.yml`) o mediante script (`workspace_swap.py`). | URL de Direct Lake del modelo semántico (`expressions.tmdl`), bloques META de dependencias del notebook (`default_lakehouse`, `default_lakehouse_workspace_id`) |

Al diseñar tus procesos de desarrollo y de CI/CD, identifica qué elementos de tu área de trabajo son dinámicos y cuáles estáticos. Los estáticos necesitan parametrización en el momento del despliegue (`parameter.yml` para CI/CD) o reescritura mediante script (`workspace_swap.py` para *feature branches*). El documento [Proceso de desarrollo](../../fabric-development-process.md) *(solo en inglés)* explica cómo gestiona este repositorio ambos casos.

---

## Inicio rápido

### Requisitos previos

1. **Capacidad de Fabric** — Una capacidad de Fabric o de Power BI Premium para todas las áreas de trabajo
2. **Tres áreas de trabajo de Fabric** — Dev (conectada a Git), Test y Prod
3. **Entidad de servicio** — Con el rol de colaborador en las áreas de trabajo de Test y Prod
4. **Entornos de GitHub** — `Test` y `Prod` con secretos de ámbito de entorno
5. **Configuración de administración de Fabric** — Acceso de entidades de servicio a las API de Fabric habilitado en el portal de administración de Fabric, en la configuración de desarrollador (consulta la [configuración de inquilino para desarrolladores](https://learn.microsoft.com/es-es/fabric/admin/service-admin-portal-developer))

### Configuración

1. Crea una entidad de servicio y añádela como colaborador en las áreas de trabajo de Test y Prod
2. Crea los entornos de GitHub (`Test`, `Prod`) con los secretos `AZURE_TENANT_ID`, `AZURE_CLIENT_ID`, `AZURE_CLIENT_SECRET` y `FABRIC_WORKSPACE_ID` *(esta demostración usa un secreto de cliente por simplicidad; para producción, evalúa la [federación OIDC de GitHub](../../fabric-cicd-governance-considerations.md#identity-model--pick-the-right-identity-for-the-job) para eliminar el secreto almacenado)*
3. Conecta el área de trabajo de Dev a la rama `dev` mediante la integración de Git de Fabric (carpeta: `data/fabric/`)
4. Crea las ramas `dev`, `test` y `main`
5. Desarrolla en `dev`, fusiona en `test` (activa el despliegue en Test) y fusiona en `main` (activa el despliegue en Prod)

### Selección del método de implementación

Este repositorio incluye tres métodos de implementación. Configura la variable de repositorio `DEPLOY_METHOD` (Settings → Secrets and variables → Actions → Variables) para elegir cuál se ejecuta:

| Valor de `DEPLOY_METHOD` | Comportamiento |
|---|---|
| `fabric-cicd` *(o sin definir)* | Se ejecutan los flujos de trabajo de fabric-cicd existentes: la ruta predeterminada y recomendada |
| `fabric-cicd-bulk` | Los flujos de trabajo de fabric-cicd se ejecutan con la publicación masiva habilitada. En este repositorio siempre recurre a la publicación estándar elemento por elemento, porque `parameter.yml` usa las variables `$items` y `$workspace`; se incluye para demostrar el modo masivo experimental de la biblioteca |
| `bulk` | Se ejecutan en su lugar los flujos de trabajo de la API de importación masiva (versión preliminar) |
| cualquier otro valor | Se omiten todos los flujos de trabajo de implementación (valor seguro por defecto) |

Sea cual sea el método que se ejecute, el flujo de trabajo de ETL se encadena después mediante `workflow_run`. Consulta [Opciones de publicación de CI/CD](../../fabric-cicd-release-options.md#tooling-within-option-3-fabric-cicd-vs-bulk-apis) *(solo en inglés)* para conocer las ventajas e inconvenientes entre fabric-cicd y las API masivas.

Para instrucciones detalladas de configuración, consulta la [Guía de implementación](../../fabric-hybrid-cicd-guide.md#prerequisites--setup) *(solo en inglés)*. Para los *rulesets* de protección de ramas, las aprobaciones en el momento del despliegue y la ruta de promoción por rama de origen que aplica este repositorio, consulta las [Consideraciones de gobernanza](../../fabric-cicd-governance-considerations.md) *(solo en inglés)*.

---

## Referencias

- [Biblioteca de Python fabric-cicd](https://microsoft.github.io/fabric-cicd) — Documentación, primeros pasos y tipos de elemento compatibles *(solo en inglés)*
- [Integración de Git de Fabric](https://learn.microsoft.com/es-es/fabric/cicd/git-integration/intro-to-git-integration) — Documentación oficial
- [Flujos de trabajo reutilizables de GitHub Actions](https://docs.github.com/es/actions/sharing-automations/reusing-workflows) — `workflow_call`, entradas y secretos

---

## Sobre esta traducción

Este documento es una traducción de [README.md](../../README.md). La versión en inglés es la fuente autorizada y puede estar más actualizada.

La terminología sigue [`GLOSARIO.md`](GLOSARIO.md) y [`GUIA-DE-ESTILO.md`](GUIA-DE-ESTILO.md). Los enlaces a `learn.microsoft.com` apuntan a la versión en español, que Microsoft traduce automáticamente; ante cualquier duda técnica, consulta la versión en inglés.

Si detectas un error, abre una incidencia indicando el idioma. Si el error también existe en el original en inglés, **corrígelo primero allí**: consulta [`TRANSLATION.md`](../../TRANSLATION.md).
