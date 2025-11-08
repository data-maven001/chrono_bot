import os
import json
import bcrypt
import torch
import fitz  # PyMuPDF
import wikipedia
import streamlit as st
from email.message import EmailMessage
import smtplib
from sentence_transformers import SentenceTransformer, util
import requests

# -----------------------------
# Page & Theming
# -----------------------------
st.set_page_config(page_title="ChronoBOT", layout="centered")
try:
    st.image("assets/logo.png", width=250)
except Exception:
    pass

st.title("📚 ChronoBOT: Research Assistant")
theme = st.checkbox("🌗 Dark Mode")
if theme:
    st.markdown("""
        <style>
        body, .stApp { background-color: #121212; color: #FFFFFF; }
        </style>
    """, unsafe_allow_html=True)

# -----------------------------
# Helpers: Config, Users, Auth, Email
# -----------------------------
def load_config():
    default = {
        "admin_user": "admin",
        "admin_pass": "admin123",
        "admin_email": "admin@example.com",
        "smtp_server": "smtp.gmail.com",
        "smtp_port": 587,
        "smtp_user": "azeezsamad070@gmail.com",  # Replace before production
        "smtp_pass": "2207166556"                # Replace before production
    }
    if not os.path.exists("config.json"):
        return default
    try:
        with open("config.json", "r") as f:
            data = json.load(f)
            return {**default, **data}
    except Exception:
        return default

CONFIG = load_config()

def send_email(subject: str, body: str, to_email: str) -> bool:
    try:
        msg = EmailMessage()
        msg["From"] = CONFIG["smtp_user"]
        msg["To"] = to_email
        msg["Subject"] = subject
        msg.set_content(body)

        with smtplib.SMTP(CONFIG["smtp_server"], CONFIG["smtp_port"]) as server:
            server.starttls()
            server.login(CONFIG["smtp_user"], CONFIG["smtp_pass"])
            server.send_message(msg)
        return True
    except Exception as e:
        st.error(f"📧 Email failed: {e}")
        return False

def load_users():
    empty = {"students": {}, "lecturers": {}}
    if not os.path.exists("users.json"):
        return empty
    try:
        with open("users.json", "r") as f:
            return json.load(f)
    except json.JSONDecodeError:
        return empty

def save_users(db: dict):
    with open("users.json", "w") as f:
        json.dump(db, f, indent=4)

def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()

def verify_password(entered_password: str, stored_hash: str) -> bool:
    if not stored_hash:
        return False
    try:
        return bcrypt.checkpw(entered_password.encode(), stored_hash.encode())
    except Exception:
        return False

users_db = load_users()

# -----------------------------
# Save & Load Lecture Files (Shared Storage)
# -----------------------------
def load_lectures():
    if not os.path.exists("lectures.json"):
        return {}
    try:
        with open("lectures.json", "r", encoding="utf-8") as f:
            return json.load(f)
    except json.JSONDecodeError:
        return {}

def save_lectures(db: dict):
    with open("lectures.json", "w", encoding="utf-8") as f:
        json.dump(db, f, indent=4)

lectures_db = load_lectures()

# -----------------------------
# Embed Model (lazy load)
# -----------------------------
@st.cache_resource
def load_model():
    return SentenceTransformer("all-MiniLM-L6-v2")

# -----------------------------
# Ollama availability & query
# -----------------------------
def check_ollama():
    """Return True if Ollama is reachable on default API port."""
    try:
        r = requests.get("http://127.0.0.1:11434/api/tags", timeout=2)
        return r.status_code == 200
    except Exception:
        return False

OLLAMA_AVAILABLE = check_ollama()

def ask_ollama_with_context(query: str, contexts: list, model_name: str = "llama3", timeout: int = 60):
    """
    Send question + contexts to Ollama API. Returns generated text or None on failure.
    Uses the /api/generate endpoint and tries to read streamed lines if present.
    """
    if not OLLAMA_AVAILABLE:
        return None

    prompt = f"""You are ChronoBOT, an academic assistant for students.
Use ONLY the provided context to answer the question. If the context does not answer fully, say: "The provided materials do not fully answer this question."

Question: {query}

Context (relevant excerpts):
{"".join([f"- {c}\\n" for c in contexts])}

Provide a concise, student-friendly explanation. Cite which excerpt you used where possible.
"""
    url = "http://127.0.0.1:11434/api/generate"
    try:
        resp = requests.post(url, json={"model": model_name, "prompt": prompt}, stream=True, timeout=timeout)
        resp.raise_for_status()
        # streamed response: read lines and parse JSON objects
        generated = ""
        for line in resp.iter_lines(decode_unicode=True):
            if not line:
                continue
            try:
                item = json.loads(line)
                # the exact key can vary by Ollama version; common is "response"
                if isinstance(item, dict) and "response" in item:
                    generated += item.get("response", "")
                # if whole text included in top-level "text" or similar (fallback)
                elif isinstance(item, dict) and "text" in item:
                    generated += item.get("text", "")
            except Exception:
                # fallback: append whatever raw text
                generated += line
        return generated.strip() if generated.strip() else None
    except Exception:
        # Last attempt: non-streaming JSON response
        try:
            r2 = requests.post(url, json={"model": model_name, "prompt": prompt}, timeout=timeout)
            if r2.status_code == 200:
                try:
                    j = r2.json()
                    # try to find text in common keys
                    if "response" in j:
                        return j["response"]
                    if "text" in j:
                        return j["text"]
                    return json.dumps(j)[:1000]
                except Exception:
                    return r2.text[:1000]
        except Exception:
            return None

# -----------------------------
# Text extraction & retrieval helpers
# -----------------------------
def create_uploads_dir():
    os.makedirs("uploads", exist_ok=True)

def extract_text_from_pdf(pdf_path):
    doc = fitz.open(pdf_path)
    text = ""
    for page in doc:
        text += page.get_text("text")
    return text

def chunk_text(text, chunk_size=500):
    chunks = []
    text = text.replace("\n", " ").strip()
    for i in range(0, len(text), chunk_size):
        chunk = text[i:i + chunk_size].strip()
        if chunk:
            chunks.append(chunk)
    return chunks

def get_all_chunks_from_storage():
    """Return list of chunks dicts from lectures.json storage (file, page, text, lecturer)."""
    db = load_lectures()
    all_chunks = []
    for fname, chunks in db.items():
        for c in chunks:
            # ensure it has keys text, page, file
            all_chunks.append({
                "text": c.get("text", ""),
                "page": c.get("page", None),
                "file": c.get("file", fname),
                "lecturer": c.get("lecturer", None)
            })
    return all_chunks

def retrieve_top_k(query: str, top_k: int = 3):
    """
    Return top_k text chunks (strings) and metadata for a query using SentenceTransformer similarity.
    """
    model = load_model()
    all_chunks = get_all_chunks_from_storage()
    if not all_chunks:
        return []

    texts = [c["text"] for c in all_chunks]
    # embed
    query_emb = model.encode(query, convert_to_tensor=True)
    embeddings = model.encode(texts, convert_to_tensor=True)
    scores = util.cos_sim(query_emb, embeddings)[0]  # tensor
    top_idxs = torch.topk(scores, k=min(top_k, len(scores))).indices.tolist()

    results = []
    for idx in top_idxs:
        results.append({
            "text": texts[idx],
            "score": float(scores[idx].item()),
            "file": all_chunks[idx]["file"],
            "page": all_chunks[idx].get("page")
        })
    return results

# -----------------------------
# Utility: Wikipedia fallback
# -----------------------------
def search_wikipedia_extract(query):
    """Try a short wikipedia summary."""
    try:
        summary = wikipedia.summary(query, sentences=3)
        page = wikipedia.page(query)
        return summary, f"🌍 Wikipedia – {page.title} ({page.url})"
    except wikipedia.exceptions.DisambiguationError as e:
        # give a short hint
        opts = e.options[:5]
        return f"Disambiguation — possible options: {opts}", None
    except wikipedia.exceptions.PageError:
        return None, None
    except Exception as err:
        return None, None

# -----------------------------
# Session State
# -----------------------------
for key, default in {
    "history": [],
    "is_logged_in": False,
    "role": None,
    "username": None,
    "admin_logged_in": False
}.items():
    if key not in st.session_state:
        st.session_state[key] = default

# -----------------------------
# Sidebar: Role Selection & Admin
# -----------------------------
st.sidebar.title("🔑 User Role")
role_choice = st.sidebar.radio("Select Role:", ["🎓 Student", "👨‍🏫 Lecturer"])

st.sidebar.markdown("---")
st.sidebar.subheader("👑 Admin Panel")
if not st.session_state.admin_logged_in:
    admin_user_in = st.sidebar.text_input("Admin Username", key="admin_user_in")
    admin_pass_in = st.sidebar.text_input("Admin Password", type="password", key="admin_pass_in")
    if st.sidebar.button("Login as Admin"):
        if admin_user_in == CONFIG["admin_user"] and admin_pass_in == CONFIG["admin_pass"]:
            st.session_state.admin_logged_in = True
            st.sidebar.success("✅ Admin logged in")
        else:
            st.sidebar.error("❌ Invalid admin credentials")
else:
    if st.sidebar.button("Logout Admin"):
        st.session_state.admin_logged_in = False
        st.sidebar.info("👋 Admin logged out")

if st.session_state.admin_logged_in:
    st.subheader("👨‍🏫 Pending Lecturer Approvals")
    pending = {u: d for u, d in users_db.get("lecturers", {}).items() if not d.get("approved", False)}
    if not pending:
        st.info("No pending lecturers 🎉")
    else:
        for lect_name, data in pending.items():
            col1, col2, col3 = st.columns([3, 2, 2])
            with col1:
                st.write(f"🔸 **{lect_name}** — {data.get('email','(no email)')}")
            with col2:
                if st.button(f"Approve {lect_name}", key=f"approve_{lect_name}"):
                    users_db["lecturers"][lect_name]["approved"] = True
                    save_users(users_db)
                    st.success(f"✅ {lect_name} approved!")
            with col3:
                if st.button(f"Reject {lect_name}", key=f"reject_{lect_name}"):
                    users_db["lecturers"].pop(lect_name, None)
                    save_users(users_db)
                    st.warning(f"🗑️ {lect_name} rejected and removed")

# -----------------------------
# Main Page Authentication
# -----------------------------
st.subheader(f"{role_choice} Authentication")
auth_tabs = st.tabs(["🔐 Login", "📝 Sign Up"])

with auth_tabs[0]:
    st.markdown(f"### {role_choice} Login")
    login_username = st.text_input("Username", key="login_user")
    login_password = st.text_input("Password", type="password", key="login_pass")

    if st.button("Login", key="btn_login"):
        if role_choice == "🎓 Student":
            student = users_db.get("students", {}).get(login_username)
            if student and verify_password(login_password, student.get("password", "")):
                st.session_state.is_logged_in = True
                st.session_state.role = "student"
                st.session_state.username = login_username
                st.success(f"✅ Welcome {st.session_state.username} (Student)!")
            else:
                st.error("❌ Invalid username or password")

        elif role_choice == "👨‍🏫 Lecturer":
            lect = users_db.get("lecturers", {}).get(login_username)
            if not lect:
                st.error("❌ Invalid username or password")
            else:
                if not lect.get("approved", False):
                    st.warning("⚠️ Account awaiting admin approval.")
                elif verify_password(login_password, lect.get("password", "")):
                    st.session_state.is_logged_in = True
                    st.session_state.role = "lecturer"
                    st.session_state.username = login_username
                    st.success(f"✅ Welcome {st.session_state.username} (Lecturer)!")
                else:
                    st.error("❌ Invalid username or password")

with auth_tabs[1]:
    st.markdown(f"### {role_choice} Sign Up")
    new_username = st.text_input("Choose a Username", key="reg_user")
    new_password = st.text_input("Choose a Password", type="password", key="reg_pass")
    confirm_password = st.text_input("Confirm Password", type="password", key="reg_pass2")
    new_email = None
    if role_choice == "👨‍🏫 Lecturer":
        new_email = st.text_input("Email Address", key="reg_email")

    if st.button("Create Account", key="btn_create"):
        if not new_username or not new_password:
            st.error("❌ Username and password are required.")
        elif new_password != confirm_password:
            st.error("❌ Passwords do not match.")
        elif len(new_username.strip()) < 3 or len(new_password) < 4:
            st.error("❌ Username must be ≥3 chars and password ≥4 chars.")
        elif role_choice == "👨‍🏫 Lecturer" and (not new_email or "@" not in new_email):
            st.error("❌ Valid email is required for lecturer signup.")
        else:
            if role_choice == "🎓 Student":
                if new_username in users_db.get("students", {}):
                    st.error("❌ Student username already exists.")
                else:
                    users_db.setdefault("students", {})[new_username] = {
                        "password": hash_password(new_password),
                    }
                    save_users(users_db)
                    st.success("✅ Account created! You can now log in.")
            else:
                if new_username in users_db.get("lecturers", {}):
                    st.error("❌ Lecturer username already exists.")
                else:
                    users_db.setdefault("lecturers", {})[new_username] = {
                        "password": hash_password(new_password),
                        "email": new_email,
                        "approved": False
                    }
                    save_users(users_db)
                    st.info("⏳ Account created! Waiting for admin approval.")
                    send_email(
                        "New Lecturer Registration Pending Approval",
                        f"A new lecturer '{new_username}' has registered.\nEmail: {new_email}",
                        CONFIG["admin_email"]
                    )

# -----------------------------
# Logout
# -----------------------------
if st.session_state.is_logged_in:
    st.sidebar.success(f"👤 Logged in as {st.session_state.username} ({st.session_state.role})")
    if st.sidebar.button("Logout"):
        st.session_state.is_logged_in = False
        st.session_state.role = None
        st.session_state.username = None
        st.sidebar.info("👋 Logged out successfully.")

# -----------------------------
# Lecturer Upload Section
# -----------------------------
if st.session_state.is_logged_in and st.session_state.role == "lecturer":
    lecturer_name = st.session_state.get("username", "UnknownLecturer")
    st.subheader(f"📂 Upload Lecture PDFs (Lecturer: {lecturer_name})")

    doc_title = st.text_input("Enter the course title (e.g., Introduction to Data Science)")
    uploaded_file = st.file_uploader("Upload a PDF", type=["pdf"])

    if uploaded_file and doc_title:
        create_uploads_dir()
        file_extension = os.path.splitext(uploaded_file.name)[1]
        new_filename = f"{doc_title} ({lecturer_name}){file_extension}"
        save_path = os.path.join("uploads", new_filename)

        # Save uploaded PDF
        with open(save_path, "wb") as f:
            f.write(uploaded_file.getbuffer())

        # Extract text and chunk
        try:
            doc = fitz.open(save_path)
            text_chunks = []
            for page_num, page in enumerate(doc):
                text = page.get_text("text") or ""
                if text.strip():
                    # chunk per page text
                    page_chunks = chunk_text(text, chunk_size=500)
                    for chunk in page_chunks:
                        text_chunks.append({
                            "text": chunk,
                            "page": page_num + 1,
                            "file": new_filename,
                            "lecturer": lecturer_name
                        })

            # Save to shared JSON
            lectures_db = load_lectures()
            lectures_db[new_filename] = text_chunks
            save_lectures(lectures_db)

            st.success(f"✅ {new_filename} uploaded successfully and saved!")
        except Exception as e:
            st.error(f"Failed to read PDF: {e}")

# -----------------------------
# Student Question Section (Hybrid: Lectures -> Ollama -> Wikipedia)
# -----------------------------
if st.session_state.is_logged_in and st.session_state.role == "student":
    st.subheader("🎓 Ask a Question")
    user_input = st.text_input("Type your question and press Enter:")

    if user_input:
        st.info("🔎 Retrieving relevant lecture excerpts...")
        top_chunks = retrieve_top_k(user_input, top_k=3)  # top 3 chunks
        final_answer = None
        source_info = None

        if top_chunks:
            # Prepare small context list (texts)
            contexts = [c["text"] for c in top_chunks]
            # Show retrieved excerpts for transparency
            st.subheader("📄 Retrieved excerpts (from uploaded lectures):")
            for c in top_chunks:
                st.markdown(f"- {c['text'][:300]}...  _(score: {c['score']:.3f})_\n  **{c['file']}** (Page {c['page']})")

            # If Ollama is available, ask it to explain using these contexts
            if OLLAMA_AVAILABLE:
                st.info("🤖 Sending to Ollama for a student-friendly explanation...")
                ollama_response = ask_ollama_with_context(user_input, contexts)
                if ollama_response:
                    final_answer = ollama_response
                    source_info = "Answer generated by Ollama using uploaded lecture excerpts."
                else:
                    # fallback: use concatenated excerpt
                    final_answer = "\n\n".join(contexts)
                    source_info = "Returned raw excerpts (Ollama failed to generate)."
            else:
                # Ollama not reachable, show best excerpt as answer
                final_answer = top_chunks[0]["text"]
                source_info = f"⚠️ Ollama unavailable — answer is extracted from {top_chunks[0]['file']} (Page {top_chunks[0]['page']})."

        else:
            # No lecture excerpts found: try Ollama (without lecture context) OR Wikipedia
            if OLLAMA_AVAILABLE:
                st.info("📡 No lecture excerpts found — asking Ollama (general knowledge)...")
                ollama_response = ask_ollama_with_context(user_input, contexts=[])
                if ollama_response:
                    final_answer = ollama_response
                    source_info = "Answer generated by Ollama (no lecture context)."
                else:
                    # Fallback to Wikipedia
                    wiki_text, wiki_ref = search_wikipedia_extract(user_input)
                    if wiki_text:
                        final_answer = wiki_text
                        source_info = wiki_ref
                    else:
                        final_answer = "❌ Sorry — no helpful content found."
                        source_info = None
            else:
                st.info("📚 Searching Wikipedia as Ollama is unavailable...")
                wiki_text, wiki_ref = search_wikipedia_extract(user_input)
                if wiki_text:
                    final_answer = wiki_text
                    source_info = wiki_ref
                else:
                    final_answer = "❌ Sorry — no helpful content found."
                    source_info = None

        # Display final answer
        st.subheader("📝 Final Answer")
        st.write(final_answer)
        if source_info:
            st.caption(source_info)

        # Save history per user
        history_file = os.path.join("user_history", f"{st.session_state.username}_history.json")
        os.makedirs("user_history", exist_ok=True)
        history = []
        if os.path.exists(history_file):
            with open(history_file, "r") as f:
                history = json.load(f)
        history.append({"query": user_input, "answer": final_answer, "source": source_info})
        with open(history_file, "w") as f:
            json.dump(history, f, indent=2)
        st.session_state.history.append(user_input)

# -----------------------------
# Sidebar: History
# -----------------------------
if st.session_state.history:
    st.sidebar.header("📌 Your Search History")
    for item in st.session_state.history[::-1][:5]:
        st.sidebar.write(f"🔸 {item}")
