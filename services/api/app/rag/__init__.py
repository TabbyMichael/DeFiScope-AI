"""Grounded "Ask the analyst" RAG chat (roadmap #8).

Package layout:
- ``chunking``: split source markdown / evidence into citable chunks.
- ``lexical``: pure-Python BM25 ranking - the offline retrieval path.
- ``embeddings``: OpenAI-compatible vector embedding, ``None`` when no key.
- ``service``: retrieve -> ground -> answer (LLM or extractive) with citations.
- ``ingest``: build chunks from docs + protocol evidence and persist them.
"""
