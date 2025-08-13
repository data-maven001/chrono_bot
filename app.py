import streamlit as st
import wikipedia

# --- Page Config ---
st.set_page_config(page_title="ChronoBOT", layout="centered")

# --- Logo ---
st.image("assests/logo.png", width=250)  # Make sure logo is in 'assets' folder

# --- Title & Theme ---
st.title(" ChronoBOT: Ask Me About History & Famous People")
theme = st.toggle("🌗 Dark Mode")

# --- Styling for Dark Mode ---
if theme:
    st.markdown("""
        <style>
        body, .stApp {
            background-color: #121212;
            color: #FFFFFF;
        }
        </style>
    """, unsafe_allow_html=True)

# --- User Input ---
user_input = st.text_input("Ask me about any historical topic or famous person:")

# --- Session State for History ---
if "history" not in st.session_state:
    st.session_state.history = []

# --- Wikipedia Search ---
if user_input:
    with st.spinner("Fetching information..."):
        try:
            summary = wikipedia.summary(user_input, sentences=3)
            page = wikipedia.page(user_input)
            image_url = page.images[0] if page.images else None
            related_topics = wikipedia.search(user_input)

            # Display Results
            st.success("Here's a quick summary:")
            with st.expander("🔍 Summary"):
                st.write(summary)

            # Display Image
            if image_url:
                st.image(image_url, caption=f"{page.title}", use_column_width=True)

            # Related Suggestions
            st.subheader("🔗 Related Topics:")
            st.write(related_topics[:5])

            # Save to History
            st.session_state.history.append(user_input)

        except wikipedia.exceptions.DisambiguationError as e:
            st.warning(f"Too many matches found. Be more specific. Options include: {e.options[:5]}")
        except wikipedia.exceptions.PageError:
            st.error("No page found on that topic.")
        except Exception as err:
            st.error(f"Error: {err}")

# --- History Section ---
if st.session_state.history:
    st.sidebar.header("📌 Your Search History")
    for item in st.session_state.history[::-1][:5]:
        st.sidebar.write(f"🔸 {item}")
