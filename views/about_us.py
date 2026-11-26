import streamlit as st

st.title("About Us")

st.markdown(
    """
**Social Bot** is an AI-powered assistant that helps social workers in Singapore
navigate the complex landscape of government and social-service support schemes.
It lets a user assemble a knowledge base from trusted web pages and documents,
then ask natural-language questions and receive answers grounded in — and cited
back to — that material.

---

## Project Scope

Social Bot is a **prototype** built for educational purposes.

- **In scope** — answering questions about financial assistance and support
  schemes, using only the sources the user provides (public scheme web pages
  and uploaded documents); showing the exact passages behind each answer; and
  giving the user control over how sources are processed and retrieved.
- **Out of scope** — official eligibility determination, case management,
  storing client records, submitting applications, or acting as a substitute
  for professional judgement or official agency advice. The bot does not draw
  on any knowledge beyond the sources supplied to it.

The application is a single-page chat tool with supporting pages, intended for
one user per session.

## Objectives

1. **Reduce lookup time** — let front-line workers find scheme and eligibility
   information in seconds instead of searching multiple agency websites.
2. **Keep answers grounded** — constrain the language model to the supplied
   sources and have it say so plainly when an answer isn't in them, reducing
   fabrication.
3. **Preserve trust through transparency** — surface the source passages behind
   every answer so the user can verify before acting.
4. **Adapt to each case** — allow users to bring their own web pages and
   documents so the assistant reflects the material relevant to their client.
5. **Protect sensitive context** — isolate each session's data and gate access
   behind a password.

## Data Sources

Social Bot answers **only** from sources the user supplies. There are two kinds:

- **Web pages** — one or more URLs entered in the sidebar. Pages are fetched
  live at indexing time. The default suggestions point to official Singapore
  government resources, for example:
    - Ministry of Social and Family Development (MSF) — ComCare
    - Ministry of Finance (MOF) — individual support schemes
    - Ministry of Education (MOE) — financial assistance
    - SupportGoWhere
- **Uploaded documents** — PDF and plain-text files uploaded directly, useful
  for scheme brochures, internal guides, or any material not available at a
  stable public URL.

Sources can be mixed freely and are combined into a single searchable index.
The model is **not** given any external knowledge beyond these sources.

## Features

- **Multi-source retrieval (RAG)** — combines web pages and documents into one
  index and retrieves the most relevant passages for each question.
- **Client context** — an optional field describing the client's situation in
  general terms; when provided, it is woven into every answer so responses are
  tailored to the case without the user re-typing the background each time.
- **Quick-action buttons** — one-click shortcuts for frequently used
  instructions (e.g. eligible schemes, documents needed), alongside free-form
  typing.
- **Live web fetching with JavaScript support** — fetches pages directly, and
  automatically falls back to a rendering service for JavaScript-heavy sites
  that a plain fetch cannot read.
- **Document upload** — supports multiple PDF and text files at once.
- **Source citations** — every answer includes an expandable view of the exact
  chunks (with document name and page, where available) that informed it.
- **Grounded answers** — the assistant is instructed to use only the retrieved
  context and to state clearly when the answer isn't present.
- **Incremental indexing** — adding or removing a source updates only what
  changed instead of rebuilding the whole index.
- **Adjustable settings** — editable system prompt, chunk size and overlap,
  number of passages retrieved (k), and model temperature.
- **Conversation tools** — download the chat transcript and clear the
  conversation at any time.
- **Access control & isolation** — the app is password-protected, and each
  session's sources and conversation are kept separate from other users'.

---

### Who it's for
Front-line social workers, case workers, and social-service professionals who
need to quickly cross-reference schemes and eligibility information while
working with clients.

### Privacy
Conversations and uploaded documents stay within your own session and are not
shared with other users. Avoid entering information that identifies a specific
client unless your organisation's policies permit it.
"""
)
