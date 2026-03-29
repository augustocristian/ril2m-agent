"""RAG node – builds a vector store from annotated test cases and retrieves
similar cases for non-annotated ones using Ollama embeddings + ChromaDB."""

from __future__ import annotations

import logging

from langchain_chroma import Chroma
from langchain_core.documents import Document
from langchain_ollama import OllamaEmbeddings

from agent.config import get_settings
from agent.state import AgentState, TestCase

logger = logging.getLogger(__name__)

# Module-level cache so the vector store persists across invocations in the
# same process.
_vectorstore: Chroma | None = None


def _test_to_document(tc: TestCase) -> Document:
    """Convert an annotated TestCase into a LangChain Document.

    The page_content is the method body **without** the @AccessMode annotation
    so that retrieval is based on code semantics, not on the annotation itself.
    """
    # Strip @AccessMode from the body text used for embedding
    body_for_embed = tc.method_body
    metadata = {
        "file_path": tc.file_path,
        "class_name": tc.class_name,
        "method_name": tc.method_name,
        "access_mode": tc.access_mode_value or "",
        "annotations": "|".join(tc.annotations),
    }
    return Document(page_content=body_for_embed, metadata=metadata)


def _get_vectorstore(force_rebuild: bool = False) -> Chroma:
    """Return (and optionally rebuild) the ChromaDB vector store."""
    global _vectorstore
    if _vectorstore is not None and not force_rebuild:
        return _vectorstore

    settings = get_settings()
    embeddings = OllamaEmbeddings(
        model=settings.ollama_embed_model,
        base_url=settings.ollama_base_url,
    )
    _vectorstore = Chroma(
        collection_name=settings.chroma_collection_name,
        embedding_function=embeddings,
        persist_directory=settings.chroma_persist_dir,
    )
    return _vectorstore


def build_rag_index(state: AgentState) -> dict:
    """Index all annotated test cases into the vector store."""
    if not state.annotated_tests:
        logger.warning("No annotated tests to index – RAG will have no corpus.")
        return {"rag_ready": False, "current_step": "rag_empty"}

    docs = [_test_to_document(tc) for tc in state.annotated_tests]
    logger.info("Indexing %d annotated test cases into ChromaDB …", len(docs))

    vs = _get_vectorstore(force_rebuild=True)
    vs.add_documents(docs)

    logger.info("RAG index built successfully.")
    return {"rag_ready": True, "current_step": "rag_ready"}


def retrieve_similar(test_case: TestCase, k: int = 3) -> list[Document]:
    """Retrieve the *k* most similar annotated test cases for a given test."""
    vs = _get_vectorstore()
    return vs.similarity_search(test_case.method_body, k=k)
