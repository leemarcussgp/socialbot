import streamlit as st

from utility import check_password

# Must be the first Streamlit command and is set once here for the whole app.
st.set_page_config(page_title="Social Bot", page_icon="😊")

# Gate the entire app behind a password. Because every page load runs this
# entry script before navigation, this one check protects all pages.
if not check_password():
    st.stop()

# Multipage navigation. The chatbot is the default landing page.
chatbot_page = st.Page(
    "views/chatbot.py", title="Social Bot", icon="😊", default=True
)
about_page = st.Page("views/about_us.py", title="About Us", icon="ℹ️")
methodology_page = st.Page("views/methodology.py", title="Methodology", icon="🧭")
disclaimer_page = st.Page("views/disclaimer.py", title="Disclaimer", icon="⚠️")

pg = st.navigation(
    [chatbot_page, about_page, methodology_page, disclaimer_page]
)
pg.run()
