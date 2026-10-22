import os
import re

import tiktoken
from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter

from app.logging_config import logger


class DocumentProcessor:

    def __init__(self, model_encoding: str = "cl100k_base"):
        self.tokenizer = tiktoken.get_encoding(model_encoding)

        # Parametros establecidos a partir de la evaluación de la PreEntrega 4, ver README.md
        self.splitter = RecursiveCharacterTextSplitter(
            chunk_size=400,
            chunk_overlap=100,
            length_function=self.calculate_tokens,
            separators=["\n\n", "\n", ".", " ", ""],
        )

    def clean_text(self, text: str) -> str:
        """Limpia espacios excesivos manteniendo la estructura del documento."""

        text = re.sub(r"[ \t]+", " ", text)
        text = re.sub(r"\n[ \t]+", "\n", text)
        text = re.sub(r"\n{3,}", "\n\n", text)

        return text.strip()

    def calculate_tokens(self, text: str) -> int:
        return len(self.tokenizer.encode(text))

    def process_document(self, documents: list[Document]) -> list[Document]:
        """Limpieza, chunking y enriquecimiento de metadata."""
        processed_chunks = []

        for document in documents:

            cleaned_text = self.clean_text(document.page_content)

            chunks = self.splitter.create_documents(
                [cleaned_text],
                metadatas=[document.metadata]
            )

            processed_chunks.extend(chunks)

        for i, chunk in enumerate(processed_chunks):

            nombre_archivo = os.path.basename(chunk.metadata["source"])

            nombre_sin_extension = os.path.splitext(nombre_archivo)[0]

            # La fuente y la categoría se obtienen del nombre del archivo, separadas por una coma.
            fuente, categoria = nombre_sin_extension.split(
                ",",
                maxsplit=1
            )

            chunk.metadata["fuente"] = fuente.strip()

            chunk.metadata["pagina"] = int(chunk.metadata["page"]) + 1
            
            chunk.metadata["categoria"] = categoria.strip()

            # Se fuerza a entero porque Pinecone puede devolver este valor como float.
            chunk.metadata["chunk_id"] = int(i)

            token_count = self.calculate_tokens(
                chunk.page_content
            )

            logger.info(
                f"Chunk {i} creado: {token_count} tokens "
                f"(página {chunk.metadata['pagina']})."
            )

        return processed_chunks