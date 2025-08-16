import streamlit as st
import torch, wikipedia, os, pickle
import fitz  # PyMuPDF
from io import BytesIO
from PIL import Image
from sentence_transformers import SentenceTransformer, util
from transformers import pipeline

# --- Models ---
@st.cache_resource
def load_model():
    return SentenceTransformer("all-MiniLM-L6-v2")
model = load_model()

@st.cache_resource
def load_summarizer():
    return pipeline("summarization", model="facebook/bart-large-cnn")
summarizer = load_summarizer()

# --- Helper: Render PDF page ---
def render_pdf_page(file_path, page_number):
    try:
        doc = fitz.open(file_path)
        page = doc.load_page(page_number - 1)  # 0-indexed
        pix = page.get_pixmap(matrix=fitz.Matrix(2, 2))  # zoom factor
        img = Image.open(BytesIO(pix.tobytes("png")))
        return img
    except Exception as e:
        return None

# --- Student Question Box ---
user_input = st.text_input("Ask me anything:")

if user_input and selected_data:
    with st.spinner("Fetching answers..."):
        # Embed query
        query_embedding = model.encode(user_input, convert_to_tensor=True)
        scores = util.pytorch_cos_sim(query_embedding, selected_embeddings)[0]

        # Pick top 3 chunks
        top_k = min(3, len(scores))
        best_indices = torch.topk(scores, k=top_k).indices.tolist()

        detailed_refs = []

        for idx in best_indices:
            best_chunk = selected_data[idx]

            # Summarize chunk
            summary_pdf = summarizer(
                best_chunk["text"],
                max_length=80, min_length=30, do_sample=False
            )[0]['summary_text']

            # Store metadata
            detailed_refs.append({
                "summary": summary_pdf,
                "lecturer": best_chunk["lecturer"],
                "file": best_chunk["file"],
                "page": best_chunk["page"]
            })

        # Wikipedia backup
        try:
            summary_wiki = wikipedia.summary(user_input, sentences=3)
        except:
            summary_wiki = "No Wikipedia entry found."

        # --- Show Each Reference Separately ---
        st.subheader("📖 Answers from Uploaded PDFs")

        for ref in detailed_refs:
            with st.expander(
                f"📖 {ref['lecturer']} / {ref['file']} / Page {ref['page']}"
            ):
                st.write(ref["summary"])
                st.caption(f"Reference: {ref['file']} (Lecturer: {ref['lecturer']}, Page {ref['page']})")

                # Show the actual PDF page
                pdf_path = f"uploads/{ref['lecturer']}/{ref['file']}"  # fixed path
                pdf_img = render_pdf_page(pdf_path, ref["page"])
                if pdf_img:
                    st.image(pdf_img, caption=f"📄 Page {ref['page']} Preview", use_column_width=True)

                    # Optional download button
                    buf = BytesIO()
                    pdf_img.save(buf, format="PNG")
                    st.download_button(
                        "⬇️ Download This Page",
                        data=buf.getvalue(),
                        file_name=f"{ref['file']}_page{ref['page']}.png",
                        mime="image/png"
                    )
                else:
                    st.warning("⚠️ Could not render this PDF page.")

        # Wikipedia reference at the bottom
        st.subheader("🌍 Wikipedia Reference")
        st.write(summary_wiki)