import asyncio

from langchain_pinecone import PineconeVectorStore
from pinecone import Pinecone, ServerlessSpec

from app.db_config import (
    DIMENSIONS,
    EMBEDDINGS,
    INDEX_NAME,
    NAMESPACE,
    PINECONE_API_KEY,
)
from app.setup import procesamiento_desde_pdfs, recuperar_documentos_de_pinecone


async def setup_vector_infrastructure(
    INDEX_NAME: str,
    DIMENSIONS: int
):

    pc = Pinecone(api_key=PINECONE_API_KEY)

    if INDEX_NAME not in pc.list_indexes().names():

        print(f"Creando índice: {INDEX_NAME}...")

        pc.create_index(
            name=INDEX_NAME,
            dimension=DIMENSIONS,
            metric="cosine",
            spec=ServerlessSpec(
                cloud="aws",
                region="us-east-1"
            )
        )

        while not pc.describe_index(INDEX_NAME).status["ready"]:
            await asyncio.sleep(1)

    index = pc.Index(INDEX_NAME)

    stats = index.describe_index_stats()

    vector_count = (
        stats["namespaces"]
        .get(NAMESPACE, {})
        .get("vector_count", 0)
    )

    if vector_count == 0:

        documentos_procesados = procesamiento_desde_pdfs()

        vectorstore = PineconeVectorStore.from_documents(
            documents=documentos_procesados,
            embedding=EMBEDDINGS,
            index_name=INDEX_NAME,
            namespace=NAMESPACE,
        )

    else:

        documentos_procesados = recuperar_documentos_de_pinecone(index)

        vectorstore = PineconeVectorStore(
            index_name=INDEX_NAME,
            embedding=EMBEDDINGS,
            namespace=NAMESPACE,
        )

    print(
        "📦 Vectores en el namespace:",
        stats["namespaces"].get(NAMESPACE, {})
    )

    print(f"Estado del índice: {stats}")

    return index, vectorstore, documentos_procesados


index, vectorstore, documentos_procesados = asyncio.run(
    setup_vector_infrastructure(INDEX_NAME, DIMENSIONS)
)