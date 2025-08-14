import streamlit as st
import os
import pandas as pd
from app.db.database import SessionLocal, init_db
from app.db import crud
from app.core.config_manager import ConfigManager
from app.core.document_processor import DocumentProcessor
from app.utils.pdf_highlighter import highlight_extractions_on_pdf


# --- App Setup and Configuration ---
st.set_page_config(
    page_title="PDF Data Extractor",
    page_icon="🚀",
    layout="wide"
)
TEMP_DIR, CONFIG_DIR = "temp_uploads", "configs"
if not os.path.exists(TEMP_DIR): os.makedirs(TEMP_DIR)
if not os.path.exists(CONFIG_DIR): os.makedirs(CONFIG_DIR)

# --- Initialization ---
@st.cache_resource
def get_db_session(): return SessionLocal()
@st.cache_resource
def get_config_manager(): return ConfigManager(config_dir=CONFIG_DIR)

init_db()
db = get_db_session()
config_manager = get_config_manager()
if 'processing_log' not in st.session_state: st.session_state.processing_log = []

# --- UI Layout and Logic ---
st.title("🚀 PDF Data Extractor")
st.markdown("An application combining precise **config-based** extraction with a flexible **dynamic heuristic** engine.")

with st.sidebar:
    st.header("1. Select Processing Mode")
    processing_mode = st.radio(
        "Choose your extraction method:",
        ('Precise (Config-Based)', 'Flexible (Dynamic Heuristic)'),
        help="""
        - **Precise:** Uses a YAML config for known forms. Fast and highly accurate.
        - **Flexible:** Uses AI heuristics to process any form, even unknown ones. Slower and may have errors.
        """
    )

    st.header("2. Upload PDF Files")
    uploaded_files = st.file_uploader("Upload one or more PDF files", type="pdf", accept_multiple_files=True)

    st.header("3. Process Documents")
    if st.button("Process Selected Files", type="primary", disabled=not uploaded_files):
        st.session_state.processing_log = [f"Starting {processing_mode} processing..."]
        processor = DocumentProcessor(db, config_manager)
        with st.spinner(f"Processing {len(uploaded_files)} file(s)..."):
            progress_bar = st.progress(0, text="Starting...")
            for i, uploaded_file in enumerate(uploaded_files):
                file_path = os.path.join(TEMP_DIR, uploaded_file.name)
                with open(file_path, "wb") as f: f.write(uploaded_file.getvalue())
                log_message = f"Processing {i + 1}/{len(uploaded_files)}: {uploaded_file.name}"
                st.session_state.processing_log.append(log_message)
                progress_bar.progress((i + 1) / len(uploaded_files), text=log_message)
                processor.process_document(file_path, mode=processing_mode)
        st.success("Processing complete!")
        st.rerun()

    st.header("Database Actions")
    if st.button("Clear All Extracted Data"):
        with st.spinner("Clearing database..."): crud.clear_all_data(db)
        st.success("All data has been cleared.")
        st.rerun()

tab1, tab2 = st.tabs(["📊 View Results", "⚙️ Processing Log"])
with tab1:
    st.header("Extracted Document Data")
    all_documents = crud.get_all_documents(db)
    if not all_documents:
        st.info("No documents have been processed yet. Select a mode, upload files, and click 'Process' in the sidebar.")
    else:
        doc_options = [f"{doc.filename} (ID: {doc.id}, Mode: {doc.processing_method}, Status: {doc.status})" for doc in all_documents]
        selected_doc_str = st.selectbox("Select a processed document:", options=doc_options)
        if selected_doc_str:
            selected_doc_id = int(selected_doc_str.split("ID: ")[1].split(",")[0])
            selected_doc = crud.get_document_by_id(db, selected_doc_id)
            col1, col2 = st.columns([0.6, 0.4])
            with col1:
                st.subheader("Extracted Data")
                if selected_doc.extracted_data:
                    display_data = [item for item in selected_doc.extracted_data if item.value != "Unchecked"]
                    df = pd.DataFrame([{"Key": item.key, "Value": item.value, "Method": item.extraction_method} for item in display_data])
                    st.dataframe(df, use_container_width=True)
                else:
                    st.warning("No data was extracted for this document.")
            with col2:
                st.subheader("Data Location on Document")
                pdf_path = os.path.join(TEMP_DIR, selected_doc.filename)
                if os.path.exists(pdf_path) and selected_doc.extracted_data:
                    with st.spinner("Generating highlighted view..."):
                        highlighted_image_bytes = highlight_extractions_on_pdf(pdf_path, selected_doc.extracted_data)
                        st.image(highlighted_image_bytes, caption="Highlights show where data was found.")

with tab2:
    st.header("Processing Log")
    st.code("\n".join(st.session_state.processing_log), language="plaintext")
