import os
import json
import bcrypt
import torch
import fitz  # PyMuPDF
import wikipedia
import streamlit as st
from email.message import EmailMessage
import smtplib
from sentence_transformers import SentenceTransformer

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
        "smtp_user": "azeezsamad070@gmail.com",  # Use an app password in production
        "smtp_pass": "2207166556"
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
# Sidebar: Role Selection
# -----------------------------
st.sidebar.title("🔑 User Role")
role_choice = st.sidebar.radio("Select Role:", ["🎓 Student", "👨‍🏫 Lecturer"])

# -----------------------------
# Sidebar: Admin Panel
# -----------------------------
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

# Approvals
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
        os.makedirs("uploads", exist_ok=True)
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
                    for i in range(0, len(text), 500):
                        text_chunks.append({
                            "text": text[i:i+500],
                            "page": page_num + 1,
                            "file": new_filename,
                            "lecturer": lecturer_name
                        })

            # ✅ Save to shared JSON (instead of session only)
            lectures_db = load_lectures()
            lectures_db[new_filename] = text_chunks
            save_lectures(lectures_db)

            st.success(f"✅ {new_filename} uploaded successfully and saved!")
        except Exception as e:
            st.error(f"Failed to read PDF: {e}")

# -----------------------------
# Student Question Section
# -----------------------------
if st.session_state.is_logged_in and st.session_state.role == "student":
    st.subheader("🎓 Ask a Question")
    user_input = st.text_input("Ask me about any historical topic or famous person:")

    if user_input:
        best_answer, source_ref = None, None
        model = load_model()

        # ✅ Load from saved lectures
        lectures_db = load_lectures()
        all_chunks = [c for file_chunks in lectures_db.values() for c in file_chunks]

        if all_chunks:
            texts = [c["text"] for c in all_chunks]
            embeddings = model.encode(texts, convert_to_tensor=True)
            query_embedding = model.encode(user_input, convert_to_tensor=True)

            scores = torch.nn.functional.cosine_similarity(
                query_embedding.unsqueeze(0), embeddings, dim=1
            )
            best_idx = int(torch.argmax(scores))
            best_chunk = all_chunks[best_idx]
            best_answer = best_chunk["text"]
            source_ref = f"📖 Source: {best_chunk['file']} (Page {best_chunk['page']})"

        # Fallback to Wikipedia
        if not best_answer:
            try:
                summary = wikipedia.summary(user_input, sentences=3)
                page = wikipedia.page(user_input)
                best_answer = summary
                source_ref = f"🌍 Source: Wikipedia – [{page.title}]({page.url})"
            except wikipedia.exceptions.DisambiguationError as e:
                st.warning(f"Too many matches. Options: {e.options[:5]}")
            except wikipedia.exceptions.PageError:
                st.error("No page found.")
            except Exception as err:
                st.error(f"Error: {err}")

        if best_answer:
            st.success("Here's what I found:")
            st.write(best_answer)
            if source_ref:
                st.caption(source_ref)
            st.session_state.history.append(user_input)

# -----------------------------
# Sidebar: History
# -----------------------------
if st.session_state.history:
    st.sidebar.header("📌 Your Search History")
    for item in st.session_state.history[::-1][:5]:
        st.sidebar.write(f"🔸 {item}")
