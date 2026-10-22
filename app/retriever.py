from langchain_classic.retrievers import EnsembleRetriever
from langchain_community.retrievers import BM25Retriever

from app.db_ingest import documentos_procesados, vectorstore

retriever_bm25 = BM25Retriever.from_documents(
    documentos_procesados
)

retriever_bm25.k = 5

retriever_vectorial = vectorstore.as_retriever(
    search_kwargs={"k": 5},
)

# Los mejores resultados de Recall@5 y Precision@5 se obtuvieron con estos pesos (ver README.md).
retriever_hibrido = EnsembleRetriever(
    retrievers=[retriever_bm25, retriever_vectorial],
    weights=[0.25, 0.75],
)