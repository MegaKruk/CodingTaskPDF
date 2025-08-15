import fitz
import re


def highlight_extractions_on_pdf(pdf_path: str, extractions: list) -> bytes:
    """
    Draws highlights on a PDF page and returns it as a PNG image bytes.

    Args:
        pdf_path (str): Path to the original PDF file.
        extractions (list): A list of ExtractedData ORM objects.

    Returns:
        Bytes of the rendered PNG image of the first page with highlights.
    """
    doc = fitz.open(pdf_path)

    # We will render the first page where most data usually is.
    # A more advanced version could handle multi-page highlights.
    page = doc[0]

    for item in extractions:
        # Only highlight items from the first page.
        if item.source_coordinates and item.source_page == 0:
            try:
                # Coords are stored as "x0,y0,x1,y1"
                coords = [float(c) for c in item.source_coordinates.split(',')]

                # Validate coordinates
                if len(coords) != 4:
                    continue

                # Check for invalid coordinates (0,0,0,0)
                if all(c == 0.0 for c in coords):
                    continue

                rect = fitz.Rect(coords)

                # Validate rect
                if rect.is_empty or not rect.is_valid:
                    continue

                # Add a semi-transparent colored highlight based on extraction method.
                color_map = {
                    # Config-Based Methods
                    "Config Field": [1, 1, 0],  # Yellow
                    "Config Checkbox": [1, 0, 1],  # Magenta

                    # Dynamic/Heuristic Methods
                    "Dynamic Heuristic": [1, 0.5, 0],  # Orange
                    "Visual Checkbox": [1, 0.5, 0],  # Orange
                    "Compound Label": [1, 0.5, 0],  # Orange
                    "Form Field": [1, 0.5, 0],  # Orange (Used by your dynamic extractor)
                    "Label Match": [1, 0.5, 0],  # Orange
                    "Checkbox Option": [1, 0.5, 0],  # Orange

                    # General High-Reliability Methods
                    "Widget": [0, 0, 1],  # Blue
                    "Table": [0, 1, 0],  # Green
                }
                color = color_map.get(item.extraction_method, [1, 0, 0])  # Red for unknown

                highlight = page.add_highlight_annot(rect)
                highlight.set_colors(stroke=color)
                highlight.set_info(content=f"Key: {item.key}\nValue: {item.value}\nMethod: {item.extraction_method}")
                highlight.update()
            except (ValueError, IndexError, TypeError) as e:
                print(f"Could not parse coordinates for highlighting: {item.source_coordinates}, Error: {e}")

    # Render the page with highlights to a PNG pixmap
    # Higher DPI gives a clearer image
    pix = page.get_pixmap(dpi=150)
    img_bytes = pix.tobytes("png")

    doc.close()
    return img_bytes


def clean_value(value: str) -> str:
    """Aggressively cleans the extracted value to remove placeholders and artifacts."""
    if not value:
        return ""
    # Remove any sequence of 2 or more underscores or dots
    cleaned = re.sub(r'[_\.]{2,}', ' ', value)
    # Remove common junk characters and artifacts from OCR
    cleaned = re.sub(r'[\(\)\[\]\|:]', '', cleaned)
    # Remove standalone single letters that are likely noise
    cleaned = re.sub(r'\b[a-zA-Z]\b', '', cleaned)
    # Collapse multiple spaces and strip
    cleaned = re.sub(r'\s+', ' ', cleaned).strip()
    return cleaned


def clean_text(text: str) -> str:
    """Standardizes text for KEYS by cleaning and formatting."""
    if not text: return ""
    # Remove underscores and dots used for form lines
    cleaned = re.sub(r'[_\.]{3,}', '', text)
    cleaned = cleaned.strip().strip(":").strip()
    return cleaned
