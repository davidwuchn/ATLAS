FROM docker.io/python:3.11-slim

WORKDIR /app

# Install system deps
RUN apt-get update && apt-get install -y --no-install-recommends curl && rm -rf /var/lib/apt/lists/*

# Copy benchmark modules (V3 pipeline depends on them)
COPY benchmark/ /app/benchmark/
COPY v3-service/main.py /app/main.py
# Structural call-graph reasoning (issue #39): tree-sitter-backed call graph.
# Pure stdlib + the tree-sitter grammars installed below; no extra deps.
COPY v3-service/graph/ /app/graph/

# Install Python deps
RUN pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu

# GH #39 v1: tree-sitter for /internal/ast_edit. Wheels ship pre-built so
# this doesn't pull in build-essential. Languages match the selector
# translator — extend when adding new languages.
RUN pip install --no-cache-dir \
        tree_sitter \
        tree_sitter_python \
        tree_sitter_html \
        tree_sitter_javascript

EXPOSE 8070

CMD ["python", "main.py"]
