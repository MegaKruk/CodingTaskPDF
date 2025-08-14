import streamlit as st
import os
import pandas as pd
from app.db.database import SessionLocal, init_db
from app.db import crud
from app.core.document_processor import DocumentProcessor
from app.utils.pdf_highlighter import highlight_extractions_on_pdf

# --- App Setup and Configuration ---
st.set_page_config(
    page_title="Dynamic PDF Data Extractor",
    page_icon="🚀",
    layout="wide"
)

# --- Constants ---
# We create a temporary directory to store uploaded files for the session.
TEMP_DIR = "temp_uploads"
if not os.path.exists(TEMP_DIR):
    os.makedirs(TEMP_DIR)


# --- Initialization ---
@st.cache_resource
def get_db_session():
    """Creates and returns a database session."""
    return SessionLocal()


# Initialize database
init_db()
db = get_db_session()

# --- App State Management ---
if 'processing_log' not in st.session_state:
    st.session_state.processing_log = []

# --- UI Layout and Logic ---
st.title("🚀 Dynamic PDF Data Extractor")
st.markdown("An intelligent, template-free application to extract data from any PDF form.")

# --- Sidebar for Navigation/Actions ---
with st.sidebar:
    st.header("Actions")

    # NEW: File uploader for user to select files.
    uploaded_files = st.file_uploader(
        "Upload PDF Files for Processing",
        type="pdf",
        accept_multiple_files=True
    )

    # NEW: Button to process only the selected files.
    # The button is disabled if no files are uploaded.
    if st.button("Process Selected Files", type="primary", disabled=not uploaded_files):
        st.session_state.processing_log = ["Starting dynamic processing..."]
        processor = DocumentProcessor(db)

        with st.spinner(f"Processing {len(uploaded_files)} file(s)..."):
            progress_bar = st.progress(0, text="Starting...")

            for i, uploaded_file in enumerate(uploaded_files):
                # Save the uploaded file to the temporary directory
                file_path = os.path.join(TEMP_DIR, uploaded_file.name)
                with open(file_path, "wb") as f:
                    f.write(uploaded_file.getvalue())

                log_message = f"Processing {i + 1}/{len(uploaded_files)}: {uploaded_file.name}"
                st.session_state.processing_log.append(log_message)
                progress_bar.progress((i + 1) / len(uploaded_files), text=log_message)

                # The processor works with the saved file path
                processor.process_document(file_path)

        st.success("Processing complete!")
        st.info("Results are now available in the 'View Results' tab.")

    if st.button("Clear All Extracted Data"):
        with st.spinner("Clearing database..."):
            crud.clear_all_data(db)
        st.success("All data has been cleared.")

    st.markdown("---")
    st.header("About")
    st.markdown(
        "This tool uses a dynamic, multi-strategy approach to extract data, "
        "eliminating the need for manual configuration for each form type."
    )

# --- Main Content Area with Tabs ---
tab1, tab2 = st.tabs(["📊 View Results", "⚙️ Processing Log"])

with tab1:
    st.header("Extracted Document Data")
    all_documents = crud.get_all_documents(db)

    if not all_documents:
        st.info("No documents have been processed yet. Upload files and click 'Process' in the sidebar.")
    else:
        doc_options = [f"{doc.filename} (ID: {doc.id}, Status: {doc.status})" for doc in all_documents]
        selected_doc_str = st.selectbox("Select a processed document:", options=doc_options)

        if selected_doc_str:
            selected_doc_id = int(selected_doc_str.split("ID: ")[1].split(",")[0])
            selected_doc = crud.get_document_by_id(db, selected_doc_id)

            col1, col2 = st.columns([0.6, 0.4])

            with col1:
                st.subheader("Extracted Data")

                if selected_doc.extracted_data:
                    df = pd.DataFrame([{
                        "Key": item.key,
                        "Value": item.value,
                        "Method": item.extraction_method
                    } for item in selected_doc.extracted_data])
                    st.dataframe(df, use_container_width=True)
                else:
                    st.warning("No data was extracted for this document.")

            with col2:
                st.subheader("Data Location on Document")
                # The path now points to our temporary uploads folder
                pdf_path = os.path.join(TEMP_DIR, selected_doc.filename)

                if os.path.exists(pdf_path) and selected_doc.extracted_data:
                    with st.spinner("Generating highlighted view..."):
                        # We can read the file from the temp path for highlighting
                        with open(pdf_path, "rb") as f:
                            pdf_bytes = f.read()

                        highlighted_image_bytes = highlight_extractions_on_pdf(
                            pdf_path, selected_doc.extracted_data
                        )
                        st.image(highlighted_image_bytes, caption="Colored boxes show where data was found.")
                        st.markdown(
                            """
                            **Highlight Legend:**
                            - <span style="color:blue; font-weight:bold;">Blue:</span> From interactive form fields (Widgets).
                            - <span style="color:green; font-weight:bold;">Green:</span> From detected tables.
                            - <span style="color:yellow; background-color:grey; font-weight:bold;">Yellow:</span> From text-based heuristics (Label: Value).
                            """, unsafe_allow_html=True
                        )
                else:
                    st.warning(
                        f"Cannot display image. PDF '{selected_doc.filename}' not found in temp folder or no data to highlight.")

with tab2:
    st.header("Processing Log")
    if st.session_state.processing_log:
        log_text = "\n".join(st.session_state.processing_log)
        st.code(log_text, language="plaintext")
    else:
        st.info("No processing has been initiated in this session.")
