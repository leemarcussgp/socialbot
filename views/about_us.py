import streamlit as st

st.title("About Us")

st.markdown(
    """
**Social Bot** is an AI assistant built to support social workers in Singapore
as they help clients navigate life circumstances and the support schemes
offered by government and social service agencies.

### What it does
- Answers questions about financial assistance and support schemes, grounded in
  the web pages and documents you provide.
- Lets you add your own sources — paste web pages or upload PDFs and text
  files — so answers reflect the material relevant to your client.
- Shows the source passages behind each answer, so you can verify before you
  act on anything.

### Who it's for
Front-line social workers, case workers, and social service professionals who
need to quickly cross-reference schemes and eligibility information while
working with clients.

### Important disclaimer
Social Bot is a decision-support aid, **not** a source of official guidance. It
can make mistakes or miss context. Always confirm eligibility, amounts, and
application steps against the official agency sources before advising a client.

### Privacy
Conversations and uploaded documents stay within your own session and are not
shared with other users. Avoid entering information that identifies a specific
client unless your organisation's policies permit it.
"""
)
