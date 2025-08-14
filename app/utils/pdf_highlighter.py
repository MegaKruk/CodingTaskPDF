import fitz


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
                rect = fitz.Rect(coords)

                # Add a semi-transparent colored highlight based on extraction method.
                color_map = {
                    "Widget": [0, 0, 1],  # Blue
                    "Table": [0, 1, 0],  # Green
                    "Heuristic": [1, 1, 0],  # Yellow
                }
                color = color_map.get(item.extraction_method, [1, 0, 0])  # Red for unknown

                highlight = page.add_highlight_annot(rect)
                highlight.set_colors(stroke=color)
                highlight.set_info(content=f"Key: {item.key}\nMethod: {item.extraction_method}")
                highlight.update()
            except (ValueError, IndexError):
                print(f"Could not parse coordinates for highlighting: {item.source_coordinates}")

    # Render the page with highlights to a PNG pixmap
    # Higher DPI gives a clearer image
    pix = page.get_pixmap(dpi=150)
    img_bytes = pix.tobytes("png")

    doc.close()
    return img_bytes
