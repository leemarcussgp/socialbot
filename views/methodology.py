import streamlit as st

st.title("Methodology")

st.markdown(
    """
Social Bot answers questions using **Retrieval-Augmented Generation (RAG)**: it
retrieves the most relevant passages from the sources you provide and asks a
language model to answer using only that material.

### 1. Gather sources
You supply the knowledge base from the sidebar:
- **Web pages** — one URL per line. Each page is fetched server-side. Only
  public `http`/`https` addresses are allowed; internal and private addresses
  are rejected to prevent misuse.
- **Documents** — one or more PDF or text files uploaded directly.

### 2. Split into chunks
Each source is broken into overlapping text **chunks** (default ~800 characters
with ~100 characters of overlap). Overlap preserves context that would
otherwise be cut off at a chunk boundary. Chunk size and overlap are adjustable
under **System Configuration**.

### 3. Embed and index
Every chunk is converted into a numeric **embedding** with OpenAI's
`text-embedding-3-small` model and stored in a Chroma vector database. Each
browser session gets its own isolated index, so your sources are never mixed
with another user's.

### 4. Retrieve
When you ask a question, it is embedded the same way, and the **k** most similar
chunks are retrieved from the index (k is adjustable; default 4). These passages
form the context for the answer.

### 5. Generate
The retrieved context, the system prompt, and recent conversation history are
sent to the chat model (`gpt-4o-mini`). The model is instructed to answer using
**only** the retrieved context — if the answer isn't there, it says so rather
than guessing. The reply streams back token by token.

### 6. Show the sources
Each answer includes an expandable **View Sources** section listing the exact
chunks (with document name and page, where available) that informed it, so you
can verify the response.

### Settings that affect answers
- **Chunk size / overlap** — how sources are divided before indexing.
- **Chunks to retrieve (k)** — how much context is gathered per question.
- **Temperature** — how deterministic the model's wording is (lower is more
  focused and consistent).
"""
)
