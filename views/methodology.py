import streamlit as st

st.title("Methodology")

st.markdown(
    """
Social Bot answers questions using **Retrieval-Augmented Generation (RAG)**: it
retrieves the most relevant passages from the sources you provide and asks a
language model to answer using only that material. This page documents how the
application is built, how data flows through it, and the process flow for each
use case.
"""
)

# ---------------------------------------------------------------------------
# Architecture & implementation
# ---------------------------------------------------------------------------
st.header("System architecture")

st.markdown(
    """
The app is a multipage Streamlit application:

- **`app.py`** — the entry point. It sets global page config, enforces the
  password gate (`utility.check_password`), and defines navigation across the
  **Social Bot**, **About Us**, **Methodology**, and **Disclaimer** pages. Every
  page load runs this script first, so the single password check protects the
  whole app.
- **`views/chatbot.py`** — the RAG core: source ingestion, indexing, retrieval,
  and the chat loop.
- **`utility.py`** — the authentication helper.

### Models
- **Embeddings:** OpenAI `text-embedding-3-small` — turns text into vectors for
  similarity search.
- **Chat:** OpenAI `gpt-4o-mini` — generates the streamed answer.

### Where data lives
- **Vector store:** a [Chroma](https://www.trychroma.com/) database persisted to
  disk under a temp directory, in a subfolder unique to each browser **session**
  (`BASE_PERSIST_DIR/<session_id>`). Sessions never share an index.
- **Conversation:** held in `st.session_state` (memory only) for the life of the
  session; downloadable as a transcript.
- **Secrets:** the OpenAI API key and app password come from `st.secrets`
  (locally `.streamlit/secrets.toml`; on Streamlit Cloud the Secrets panel).

### Caching layers
- **`@st.cache_data` (1-hour TTL)** on URL fetching — an already-fetched page is
  not re-downloaded on every rerun.
- **`@st.cache_resource`** on the vector store — the same Chroma handle is reused
  across reruns so sources can be added and removed incrementally.

### Security & isolation
- **Password gate** on every page load.
- **SSRF protection:** user-supplied URLs are validated (`_validate_public_url`)
  to allow only public `http`/`https` addresses, blocking internal, loopback,
  and cloud-metadata targets.
- **Per-session isolation:** each session has a random `session_id` that scopes
  its on-disk vector store.
"""
)

st.header("End-to-end data flow")

st.markdown(
    """
At a high level, data moves through the system in two phases — **ingestion**
(building the index) and **query** (answering a question):
"""
)

st.graphviz_chart(
    r"""
digraph {
  rankdir=LR;
  node [shape=box, style="rounded,filled", fillcolor="#eef3fb", fontname="Helvetica"];
  edge [fontname="Helvetica", fontsize=10];

  subgraph cluster_ingest {
    label="Ingestion"; style=dashed; color="#9bb4d6";
    src [label="Sources\n(URLs + documents)"];
    chunk [label="Split into\noverlapping chunks"];
    emb [label="Embed chunks\n(text-embedding-3-small)"];
    store [label="Chroma vector store\n(per session)"];
    src -> chunk -> emb -> store;
  }

  subgraph cluster_query {
    label="Query"; style=dashed; color="#9bb4d6";
    q [label="User question"];
    qemb [label="Embed question"];
    ret [label="Retrieve top-k\nsimilar chunks"];
    llm [label="gpt-4o-mini\n(answer from context)"];
    ans [label="Streamed answer\n+ cited sources"];
    q -> qemb -> ret -> llm -> ans;
  }

  store -> ret [label="similarity\nsearch", constraint=false, color="#5b7cb3"];
}
"""
)

st.markdown(
    """
The sections below break down the process flow for each **use case** in the
application.
"""
)

# ---------------------------------------------------------------------------
# 1. Authentication
# ---------------------------------------------------------------------------
st.header("1. Authentication")

st.markdown(
    """
Before anything else, the entry script gates access. `check_password()` reads
the expected password from `st.secrets`, compares it in constant time
(`hmac.compare_digest`), and remembers success in session state so the prompt
only appears once per session. If no password is configured, the app explains
that instead of crashing.
"""
)

st.graphviz_chart(
    r"""
digraph {
  rankdir=TB;
  node [shape=box, style="rounded,filled", fillcolor="#eef3fb", fontname="Helvetica"];
  edge [fontname="Helvetica", fontsize=10];

  start [shape=oval, fillcolor="#dcedc8", label="User opens app"];
  cfg [label="app.py:\nset_page_config"];
  secret [shape=diamond, fillcolor="#fff3cd", label="password secret\nconfigured?"];
  noconf [shape=box, fillcolor="#f8d7da", label="Show 'no password\nconfigured' message"];
  authed [shape=diamond, fillcolor="#fff3cd", label="already authenticated\nthis session?"];
  prompt [label="Show password input"];
  correct [shape=diamond, fillcolor="#fff3cd", label="password correct?"];
  mark [label="Mark session\nauthenticated"];
  stop [shape=box, fillcolor="#f8d7da", label="st.stop()\n(block, show error)"];
  run [shape=oval, fillcolor="#dcedc8", label="Run navigation\n(render pages)"];

  start -> cfg -> secret;
  secret -> noconf [label="no"];
  secret -> authed [label="yes"];
  authed -> run [label="yes"];
  authed -> prompt [label="no"];
  prompt -> correct;
  correct -> mark [label="yes"];
  correct -> stop [label="no"];
  mark -> run;
}
"""
)

# ---------------------------------------------------------------------------
# 2. Add a web page (URL)
# ---------------------------------------------------------------------------
st.header("2. Add a web page as a source")

st.markdown(
    """
When a URL is added, the app validates it, then tries a fast direct HTTP fetch.
If the page yields too little text — typically a JavaScript single-page app — it
falls back to the Jina Reader rendering proxy, which executes the page's
JavaScript and returns clean text (this also sidesteps datacenter-IP blocks).
Successful fetches are cached for an hour. The resulting chunks are embedded and
added to the index.
"""
)

st.graphviz_chart(
    r"""
digraph {
  rankdir=TB;
  node [shape=box, style="rounded,filled", fillcolor="#eef3fb", fontname="Helvetica"];
  edge [fontname="Helvetica", fontsize=10];

  u [shape=oval, fillcolor="#dcedc8", label="User enters URL(s)"];
  sync [label="Source sync detects\na new / changed URL"];
  cache [shape=diamond, fillcolor="#fff3cd", label="cached?\n(cache_data, 1h TTL)"];
  val [label="_validate_public_url\n(SSRF check)"];
  direct [label="_fetch_direct\n(plain HTTP)"];
  ok1 [shape=diamond, fillcolor="#fff3cd", label="enough\nreadable text?"];
  jina [label="_fetch_via_jina\n(render JavaScript)"];
  ok2 [shape=diamond, fillcolor="#fff3cd", label="enough\nreadable text?"];
  warn [shape=box, fillcolor="#f8d7da", label="Warn & skip\n(keep last good)"];
  split [label="_split into chunks\n(source = URL)"];
  embed [label="Embed + add_documents\nto Chroma"];
  done [shape=oval, fillcolor="#dcedc8", label="Index updated"];

  u -> sync -> cache;
  cache -> split [label="hit"];
  cache -> val [label="miss"];
  val -> direct -> ok1;
  ok1 -> split [label="yes"];
  ok1 -> jina [label="no"];
  jina -> ok2;
  ok2 -> split [label="yes"];
  ok2 -> warn [label="no"];
  split -> embed -> done;
}
"""
)

# ---------------------------------------------------------------------------
# 3. Upload a document
# ---------------------------------------------------------------------------
st.header("3. Upload a document")

st.markdown(
    """
Uploaded PDF or text files are written to a temporary file (the loaders need a
path), parsed with the matching loader, split into chunks stamped with the
original filename, then embedded and added to the index. A file that cannot be
read is skipped with a warning rather than aborting the whole batch.
"""
)

st.graphviz_chart(
    r"""
digraph {
  rankdir=TB;
  node [shape=box, style="rounded,filled", fillcolor="#eef3fb", fontname="Helvetica"];
  edge [fontname="Helvetica", fontsize=10];

  u [shape=oval, fillcolor="#dcedc8", label="User uploads\nPDF / TXT file(s)"];
  sync [label="Source sync detects\na new / changed file"];
  tmp [label="Write bytes to\ntemporary file"];
  kind [shape=diamond, fillcolor="#fff3cd", label="file type?"];
  pdf [label="PyPDFLoader"];
  txt [label="TextLoader (utf-8)"];
  err [shape=box, fillcolor="#f8d7da", label="Warn & skip\n(e.g. unreadable)"];
  split [label="_split into chunks\n(source = filename)"];
  embed [label="Embed + add_documents\nto Chroma"];
  done [shape=oval, fillcolor="#dcedc8", label="Index updated"];

  u -> sync -> tmp -> kind;
  kind -> pdf [label=".pdf"];
  kind -> txt [label=".txt / other"];
  kind -> err [label="load error"];
  pdf -> split;
  txt -> split;
  split -> embed -> done;
}
"""
)

# ---------------------------------------------------------------------------
# 4. Ask a question (RAG)
# ---------------------------------------------------------------------------
st.header("4. Ask a question")

st.markdown(
    """
When the user sends a message, it is stored in history. If an index exists, the
question is embedded and the top-**k** most similar chunks are retrieved and
folded into a RAG system prompt that instructs the model to answer **only** from
that context. With no index, the base system prompt is used. The last 20
messages plus the system prompt are sent to `gpt-4o-mini`, and the reply streams
back. If retrieved chunks were used, a **View Sources** panel lists them.
"""
)

st.graphviz_chart(
    r"""
digraph {
  rankdir=TB;
  node [shape=box, style="rounded,filled", fillcolor="#eef3fb", fontname="Helvetica"];
  edge [fontname="Helvetica", fontsize=10];

  q [shape=oval, fillcolor="#dcedc8", label="User sends\nchat message"];
  save [label="Append to history\n(session_state)"];
  has [shape=diamond, fillcolor="#fff3cd", label="vector store\navailable?"];
  emb [label="Embed query"];
  ret [label="Retrieve top-k chunks\n(retriever.invoke)"];
  rag [label="build_rag_system_prompt\n(context + 'use only this')"];
  base [label="Use base\nsystem prompt"];
  call [label="gpt-4o-mini\nchat.completions (stream,\nlast 20 messages)"];
  stream [label="Stream tokens to UI"];
  used [shape=diamond, fillcolor="#fff3cd", label="sources used?"];
  cite [label="Show 'View Sources'\n(retrieved chunks)"];
  store [label="Save reply to history"];
  done [shape=oval, fillcolor="#dcedc8", label="Answer shown"];

  q -> save -> has;
  has -> emb [label="yes"];
  has -> base [label="no"];
  emb -> ret -> rag -> call;
  base -> call;
  call -> stream -> used;
  used -> cite [label="yes"];
  used -> store [label="no"];
  cite -> store -> done;
}
"""
)

# ---------------------------------------------------------------------------
# 5. Incremental index synchronization
# ---------------------------------------------------------------------------
st.header("5. Keeping the index in sync")

st.markdown(
    """
On each rerun the app reconciles the vector store with the current source list
instead of rebuilding it. Changing the chunk size or overlap invalidates every
chunk, so the index is rebuilt; otherwise only new or changed sources are added
and removed sources are deleted. A per-session record maps each source to the
chunk IDs it produced, so deletions are precise.
"""
)

st.graphviz_chart(
    r"""
digraph {
  rankdir=TB;
  node [shape=box, style="rounded,filled", fillcolor="#eef3fb", fontname="Helvetica"];
  edge [fontname="Helvetica", fontsize=10];

  start [shape=oval, fillcolor="#dcedc8", label="Rerun with\ncurrent source list"];
  empty [shape=diamond, fillcolor="#fff3cd", label="record stale?\n(store emptied)"];
  reset [label="Reset record"];
  settings [shape=diamond, fillcolor="#fff3cd", label="chunk settings\nchanged?"];
  rebuild [label="Delete all chunks,\nreset record"];
  diff [label="Diff desired vs indexed\n(source id + signature)"];
  rem [label="Delete removed /\nchanged sources (by IDs)"];
  add [label="Fetch, embed & add\nnew / changed sources"];
  update [label="Update record\n(IDs per source)"];
  done [shape=oval, fillcolor="#dcedc8", label="Store matches\nsource list"];

  start -> empty;
  empty -> reset [label="yes"];
  empty -> settings [label="no"];
  reset -> settings;
  settings -> rebuild [label="yes"];
  settings -> diff [label="no"];
  rebuild -> diff;
  diff -> rem -> add -> update -> done;
}
"""
)

# ---------------------------------------------------------------------------
# Settings reference
# ---------------------------------------------------------------------------
st.header("Settings that affect answers")

st.markdown(
    """
- **Chunk size / overlap** — how sources are divided before indexing. Changing
  these rebuilds the index.
- **Chunks to retrieve (k)** — how much context is gathered per question.
- **Temperature** — how deterministic the model's wording is (lower is more
  focused and consistent).
- **System prompt** — the base instruction that frames the assistant's role.
"""
)
