import hmac

import streamlit as st


def check_password():
    """Return True once the user has entered the correct password.

    The expected password is read from ``st.secrets["password"]``. A correct
    entry is remembered for the rest of the browser session via session state,
    and the typed value is removed from memory immediately after it is checked.
    """

    # A password must be configured in st.secrets (locally in
    # .streamlit/secrets.toml, or in the Streamlit Cloud Secrets panel).
    if "password" not in st.secrets:
        st.error(
            "No app password is configured. Set a `password` entry in the "
            "app's secrets to enable login."
        )
        return False

    def password_entered():
        # Constant-time comparison avoids leaking the password via timing.
        if hmac.compare_digest(
            st.session_state["password"], st.secrets["password"]
        ):
            st.session_state["password_correct"] = True
            # Don't keep the plaintext password around in session state.
            del st.session_state["password"]
        else:
            st.session_state["password_correct"] = False

    # Already authenticated earlier this session.
    if st.session_state.get("password_correct", False):
        return True

    # Prompt for the password.
    st.text_input(
        "Password",
        type="password",
        on_change=password_entered,
        key="password",
    )
    if "password_correct" in st.session_state:
        st.error("😕 Password incorrect")
    return False
