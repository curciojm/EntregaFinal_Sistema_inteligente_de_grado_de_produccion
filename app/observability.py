from openinference.instrumentation.langchain import LangChainInstrumentor
from phoenix.otel import register


def configurar_observabilidad():

    tracer_provider = register(
        project_name="multiagente-estadistica",
        endpoint="http://localhost:6006/v1/traces",
    )

    LangChainInstrumentor().instrument(
        tracer_provider=tracer_provider
    )

    return tracer_provider