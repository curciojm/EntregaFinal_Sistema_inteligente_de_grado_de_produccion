# Sistema multiagente de tutoría en Estadística y Metodología

Sistema inteligente de tutoría académica basado en agentes especializados, recuperación híbrida de información (RAG), evaluación de respuestas y supervisión humana. La aplicación integra una API asíncrona, procesamiento en segundo plano, persistencia del estado y observabilidad de las ejecuciones.

## Descripción general

El sistema permite que un usuario solicite explicaciones de conceptos de Estadística y Metodología de la Investigación, consulte fuentes bibliográficas o reciba una evaluación de sus respuestas.

La arquitectura utiliza un grafo de agentes coordinado por un supervisor. Los agentes especializados consultan una base de conocimientos mediante un recuperador híbrido que combina búsqueda léxica y similitud semántica. Cuando corresponde, el flujo incorpora una instancia de revisión humana antes de continuar con la evaluación y la síntesis de la respuesta final.

La aplicación expone sus funcionalidades mediante una API REST desarrollada con FastAPI. Las tareas se procesan de manera asíncrona mediante una cola de Redis y un Worker independiente. LangGraph administra el flujo de ejecución y permite persistir el estado necesario para interrumpir y reanudar las tareas.

El proyecto incorpora observabilidad mediante Arize Phoenix, instrumentación con OpenInference, registro de trazas en JSON y tests automatizados.

## Arquitectura

```text
                        Cliente
                           |
                           v
                    FastAPI / REST
                           |
                 +---------+---------+
                 |                   |
                 v                   v
           Estado en Redis     Cola de tareas
                                     |
                                     v
                                   Worker
                                     |
                                     v
                                  LangGraph
                                     |
                                  Supervisor
                                     |
                     +---------------+---------------+
                     |                               |
                     v                               v
               Agente profesor                Agente evaluador
                     |                               |
                     +---------------+---------------+
                                     |
                             Recuperador híbrido
                                     |
                             Base de conocimientos
                                     |
                                     v
                             Revisión humana (HITL)
                                     |
                                     v
                                  Síntesis
                                     |
                                     v
                                Resultado final
```

El diagrama representa los componentes principales y sus relaciones funcionales. El orden efectivo de ejecución depende de las decisiones del supervisor y de las condiciones definidas en el grafo.

### Componentes principales

- **FastAPI:** recibe las solicitudes y expone los endpoints de procesamiento, consulta de estado y aprobación humana.
- **Redis:** almacena el estado de las tareas y administra las colas de procesamiento y aprobación.
- **Worker asíncrono:** consume las tareas pendientes y ejecuta el grafo fuera del contexto de la solicitud HTTP.
- **LangGraph:** coordina los agentes, administra las transiciones del flujo y permite interrumpir y reanudar la ejecución.
- **Supervisor:** decide qué agente debe intervenir y cuándo corresponde finalizar el proceso.
- **Agente profesor:** recupera información teórica y fuentes relevantes para responder consultas académicas.
- **Agente evaluador:** evalúa las respuestas del usuario mediante una herramienta de similitud semántica y consulta información de respaldo.
- **Nodo de síntesis:** integra las contribuciones del sistema en una respuesta final.
- **Arize Phoenix:** permite inspeccionar las trazas y analizar las ejecuciones instrumentadas.
- **Trazas JSON:** conservan un registro adicional de los mensajes, las llamadas a herramientas y las intervenciones humanas.

## Recuperación híbrida de información (RAG)

El sistema utiliza un recuperador híbrido que combina dos mecanismos complementarios:

- **Búsqueda léxica BM25:** recupera documentos a partir de coincidencias entre términos.
- **Búsqueda vectorial:** utiliza embeddings para recuperar documentos semánticamente similares a la consulta.

Los resultados de ambos mecanismos se combinan mediante una estrategia de ponderación para producir una lista de documentos relevantes.

La recuperación híbrida se utiliza para buscar definiciones, explicaciones teóricas y fuentes bibliográficas. Los documentos recuperados constituyen el material de referencia de los agentes especializados.

### Herramientas de recuperación y evaluación

| Herramienta | Función |
|---|---|
| `buscar_concepto` | Recupera contenido teórico relevante para explicar un concepto. |
| `buscar_fuente` | Recupera información bibliográfica y números de página. |
| `evaluar_concepto` | Compara semánticamente la respuesta del usuario con el contenido recuperado. |

La herramienta de evaluación utiliza umbrales heurísticos para asignar una de cuatro categorías: `Mal`, `Incompleta`, `Bien` y `Muy bien`.

Estos umbrales no están calibrados empíricamente. La similitud semántica constituye una señal de comparación con los documentos recuperados, pero no es por sí sola una medida definitiva de la calidad conceptual de una respuesta.

### Análisis de la configuración del recuperador

*Sección pendiente de integrar.*

En esta sección se incorporará el análisis experimental de la Pre-Entrega 4, incluyendo las configuraciones de pesos evaluadas, los criterios de comparación, los resultados obtenidos y la justificación de la configuración seleccionada para el sistema final.

## Sistema multiagente

El grafo se organiza alrededor de un supervisor y dos agentes especializados, con un nodo de síntesis para la respuesta final.

### Supervisor

El supervisor utiliza salida estructurada mediante el modelo `DecisionSupervisor` para determinar el siguiente paso del flujo.

Las decisiones posibles son:

- `profesor`
- `evaluador`
- `FINISH`

El grafo incorpora un límite máximo de pasos para evitar ciclos excesivos. Los agentes utilizan mecanismos de fallback entre proveedores de modelos de lenguaje cuando corresponde.

### Agente profesor

El agente profesor utiliza las herramientas de recuperación para localizar información relevante y elaborar explicaciones fundamentadas en la base de conocimientos.

### Agente evaluador

El agente evaluador utiliza la herramienta `evaluar_concepto` para obtener una categoría inicial y puede consultar fuentes o contenido teórico adicional. Cuando recibe feedback humano, vuelve a analizar la respuesta considerando las observaciones recibidas.

### Síntesis

El nodo de síntesis combina las contribuciones acumuladas durante la ejecución y produce una respuesta final clara y breve.

## Human-in-the-loop (HITL)

El sistema incorpora un mecanismo de intervención humana mediante `interrupt()` y `Command(resume=...)` de LangGraph.

Cuando el flujo requiere una revisión, el grafo se interrumpe y la tarea pasa al estado `waiting_approval`. La persona puede aprobar la evaluación o rechazarla y proporcionar observaciones.

El flujo de aprobación utiliza el siguiente esquema:

```text
Ejecución del grafo
        |
        v
Solicitud de revisión humana
        |
        v
     interrupt()
        |
        v
  waiting_approval
        |
        v
 POST /approve/{job_id}
        |
        v
 Decisión y feedback en Redis
        |
        v
       Worker
        |
        v
 Command(resume=...)
        |
        v
 Reanudación del grafo
        |
        +----> Reevaluación o aclaración, si corresponde
        |
        v
      Síntesis
        |
        v
     completed
```

El feedback humano se incorpora a la siguiente evaluación cuando se solicita una revisión. El flujo puede volver a requerir intervención si la lógica del grafo así lo determina.

Las decisiones humanas también se registran como eventos asociados a la tarea y se incorporan a la traza JSON cuando finaliza correctamente.

## API REST

La API expone tres endpoints principales.

### `POST /process`

Recibe una consulta, genera un identificador único, guarda el estado inicial en Redis y agrega la tarea a la cola `multiagent_tasks`.

Ejemplo de solicitud:

```json
{
  "query": "Quiero que evalúes mi respuesta sobre la correlación."
}
```

Respuesta inicial:

```json
{
  "job_id": "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx",
  "status": "pending"
}
```

El procesamiento continúa en segundo plano. El cliente utiliza el identificador recibido para consultar el estado de la tarea.

### `GET /status/{job_id}`

Permite consultar el estado, el resultado y los posibles errores de una tarea.

Los estados contemplados por el flujo son:

- `pending`
- `processing`
- `waiting_approval`
- `completed`
- `failed`

### `POST /approve/{job_id}`

Recibe la decisión humana y, opcionalmente, el feedback para el agente evaluador.

Ejemplo de aprobación:

```json
{
  "decision": "approve",
  "feedback": ""
}
```

Ejemplo de rechazo con observaciones:

```json
{
  "decision": "reject",
  "feedback": "Revisá la explicación y agregá un ejemplo aplicado."
}
```

El endpoint verifica que la tarea exista y se encuentre esperando aprobación. Después guarda la decisión en Redis y la agrega a la cola `multiagent_approvals`. El Worker recupera esa información y reanuda el grafo.

La documentación interactiva de la API está disponible en `/docs` cuando el servidor está en ejecución.

## Procesamiento asíncrono y persistencia

La arquitectura desacopla la recepción de solicitudes del procesamiento de los agentes.

La cola principal utiliza la clave `multiagent_tasks`; las aprobaciones se procesan mediante `multiagent_approvals`. El estado de cada tarea se guarda en `task_status:{job_id}`.

El grafo se compila con `AsyncRedisSaver`, que permite persistir checkpoints asociados al identificador de conversación (`thread_id`). Esto permite reanudar la ejecución después de una interrupción de Human-in-the-loop.

El Worker actualiza el estado de la tarea según el resultado del procesamiento. Si se produce una excepción, registra el error y marca la tarea como `failed`.

## Observabilidad y trazas

La instrumentación utiliza Arize Phoenix, OpenInference y OpenTelemetry para observar las ejecuciones del sistema.

Phoenix permite inspeccionar las trazas y spans instrumentados, seguir la secuencia observable de ejecución y analizar las métricas disponibles de latencia y costo.

Además, el sistema conserva trazas locales en formato JSON. Según el flujo ejecutado, estas pueden incluir:

- Mensajes del usuario y respuestas de los agentes.
- Llamadas y resultados de herramientas.
- Identificación de los agentes involucrados.
- Eventos de aprobación humana y feedback.
- Secuencia observable de ejecución.

Las trazas representan la ejecución observable del sistema, no el razonamiento interno no observable de los modelos.

La instrumentación de Phoenix utiliza el endpoint local `http://localhost:6006/v1/traces`. La interfaz web se encuentra en `http://localhost:6006`.

## Manejo de errores

El proyecto incorpora manejo de errores en la ejecución de las herramientas, los agentes y el Worker.

Los errores de proveedores LLM se clasifican mediante los mecanismos definidos en `app/errors.py`. Los agentes contemplan fallback entre los proveedores configurados, y los errores que impiden completar una tarea se registran en su estado.

La información de error queda disponible al consultar `GET /status/{job_id}`.

## Tests automatizados

El proyecto incluye una suite de tests automatizados para verificar componentes de la API, el Worker y otras funcionalidades cubiertas por los casos de prueba.

La suite se ejecutó con éxito en el entorno de desarrollo: **40 tests ejecutados correctamente**.

**Importante:** antes de ejecutar los tests, es necesario iniciar la aplicación con `run.sh`. Algunos tests requieren que los servicios reales estén disponibles, por lo que no alcanza con ejecutar la suite de manera aislada.

### Procedimiento de ejecución

1. Abrir una terminal en la carpeta raíz del proyecto.
2. Iniciar la aplicación ejecutando `run.sh`.
3. Esperar a que Redis, Phoenix, FastAPI y el Worker estén disponibles.
4. Mantener esa terminal abierta mientras se ejecutan las pruebas.
5. Abrir una segunda terminal, activar el entorno virtual y ejecutar los tests.

Comando para iniciar la aplicación:

```bash
bash run.sh
```

En una segunda terminal, ejecutar:

```bash
python -m pytest -v
```

Al finalizar los tests, la aplicación puede detenerse con `Ctrl+C` en la terminal donde se ejecuta `run.sh`. Redis y Phoenix permanecen ejecutándose en Docker y pueden detenerse por separado cuando sea necesario.

## Requisitos

Para ejecutar el proyecto se necesita:

- Python 3.12 o la versión compatible especificada por las dependencias del proyecto.
- Docker y Docker Compose.
- Redis, iniciado mediante el archivo `compose.yml`.
- Acceso al índice de Pinecone utilizado por el recuperador.
- Una clave de API para el proveedor LLM configurado.
- Arize Phoenix para la observabilidad.
- Las dependencias de Python declaradas en `requirements.txt`.

Las claves de los proveedores alternativos son necesarias si se desea utilizar el mecanismo de fallback correspondiente.

## Instalación y configuración

### 1. Clonar el repositorio

```bash
git clone <URL_DEL_REPOSITORIO>
cd EntregaFinal_Sistema_inteligente_de_grado_de_produccion
```

### 2. Crear y activar el entorno virtual

Crear el entorno virtual:

```bash
python -m venv .venv
```

En Windows PowerShell:

```powershell
.\.venv\Scripts\Activate.ps1
```

En Linux o macOS:

```bash
source .venv/bin/activate
```

### 3. Instalar las dependencias

```bash
python -m pip install -r requirements.txt
```

### 4. Configurar las variables de entorno

Crear un archivo `.env` tomando como referencia `.env.example` y completar las credenciales necesarias.

Entre las variables utilizadas por la configuración anterior se encuentran:

```text
GOOGLE_API_KEY=
OPENAI_API_KEY=
ANTHROPIC_API_KEY=
PINECONE_API_KEY=
INDEX_NAME=
```

Los nombres definitivos deben coincidir con los utilizados en la configuración actual del proyecto. No deben incluirse credenciales reales en el repositorio.

### 5. Iniciar la aplicación

El script `run.sh` automatiza el inicio de los servicios y procesos necesarios para ejecutar la aplicación en el entorno Windows utilizado durante el desarrollo.

Desde la carpeta raíz del proyecto, ejecutar:

```bash
bash run.sh
```

El script realiza las siguientes operaciones:

1. Activa el entorno virtual de Python mediante `.venv/Scripts/activate`.
2. Inicia Redis y Phoenix con Docker Compose, utilizando `compose.yml`.
3. Espera hasta que Redis responda correctamente.
4. Configura `REDIS_URL`, utilizando `redis://localhost:6379` como valor predeterminado.
5. Inicia FastAPI mediante Uvicorn con `--reload`.
6. Inicia el Worker con `python -m app.worker`.
7. Espera a que FastAPI esté disponible y abre Swagger automáticamente en Windows cuando responde dentro del tiempo de espera configurado.

Las direcciones principales son:

| Servicio | Dirección |
|---|---|
| API y Swagger | `http://127.0.0.1:8000/docs` |
| Esquema OpenAPI | `http://127.0.0.1:8000/openapi.json` |
| Phoenix | `http://localhost:6006` |

Para detener la API y el Worker, presionar `Ctrl+C` en la terminal donde se ejecuta el script. Redis y Phoenix permanecen activos en Docker.

**Nota sobre el sistema operativo:** el `run.sh` descrito aquí utiliza rutas y comandos específicos de Windows, como `.venv/Scripts/activate`, `taskkill.exe` y `explorer.exe`.

También se incorporó una alternativa mediante un script de shell para Linux. Sin embargo, **esta alternativa no fue probada en Linux**, por lo que su funcionamiento en ese sistema operativo no está verificado y queda pendiente de validación.

## Ejemplo de uso

1. Iniciar la aplicación con `run.sh`.
2. Abrir `http://127.0.0.1:8000/docs`.
3. Ejecutar `POST /process` con una consulta.
4. Copiar el `job_id` devuelto.
5. Consultar `GET /status/{job_id}` hasta que la tarea finalice o requiera aprobación.
6. Si el estado es `waiting_approval`, enviar una decisión mediante `POST /approve/{job_id}`.
7. Consultar nuevamente el estado hasta obtener el resultado final.
8. Inspeccionar la ejecución en Phoenix y revisar la traza JSON correspondiente.

## Tecnologías utilizadas

- Python
- FastAPI y Uvicorn
- asyncio
- Pydantic
- Redis
- LangChain y LangGraph
- LangGraph Checkpoint Redis
- Modelos de lenguaje de los proveedores configurados
- Pinecone
- Embeddings y recuperación vectorial
- BM25 y recuperación híbrida
- scikit-learn
- Arize Phoenix
- OpenInference y OpenTelemetry
- pytest
- Docker Compose
- Git

## Estructura del proyecto

La estructura funcional principal es:

```text
.
├── app/
│   ├── agents/
│   │   ├── profesor.py
│   │   ├── evaluador.py
│   │   ├── supervisor.py
│   │   └── sintesis.py
│   ├── main.py
│   ├── worker.py
│   ├── graph_config.py
│   ├── schemas.py
│   ├── tools.py
│   ├── retriever.py
│   ├── db_config.py
│   ├── errors.py
│   ├── hitl.py
│   ├── observability.py
│   └── trace_utils.py
├── tests/
├── traces/
├── screenshots/
├── .env.example
├── compose.yml
├── requirements.txt
├── run.sh
└── README.md
```

La lista es orientativa y deberá ajustarse a los archivos presentes en la versión final del repositorio.

## Decisiones de diseño

Las principales decisiones de diseño son:

- Separar la API del procesamiento en segundo plano.
- Utilizar Redis como mecanismo de desacoplamiento y persistencia del estado de las tareas.
- Utilizar checkpoints para preservar el estado del grafo durante las interrupciones.
- Coordinar agentes especializados mediante un supervisor.
- Incorporar recuperación híbrida para consultar una base de conocimientos.
- Implementar Human-in-the-loop para permitir revisión y reevaluación con feedback.
- Registrar errores y estados explícitos de finalización.
- Instrumentar las ejecuciones para facilitar su inspección.
- Conservar trazas detalladas de las ejecuciones.
- Automatizar pruebas mediante una suite de tests.
- Automatizar el inicio de los servicios y procesos mediante `run.sh`.

## Uso de herramientas de asistencia

Durante el desarrollo se consultaron materiales del curso, documentación técnica y recursos disponibles en Internet. También se utilizó ChatGPT como apoyo para resolver dudas conceptuales, revisar implementaciones y depurar problemas durante el desarrollo.