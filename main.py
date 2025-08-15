import streamlit as st
import os
import pandas as pd
from app.db.database import SessionLocal, init_db
from app.db import crud
from app.core.config_manager import ConfigManager
from app.core.document_processor import DocumentProcessor
from app.utils.utils import highlight_extractions_on_pdf

# App Configuration
st.set_page_config(
    page_title="PDF Data Extractor Pro 3000",
    page_icon="🚀",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Directory setup
TEMP_DIR = "temp_uploads"
CONFIG_DIR = "configs"
os.makedirs(TEMP_DIR, exist_ok=True)
os.makedirs(CONFIG_DIR, exist_ok=True)

# Custom CSS for better UI
st.markdown("""
    <style>
    .main-header {
        font-size: 2.5rem;
        color: #1f77b4;
        text-align: center;
        margin-bottom: 2rem;
    }
    .metric-card {
        background-color: #f0f2f6;
        padding: 1rem;
        border-radius: 0.5rem;
        margin-bottom: 1rem;
    }
    .success-message {
        color: #28a745;
        font-weight: bold;
    }
    .warning-message {
        color: #ffc107;
        font-weight: bold;
    }
    .error-message {
        color: #dc3545;
        font-weight: bold;
    }
    </style>
""", unsafe_allow_html=True)


# Initialize resources
@st.cache_resource
def get_db_session():
    """Get database session."""
    return SessionLocal()


@st.cache_resource
def get_config_manager():
    """Get configuration manager."""
    return ConfigManager(config_dir=CONFIG_DIR)


# Initialize database and managers
init_db()
db = get_db_session()
config_manager = get_config_manager()

# Session state initialization
if 'processing_log' not in st.session_state:
    st.session_state.processing_log = []
if 'last_processed' not in st.session_state:
    st.session_state.last_processed = []

# Header
st.markdown('<h1 class="main-header">🚀 PDF Data Extractor Pro 3000</h1>', unsafe_allow_html=True)
st.markdown("**Advanced document processing with intelligent data extraction**")
st.markdown("---")

# Sidebar
with st.sidebar:
    st.header("⚙️ Extraction Settings")

    # Mode selection
    processing_mode = st.radio(
        "Select Extraction Mode",
        options=['Precise (Config-Based)', 'Flexible (Dynamic Heuristic)'],
        help="""
        **Precise Mode:** Uses YAML configurations for known form types. 
        Fast and highly accurate for configured forms.

        **Flexible Mode:** Uses AI-powered heuristics to extract from any form. 
        Works with unknown forms but may require validation.
        """
    )

    # Display mode info
    if processing_mode == 'Precise (Config-Based)':
        st.info(f"📋 **{len(config_manager.configs)} form types configured**")
        if config_manager.configs:
            st.caption("Configured forms:")
            for form_type in config_manager.configs.keys():
                st.caption(f"• {form_type}")
    else:
        st.info("🤖 **AI-powered extraction active**")

    st.markdown("---")

    # File upload
    st.header("📁 Upload Documents")
    uploaded_files = st.file_uploader(
        "Select PDF files",
        type="pdf",
        accept_multiple_files=True,
        help="Upload one or more PDF forms for processing"
    )

    if uploaded_files:
        st.success(f"✅ {len(uploaded_files)} file(s) ready")
        for file in uploaded_files:
            st.caption(f"• {file.name}")

    st.markdown("---")

    # Process button
    st.header("🚀 Process Documents")

    col1, col2 = st.columns(2)
    with col1:
        process_btn = st.button(
            "Process Files",
            type="primary",
            disabled=not uploaded_files,
            use_container_width=True
        )
    with col2:
        clear_btn = st.button(
            "Clear Database",
            type="secondary",
            use_container_width=True
        )

    if clear_btn:
        with st.spinner("Clearing database..."):
            crud.clear_all_data(db)
            st.session_state.processing_log = []
            st.session_state.last_processed = []
        st.success("✅ Database cleared")
        st.rerun()

    if process_btn:
        st.session_state.processing_log = []
        st.session_state.last_processed = []
        processor = DocumentProcessor(db, config_manager)

        progress_bar = st.progress(0)
        status_text = st.empty()

        for i, uploaded_file in enumerate(uploaded_files):
            # Save file
            file_path = os.path.join(TEMP_DIR, uploaded_file.name)
            with open(file_path, "wb") as f:
                f.write(uploaded_file.getvalue())

            # Update progress
            progress = (i + 1) / len(uploaded_files)
            progress_bar.progress(progress)
            status_text.text(f"Processing {uploaded_file.name}...")

            # Process document
            processor.process_document(file_path, mode=processing_mode)

            # Log processing
            st.session_state.processing_log.append(
                f"✅ Processed: {uploaded_file.name}"
            )
            st.session_state.last_processed.append(uploaded_file.name)

        status_text.text("Processing complete!")
        st.success(f"✅ Successfully processed {len(uploaded_files)} document(s)")
        st.rerun()

# Main content area
tab1, tab2, tab3, tab4 = st.tabs([
    "📊 Extracted Data",
    "📈 Analytics",
    "📝 Processing Log",
    "ℹ️ About"
])

with tab1:
    st.header("📊 Extracted Document Data")

    # Get all documents
    all_documents = crud.get_all_documents(db)

    if not all_documents:
        st.info("📭 No documents processed yet. Upload files and click 'Process Files' to begin.")
    else:
        # Document selector
        doc_options = {
            f"{doc.filename} (ID: {doc.id})": doc
            for doc in all_documents
        }

        selected_doc_label = st.selectbox(
            "Select a document to view:",
            options=list(doc_options.keys()),
            format_func=lambda x: x.split(" (ID:")[0]
        )

        if selected_doc_label:
            selected_doc = doc_options[selected_doc_label]

            # Document info
            col1, col2, col3, col4 = st.columns(4)
            with col1:
                st.metric("Document ID", selected_doc.id)
            with col2:
                st.metric("Method", selected_doc.processing_method)
            with col3:
                st.metric("Status", selected_doc.status)
            with col4:
                st.metric("Data Points", len(selected_doc.extracted_data))

            # Display extracted data
            if selected_doc.extracted_data:
                # Prepare data for display
                data_for_display = []
                for item in selected_doc.extracted_data:
                    if item.value and item.value != "Unchecked" and item.value != "Not checked":
                        data_for_display.append({
                            "Field": item.key,
                            "Value": item.value,
                            "Page": item.source_page + 1,
                            "Method": item.extraction_method
                        })

                if data_for_display:
                    # Create two columns for data and visualization
                    col_data, col_viz = st.columns([3, 2])

                    with col_data:
                        st.subheader("Extracted Fields")

                        # Group by extraction method
                        df = pd.DataFrame(data_for_display)

                        # Display as organized groups
                        methods = df['Method'].unique()
                        for method in methods:
                            method_data = df[df['Method'] == method]
                            if not method_data.empty:
                                st.caption(f"**{method} ({len(method_data)} fields)**")
                                display_df = method_data[['Field', 'Value']].reset_index(drop=True)
                                st.dataframe(
                                    display_df,
                                    use_container_width=True,
                                    hide_index=True
                                )

                    with col_viz:
                        st.subheader("Document Preview")

                        # Show highlighted PDF
                        pdf_path = os.path.join(TEMP_DIR, selected_doc.filename)
                        if os.path.exists(pdf_path):
                            with st.spinner("Generating preview..."):
                                try:
                                    highlighted_image = highlight_extractions_on_pdf(
                                        pdf_path,
                                        selected_doc.extracted_data
                                    )
                                    st.image(
                                        highlighted_image,
                                        caption="Extracted data locations",
                                        use_container_width=True
                                    )
                                    st.markdown(
                                        """
                                        **Highlight Legend:**
                                        - <span style="background-color:rgba(255, 255, 0, 0.3); padding: 2px 5px; border-radius: 3px;">Yellow:</span> Config Field
                                        - <span style="background-color:rgba(255, 0, 255, 0.3); padding: 2px 5px; border-radius: 3px;">Magenta:</span> Config Checkbox
                                        - <span style="background-color:rgba(255, 127, 0, 0.3); padding: 2px 5px; border-radius: 3px;">Orange:</span> Dynamic/Heuristic
                                        - <span style="background-color:rgba(0, 0, 255, 0.3); padding: 2px 5px; border-radius: 3px;">Blue:</span> Widget
                                        - <span style="background-color:rgba(0, 255, 0, 0.3); padding: 2px 5px; border-radius: 3px;">Green:</span> Table
                                        """, unsafe_allow_html=True
                                    )
                                except Exception as e:
                                    st.error(f"Could not generate preview: {str(e)}")
                        else:
                            st.warning("Original PDF not found")

                    # Export options
                    st.markdown("---")
                    st.subheader("📥 Export Options")
                    col1, col2 = st.columns(2)

                    with col1:
                        # Export as CSV
                        csv = df.to_csv(index=False)
                        st.download_button(
                            label="Download as CSV",
                            data=csv,
                            file_name=f"{selected_doc.filename.replace('.pdf', '')}_extracted.csv",
                            mime="text/csv"
                        )

                    with col2:
                        # Export as JSON
                        import json

                        json_data = json.dumps(data_for_display, indent=2)
                        st.download_button(
                            label="Download as JSON",
                            data=json_data,
                            file_name=f"{selected_doc.filename.replace('.pdf', '')}_extracted.json",
                            mime="application/json"
                        )
                else:
                    st.warning("No meaningful data extracted from this document")
            else:
                st.warning("No data extracted from this document")

with tab2:
    st.header("📈 Extraction Analytics")

    if all_documents:
        # Overall statistics
        total_docs = len(all_documents)
        total_fields = sum(len(doc.extracted_data) for doc in all_documents)

        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("Total Documents", total_docs)
        with col2:
            st.metric("Total Fields Extracted", total_fields)
        with col3:
            avg_fields = total_fields / total_docs if total_docs > 0 else 0
            st.metric("Avg Fields per Document", f"{avg_fields:.1f}")

        # Processing methods chart
        st.subheader("Processing Methods Used")
        methods_df = pd.DataFrame([
            {"Method": doc.processing_method, "Count": 1}
            for doc in all_documents
        ])
        method_counts = methods_df.groupby("Method").sum().reset_index()
        st.bar_chart(method_counts.set_index("Method"))

        # Success rate
        st.subheader("Processing Success Rate")
        success_count = sum(1 for doc in all_documents if doc.status == "SUCCESS")
        success_rate = (success_count / total_docs) * 100 if total_docs > 0 else 0
        st.progress(success_rate / 100)
        st.caption(f"{success_rate:.1f}% success rate ({success_count}/{total_docs} documents)")
    else:
        st.info("No data available for analytics. Process some documents first.")

with tab3:
    st.header("📝 Processing Log")

    if st.session_state.processing_log:
        # Display recent processing
        st.subheader("Recent Processing Activity")
        for log_entry in reversed(st.session_state.processing_log[-10:]):
            st.text(log_entry)
    else:
        st.info("No processing activity yet")

    # System info
    st.subheader("System Information")
    col1, col2 = st.columns(2)
    with col1:
        st.caption(f"**Configuration Directory:** {CONFIG_DIR}")
        st.caption(f"**Temp Directory:** {TEMP_DIR}")
    with col2:
        st.caption(f"**Configured Forms:** {len(config_manager.configs)}")
        st.caption(f"**Database Status:** Connected")

with tab4:
    st.header("ℹ️ About PDF Data Extractor Pro 3000")

    st.markdown("""
    ### Features

    **🎯 Precise Extraction Mode**
    - Configuration-based extraction using YAML templates
    - Optimized for known form types
    - High accuracy and speed

    **🤖 Flexible Extraction Mode**
    - Dynamic extraction based on heuristics
    - Works with any PDF form
    - Automatic field detection

    **📊 Advanced Capabilities**
    - Checkbox detection and state recognition
    - Table data extraction
    - Multi-page document support
    - Form widget extraction
    - Spatial analysis for complex layouts

    **💾 Data Management**
    - SQLite database for persistence
    - Export to CSV and JSON
    - Visual highlighting of extracted data

    ### How to Use

    1. **Select Mode**: Choose between Precise (for configured forms) or Flexible (for any form)
    2. **Upload Files**: Add one or more PDF documents
    3. **Process**: Click "Process Files" to extract data
    4. **Review**: View extracted data, analytics, and export results

    ### Technical Stack
    - **PDF Processing**: PyMuPDF (fitz)
    - **Database**: SQLAlchemy with SQLite
    - **UI**: Streamlit
    - **Configuration**: YAML-based templates
    """)

    st.markdown("---")
    st.caption("PDF Data Extractor Pro 3000 v1.0 - Intelligent Document Processing")
    st.caption("Designed for scalability, accuracy, and ease of use")