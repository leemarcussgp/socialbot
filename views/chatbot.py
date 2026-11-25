import ipaddress
import os
import socket
import tempfile
import time
import traceback
import uuid
from urllib.parse import urlparse

import requests
import streamlit as st
from openai import OpenAI
from langchain_community.document_loaders import PyPDFLoader, TextLoader, WebBaseLoader
from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_openai import OpenAIEmbeddings
from langchain_chroma import Chroma

st.title("Social Bot")

# OpenAI client
client = OpenAI(
    api_key=st.secrets["OPENAI_API_KEY"],
    timeout=30.0,
    max_retries=3,
)
os.environ.setdefault(
    "USER_AGENT",
    "Mozilla/5.0 (compatible; SocialBot/1.0; +https://streamlit.io)",
)

# Base directory for Chroma stores. Kept outside cloud-synced folders because
# OneDrive can mark database files read-only or expose transient file-state
# changes that break SQLite/Chroma. Each browser session gets its own
# subdirectory (see _session_persist_dir) so concurrent users never share or
# overwrite one another's indexed documents, which may contain sensitive
# client data.
BASE_PERSIST_DIR = os.path.join(tempfile.gettempdir(), "socialbot-chroma-db")
# Embedding model for the vector store. Stores are built fresh per session, so
# they always reflect the current model.
EMBEDDING_MODEL = "text-embedding-3-small"
# Chat completion model.
CHAT_MODEL = "gpt-4o-mini"
# Cap how many prior messages are sent to the API so token cost and context
# usage stay bounded on long conversations. Full history is still kept in
# session state for display and download.
MAX_HISTORY_MESSAGES = 20


def _session_persist_dir(session_id):
    """Return this session's Chroma directory.

    Scoping by ``session_id`` keeps concurrent users isolated from each other;
    each session owns one mutable collection that sources are added to and
    removed from incrementally.
    """
    return os.path.join(BASE_PERSIST_DIR, session_id)


def get_embeddings():
    """Return the OpenAI embeddings model used for the vector store."""
    return OpenAIEmbeddings(
        model=EMBEDDING_MODEL,
        api_key=st.secrets["OPENAI_API_KEY"],
    )

# Initialize conversation history
if "messages" not in st.session_state:
    st.session_state.messages = []

# Stable per-session id used to isolate this user's vector store on disk.
if "session_id" not in st.session_state:
    st.session_state.session_id = uuid.uuid4().hex

def _split(documents, source, chunk_size, chunk_overlap):
    """Split loaded documents into chunks and stamp each with its source label."""
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
    )
    chunks = splitter.split_documents(documents)
    for chunk in chunks:
        chunk.metadata["source"] = source
    return chunks


def load_and_split(uploaded_file, chunk_size=800, chunk_overlap=100):
    """Load a Streamlit-uploaded PDF or text file and return split Document chunks."""
    # Loaders need a file path, so write the bytes to a temp file first.
    suffix = os.path.splitext(uploaded_file.name)[1].lower()
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        tmp.write(uploaded_file.getvalue())
        tmp_path = tmp.name

    try:
        if suffix == ".pdf":
            loader = PyPDFLoader(tmp_path)
        else:
            loader = TextLoader(tmp_path, encoding="utf-8")
        documents = loader.load()
    finally:
        os.remove(tmp_path)

    # Record the original filename (the loader only sees the temp path).
    return _split(documents, uploaded_file.name, chunk_size, chunk_overlap)


def _validate_public_url(url):
    """Reject URLs that could be used for server-side request forgery (SSRF).

    Only ``http``/``https`` are allowed, and every address the host resolves to
    must be a public (globally routable) IP. This blocks attempts to make the
    server fetch internal services, loopback, or cloud metadata endpoints
    (e.g. 169.254.169.254). Note this does not defend against DNS rebinding,
    which would require a custom HTTP transport that re-validates on connect.
    """
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise ValueError("Only http and https URLs are supported.")
    host = parsed.hostname
    if not host:
        raise ValueError("The URL is missing a host.")

    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    try:
        addrinfos = socket.getaddrinfo(host, port, proto=socket.IPPROTO_TCP)
    except socket.gaierror as exc:
        raise ValueError(f"Could not resolve host: {host}") from exc

    for info in addrinfos:
        ip = ipaddress.ip_address(info[4][0])
        if not ip.is_global or ip.is_multicast:
            raise ValueError("Refusing to fetch a non-public address.")


# Jina AI Reader renders JavaScript server-side and returns clean text, so it
# handles single-page apps that a plain HTTP fetch cannot, and fetches from its
# own infrastructure (which also sidesteps datacenter-IP blocks).
JINA_READER_PREFIX = "https://r.jina.ai/"


def _usable_text(documents):
    """True if the loaded documents contain enough real, non-JS-gated text."""
    text = "\n".join(
        doc.page_content.strip() for doc in documents if doc.page_content.strip()
    )
    if len(text) < 300:
        return False
    if "you need to enable javascript" in text.lower():
        return False
    return True


def _fetch_direct(url):
    """Fetch a page over plain HTTP (no JavaScript rendering)."""
    return WebBaseLoader(
        url,
        header_template={
            "User-Agent": os.environ["USER_AGENT"],
            "Accept": "text/html,application/xhtml+xml",
        },
        requests_kwargs={"timeout": 30},
        raise_for_status=True,
    ).load()


def _fetch_via_jina(url):
    """Fetch a JavaScript-rendered page's text through the Jina Reader proxy."""
    resp = requests.get(
        JINA_READER_PREFIX + url,
        headers={"User-Agent": os.environ["USER_AGENT"]},
        timeout=60,
    )
    resp.raise_for_status()
    return [Document(page_content=resp.text, metadata={"source": url})]


@st.cache_data(ttl=3600, show_spinner=False)
def load_and_split_url(url, chunk_size=800, chunk_overlap=100):
    """Fetch a web page and return split Document chunks labeled with the URL.

    Tries a fast direct HTTP fetch first; if the page yields too little text
    (e.g. a JavaScript single-page app) or the direct fetch fails, it falls
    back to the Jina Reader rendering proxy.

    The result is cached per (url, chunk_size, chunk_overlap) for one hour, so
    an already-fetched page is not re-downloaded on every rerun (including when
    other sources are added or chat messages are sent). Only successful results
    are cached; a failed fetch raises and is retried on the next run. The TTL
    bounds how stale a cached page can get.
    """
    _validate_public_url(url)
    last_error = None

    # 1) Direct fetch. Retry transient network errors, but if the page simply
    #    has no readable text, stop retrying and move to the rendering proxy.
    for attempt in range(3):
        try:
            documents = _fetch_direct(url)
            if _usable_text(documents):
                return _split(documents, url, chunk_size, chunk_overlap)
            last_error = ValueError("The page did not contain enough readable text.")
            break  # A JS/empty page won't improve on retry.
        except Exception as exc:
            last_error = exc
            if attempt < 2:
                time.sleep(1 * (attempt + 1))

    # 2) Fallback: render JavaScript via Jina Reader.
    for attempt in range(3):
        try:
            documents = _fetch_via_jina(url)
            if _usable_text(documents):
                return _split(documents, url, chunk_size, chunk_overlap)
            last_error = ValueError("The rendered page still had no readable text.")
        except Exception as exc:
            last_error = exc
        if attempt < 2:
            time.sleep(1 * (attempt + 1))

    raise RuntimeError(
        f"Could not fetch usable text (direct and rendered): {last_error}"
    )


@st.cache_resource
def get_vectorstore(session_id):
    """Return this session's persistent, mutable Chroma store.

    The same object is reused across reruns (cached per ``session_id``), so
    sources can be added and removed incrementally instead of rebuilding the
    whole index whenever the source list changes.
    """
    persist_dir = _session_persist_dir(session_id)
    os.makedirs(persist_dir, exist_ok=True)
    return Chroma(
        embedding_function=get_embeddings(),
        persist_directory=persist_dir,
    )


def _store_is_empty(store):
    """True if the store currently holds no vectors."""
    try:
        return len(store.get(limit=1)["ids"]) == 0
    except Exception:
        return True


def build_rag_system_prompt(base_prompt, context):
    """Combine the user's system prompt with RAG constraints and the context."""
    return (
        f"{base_prompt}\n\n"
        "Answer the user's question using ONLY the information in the context below. "
        "Do not use any outside knowledge. "
        'If the answer is not contained in the context, reply exactly: '
        '"I couldn\'t find that information in the uploaded document."\n\n'
        "Context:\n"
        f"{context}"
    )


def retrieve_context(vectorstore, query, k=4):
    """Retrieve the top-k relevant chunks for a query.

    Returns a tuple of (joined_string, list_of_documents).
    """
    retriever = vectorstore.as_retriever(search_kwargs={"k": k})
    docs = retriever.invoke(query)
    joined = "\n\n---\n\n".join(doc.page_content for doc in docs)
    return joined, docs


# Sidebar controls
with st.sidebar:
    with st.expander("📝 User Inputs and Settings", expanded=True):
        url_text = st.text_area(
            "🌐 Web Pages (one URL per line)",
            value=(
#                "https://www.msf.gov.sg/what-we-do/comcare\n"
#                "https://www.mof.gov.sg/news-resources/individual-support-schemes/\n"
#                "https://www.moe.gov.sg/financial-matters/financial-assistance"
                "https://supportgowhere.life.gov.sg/schemes/COMCARE-SMTA/comcare-assistance\n"
                "https://supportgowhere.life.gov.sg/schemes/COMCARE-SMTA/comcare-assistance\n"
                "https://supportgowhere.life.gov.sg/schemes/COMCARE-SMTA/comcare-assistance\n"
                "https://supportgowhere.life.gov.sg/schemes/SCFA/student-care-fee-assistance-scfa\n"
#                "https://www.ecda.gov.sg/parents/subsidies-financial-assistance#KIFAS\n"
#                "https://www.ecda.gov.sg/parents/subsidies-financial-assistance#CCICS"
            ),
            height=150,
        )
        urls = [line.strip() for line in url_text.splitlines() if line.strip()]

        uploaded_files = st.file_uploader(
            "📄 Upload Documents", type=["pdf", "txt"], accept_multiple_files=True
        )

        if uploaded_files or urls:
            labels = [f.name for f in uploaded_files] + urls
            st.success("Received: " + ", ".join(labels))
            # Filled in after the sources are processed (further down the sidebar)
            index_status = st.empty()
        elif "vectorstore" in st.session_state:
            st.info("Using the index built earlier this session. Add URLs or files to replace it.")
        else:
            st.info("Add a web page URL or upload a PDF/text file to enable document Q&A.")

        chat_transcript = "\n\n".join(
            f"{m['role'].capitalize()}: {m['content']}"
            for m in st.session_state.messages
        )
        st.download_button(
            "Download Chat",
            data=chat_transcript,
            file_name="chat.txt",
            mime="text/plain",
            disabled=not st.session_state.messages,
        )

        if st.button("Clear Conversation"):
            st.session_state.messages = []
            st.rerun()

    with st.expander("⚙️ System Configuration", expanded=False):
        system_prompt = st.text_area(
            "System Prompt",
            value=(
                "You are an assistant to a social worker who helps clients "
                "navigate through life circumstances and schemes offered by "
                "government and social service agencies in Singapore."
            ),
            height=150,
        )

        chunk_size = st.number_input(
            "Chunk size", min_value=1, value=800, step=50
        )
        chunk_overlap = st.number_input(
            "Chunk overlap", min_value=0, value=100, step=10
        )
        # Invalid chunk settings only block indexing; the chat below still renders.
        settings_valid = chunk_overlap < chunk_size
        if not settings_valid:
            st.error("Chunk overlap must be smaller than chunk size.")
        k_value = st.slider("Chunks to retrieve (k)", min_value=1, max_value=10, value=4)
        temperature = st.slider(
            "Temperature", min_value=0.0, max_value=2.0, step=0.1, value=0.2
        )

    # Incrementally sync the vector store with the current source list. Only
    # sources that are new or changed are embedded; removed ones are deleted.
    # The whole thing is skipped when chunk settings are invalid, but the chat
    # below still renders.
    if (uploaded_files or urls) and settings_valid:
        store = get_vectorstore(st.session_state.session_id)

        # What the user currently wants indexed, keyed by a stable source id.
        # For files the id is the filename and the "signature" is the size, so
        # replacing a file with a same-named but different one is re-indexed.
        # For URLs the id is the URL itself.
        desired = {}
        for f in uploaded_files:
            desired[f.name] = {"kind": "file", "sig": f.size, "arg": f}
        for url in urls:
            desired[url] = {"kind": "url", "sig": url, "arg": url}

        # Per-session record of what is actually embedded: source id -> the
        # chunk ids it produced, plus the chunk settings used.
        state = st.session_state.setdefault(
            "index_state", {"settings": None, "sources": {}}
        )

        # If the store was reset underneath us (e.g. cache eviction) but our
        # record still lists sources, the record is stale — start clean.
        if state["sources"] and _store_is_empty(store):
            state["sources"] = {}
            state["settings"] = None

        # Changing chunk settings invalidates every existing chunk, so drop the
        # whole index and re-add all current sources under the new settings.
        settings = (chunk_size, chunk_overlap)
        if state["settings"] != settings:
            stale_ids = [i for s in state["sources"].values() for i in s["ids"]]
            if stale_ids:
                store.delete(ids=stale_ids)
            state["sources"] = {}
            state["settings"] = settings

        # Remove sources no longer requested, and any whose signature changed
        # (a changed source stays in `desired` and is re-added below).
        to_remove = set(state["sources"]) - set(desired)
        for sid in list(set(state["sources"]) & set(desired)):
            if desired[sid]["sig"] != state["sources"][sid]["sig"]:
                to_remove.add(sid)
        for sid in to_remove:
            ids = state["sources"].pop(sid)["ids"]
            if ids:
                store.delete(ids=ids)

        # Add sources that aren't indexed yet.
        to_add = [sid for sid in desired if sid not in state["sources"]]
        added_sources = 0
        for sid in to_add:
            source = desired[sid]
            try:
                if source["kind"] == "file":
                    chunks = load_and_split(source["arg"], chunk_size, chunk_overlap)
                else:
                    chunks = load_and_split_url(
                        source["arg"], chunk_size, chunk_overlap
                    )
            except Exception as exc:
                traceback.print_exc()
                if source["kind"] == "file":
                    st.warning(f"Could not read: {sid}")
                else:
                    st.warning(f"Could not fetch {sid}\n\n_{exc}_")
                continue

            if not chunks:
                st.warning(f"No readable text found in: {sid}")
                continue

            ids = store.add_documents(chunks)
            state["sources"][sid] = {"sig": source["sig"], "ids": ids}
            added_sources += 1

        # Report the current state of the index. Counts distinguish what was
        # entered, what is actually indexed, and what was dropped, so the
        # numbers never look mismatched to the user.
        raw_total = len(uploaded_files) + len(urls)
        requested = len(desired)              # unique sources after dedup
        duplicates = raw_total - requested    # repeated URLs / filenames
        indexed = len(state["sources"])       # successfully embedded
        skipped = requested - indexed         # failed to fetch/read this run

        if not state["sources"]:
            st.session_state.pop("vectorstore", None)
            index_status.error(
                "No text could be extracted from the provided sources."
            )
        else:
            st.session_state.vectorstore = store
            total_chunks = sum(len(s["ids"]) for s in state["sources"].values())
            msg = (
                f"Ready! Indexed {indexed} of {requested} source(s) "
                f"({total_chunks} chunks)."
            )
            if skipped:
                msg += f" {skipped} skipped — see warnings above."
            if duplicates:
                msg += f" {duplicates} duplicate entry(ies) ignored."
            index_status.success(msg)

# Render past messages in chat bubbles
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

# Handle new user input
if prompt := st.chat_input("Tell me about the client's situation"):
    # Store and display the user's message
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    # Stream the assistant's reply from OpenAI
    with st.chat_message("assistant"):
        source_docs = []
        try:
            with st.spinner("Thinking..."):
                # Base instruction comes from the sidebar; add RAG context if a
                # document is indexed, otherwise use the base prompt as-is.
                if "vectorstore" in st.session_state:
                    context, source_docs = retrieve_context(
                        st.session_state.vectorstore, prompt, k=k_value
                    )
                    active_system_prompt = build_rag_system_prompt(system_prompt, context)
                else:
                    active_system_prompt = system_prompt

                # Only send the most recent turns so token cost and context
                # usage stay bounded on long conversations.
                recent_history = st.session_state.messages[-MAX_HISTORY_MESSAGES:]
                stream = client.chat.completions.create(
                    model=CHAT_MODEL,
                    messages=[{"role": "system", "content": active_system_prompt}]
                    + recent_history,
                    temperature=temperature,
                    stream=True,
                )

            # Spinner is gone here — tokens render live
            reply = st.write_stream(stream)

            # Show the retrieved chunks that informed this answer
            if source_docs:
                with st.expander("🔍 View Sources"):
                    for i, doc in enumerate(source_docs, start=1):
                        source = doc.metadata.get("source")
                        page = doc.metadata.get("page")
                        label = f"**Chunk {i}**"
                        if source:
                            label += f" — {source}"
                        if page is not None:
                            label += f" (page {page + 1})"
                        st.markdown(label)
                        st.text(doc.page_content)
                        if i < len(source_docs):
                            st.divider()
        except Exception as e:
            # Log the full traceback to the terminal for debugging
            traceback.print_exc()
            # Friendly message in the UI (no raw traceback)
            st.error("Sorry, something went wrong while contacting the assistant. Please try again.")
            reply = "⚠️ Sorry, I couldn't generate a response. Please try again."

    # Persist the reply (real or fallback) so history stays intact
    st.session_state.messages.append({"role": "assistant", "content": reply})
