import fitz
import re
from collections import defaultdict
from typing import List, Dict, Any


class DynamicExtractor:
    """
    Extracts data from PDFs without predefined templates.
    It uses a combination of heuristics for finding key-value pairs,
    table structures, and interactive form widgets.
    """

    def _clean_text(self, text: str) -> str:
        """Standardizes text by cleaning and formatting."""
        if not text:
            return ""
        # Remove trailing colon, strip whitespace, and convert to Title Case
        return text.strip().strip(":").replace("_", " ").title()

    def _extract_from_widgets(self, page: fitz.Page) -> List[Dict[str, Any]]:
        """
        Extracts data from interactive form fields (widgets) like text boxes and checkboxes.
        This is highly reliable if the PDF is a proper form.

        FIX: This method was made more robust to handle different widget types and
        avoid the `AttributeError: 'Widget' object has no attribute 'value'`. It now
        relies on the more consistent `field_value` attribute and checks widget types.
        """
        results = []
        for widget in page.widgets():
            if not widget.field_name:
                continue

            key = self._clean_text(widget.field_name)
            value = ""

            # Handle different widget types safely
            if widget.field_type == fitz.PDF_WIDGET_TYPE_CHECKBOX:
                # For checkboxes, 'Off' is the typical value for unchecked.
                # Any other value (e.g., 'Yes', 'On') means it's checked.
                if widget.field_value != "Off":
                    value = "Checked"
            elif widget.field_type == fitz.PDF_WIDGET_TYPE_RADIOBUTTON:
                # For radio buttons, only capture the selected one.
                if widget.field_value != "Off":
                    # The key is the group name, value is the selected option.
                    value = self._clean_text(widget.field_value)
            else:
                # This covers Text, ComboBox, and ListBox fields.
                value = self._clean_text(widget.field_value)

            # Only add if we have a meaningful value.
            # We explicitly ignore "Unchecked" to reduce clutter in the results.
            if value and value != "Unchecked":
                coords_str = f"{widget.rect.x0},{widget.rect.y0},{widget.rect.x1},{widget.rect.y1}"
                results.append({
                    "key": key, "value": value, "page_num": page.number,
                    "coords": coords_str, "method": "Widget"
                })
        return results

    def _extract_from_tables(self, page: fitz.Page) -> List[Dict[str, Any]]:
        """
        Finds and extracts data from tables on the page.
        It assumes the first row of a table is the header.
        """
        results = []
        # find_tables() is a robust method to detect tabular data.
        tables = page.find_tables()
        for i, table in enumerate(tables):
            table_data = table.extract()
            if not table_data or len(table_data) < 2:
                continue  # Skip if no data or only a header

            header = [self._clean_text(h) for h in table_data[0]]

            for row_idx, row in enumerate(table_data[1:]):
                for col_idx, cell_value in enumerate(row):
                    if cell_value and col_idx < len(header) and header[col_idx]:
                        key = f"Table {i + 1} - Row {row_idx + 1} - {header[col_idx]}"
                        value = str(cell_value).strip()

                        if not value: continue

                        cell_bbox = table.cell_bbox((row_idx + 1, col_idx))
                        coords_str = f"{cell_bbox.x0},{cell_bbox.y0},{cell_bbox.x1},{cell_bbox.y1}"
                        results.append({
                            "key": key, "value": value, "page_num": page.number,
                            "coords": coords_str, "method": "Table"
                        })
        return results

    def _extract_from_text_heuristics(self, page: fitz.Page) -> List[Dict[str, Any]]:
        """
        Finds key-value pairs based on text layout, e.g., 'Label: Value'.
        This is a fallback for non-widget, non-table data.
        """
        results = []
        text_blocks = page.get_text("dict")["blocks"]
        for block in text_blocks:
            if "lines" not in block:
                continue
            for line in block["lines"]:
                line_text = "".join([span["text"] for span in line["spans"]]).strip()

                # Heuristic: Find a label ending with a colon.
                match = re.search(r'^(.+?):\s*(.+)', line_text)
                if match:
                    key = self._clean_text(match.group(1))
                    value = match.group(2).strip()

                    if key and value:
                        # Find coordinates of the value for highlighting
                        try:
                            value_rect = page.search_for(value, clip=fitz.Rect(line["bbox"]), quads=False)[0]
                            coords_str = f"{value_rect.x0},{value_rect.y0},{value_rect.x1},{value_rect.y1}"
                        except (IndexError, ValueError):
                            # Fallback to line's bounding box if search fails
                            bbox = line["bbox"]
                            coords_str = f"{bbox[0]},{bbox[1]},{bbox[2]},{bbox[3]}"

                        results.append({
                            "key": key, "value": value, "page_num": page.number,
                            "coords": coords_str, "method": "Heuristic"
                        })
        return results

    def extract_all(self, doc: fitz.Document) -> List[Dict[str, Any]]:
        """
        Orchestrates the entire dynamic extraction process for a document.
        It uses multiple strategies and combines their results, preventing duplicates.
        """
        all_results = []
        # Use a tuple of (key, page_num) to uniquely identify an extracted item
        # to prevent adding the same data point from different methods.
        extracted_items = set()

        for page in doc:
            # The order of extraction acts as a priority list.
            strategies = [
                self._extract_from_widgets,
                self._extract_from_tables,
                self._extract_from_text_heuristics
            ]

            for strategy_func in strategies:
                try:
                    data = strategy_func(page)
                    for item in data:
                        # Create a unique identifier for the data point
                        item_id = (item["key"], item["page_num"])
                        if item_id not in extracted_items:
                            all_results.append(item)
                            extracted_items.add(item_id)
                except Exception as e:
                    print(
                        f"Warning: Extractor strategy '{strategy_func.__name__}' failed on page {page.number} with error: {e}")

        return all_results
