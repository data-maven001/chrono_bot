import streamlit as st
import wikipedia

# --- Page Config ---
st.set_page_config(page_title="HistoryBot", layout="centered")

# --- Logo ---
st.image("assests/logo.png", width=100)

# --- Title & Theme Toggle ---
st.title("📜 HistoryBot: Ask Me About History & Famous People")
dark_mode = st.toggle("🌗 Dark Mode")

# --- Custom Dark Mode Styling ---
if dark_mode:
    st.markdown("""
        <style>
        .stApp {
            background-color: #121212;
            color: white;
        }
        div.stTextInput > label, .stTextInput, .stTextInput input,
        .stSidebar, .stSidebar > div, .stSidebar .css-1d391kg {
            background-color: #1E1E1E !important;
            color: white !important;
        }
        </style>
    """, unsafe_allow_html=True)

# --- User Input ---
user_input = st.text_input("Ask me about any historical topic or famous person:")

# --- Session State for History ---
if "history" not in st.session_state:
    st.session_state.history = []

# --- Wikipedia Query Logic ---
def get_summary_data(query):
    summary = wikipedia.summary(query, sentences=3)
    page = wikipedia.page(query)
    
    # Filter out irrelevant images (e.g. SVGs, logos)
    image_url = next((img for img in page.images if img.lower().endswith(('.jpg', '.jpeg', '.png'))), None)
    related = wikipedia.search(query)
    
    return summary, page.title, image_url, related

# --- Main Logic ---
if user_input:
    with st.spinner("Fetching information..."):
        try:
            summary, title, image_url, related = get_summary_data(user_input)
            
            st.success(f"Here’s what I found about {title}:")
            with st.expander("🔍 Summary"):
                st.write(summary)

            if image_url:
                st.image(image_url, caption=title, use_column_width=True)

            st.subheader("🔗 Related Topics:")
            st.write(related[:5])

            st.session_state.history.append(user_input)

        except wikipedia.exceptions.DisambiguationError as e:
            st.warning(f"Too many matches found. Try being more specific. Example topics: {e.options[:5]}")
        except wikipedia.exceptions.PageError:
            st.error("Topic not found. Try another one.")
        except Exception as err:
            st.error(f"Error: {err}")

# --- History Sidebar ---
if st.session_state.history:
    st.sidebar.header("📌 Your Search History")
    for past_query in reversed(st.session_state.history[-5:]):
        if st.sidebar.button(f"🔸 {past_query}"):
            st.experimental_rerun()
