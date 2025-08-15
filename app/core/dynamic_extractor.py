import re
from typing import List, Dict, Any
import fitz
from app.utils.utils import clean_value, clean_text


class DynamicExtractor:
    """
    Extracts data from PDFs using a re-engineered, spatially-aware engine.
    This version correctly handles complex layouts, visual checkboxes, and multi-column forms.
    """

    def _is_form_fill_line(self, text: str) -> bool:
        """Check if text is just form fill lines (underscores, dots)."""
        return bool(re.match(r'^[_\.\s]+$', text))

    def _is_checkbox_marker(self, text: str) -> bool:
        """Check if text represents a checkbox marker."""
        return text.strip().lower() in ['x', '✓', '✔', '☑', '☐']

    def _find_compound_labels(self, all_words: List, processed_indices: set) -> List[Dict]:
        """Find compound labels like 'Passport No.' that might be split across words."""
        compound_patterns = [
            ["Passport", "No."],
            ["I.D", "Card", "No."],
            ["Date", "of", "Birth"],
            ["Level", "of", "Education"],
            ["No", "of", "Dependants"],
            ["Residential", "Address"],
            ["Period", "of", "residence"],
            ["Gross", "monthly", "income"],
            ["Net", "monthly", "income"],
            ["Other", "monthly", "income"],
            ["Monthly", "salary", "date"],
            ["Account", "number"],
            ["Time", "with", "current", "bank"],
            ["Expiry", "date"],
            ["Present", "balance"],
            ["Bank", "Name"],
            ["Account", "Name"],
            ["Full", "name"],
            ["Tel", "No."],
            ["Tel", "Nos."],
            ["Next", "of", "Kin"],
            ["Loan", "Amount", "Required"],
            ["Term", "preferred"],
            ["Loan", "Purpose"],
            ["Copy", "Documents", "Required"],
            ["Direct", "Debit", "Authority"],
            ["Account", "number", "to", "be", "debited"],
            ["Employer's", "name", "and", "address"],
            ["Period", "in", "current", "employment"],
            ["Current", "or", "previous", "credit", "facilities"],
            ["Facilities", "with", "other", "Bank"],
            ["Name", "and", "residential", "address"],
            ["Officer's", "Name"],
            ["Approving", "Manager's", "name"],
        ]

        found_labels = []

        for pattern in compound_patterns:
            for i in range(len(all_words) - len(pattern) + 1):
                if i in processed_indices:
                    continue

                # Check if pattern matches starting from position i
                match = True
                matched_indices = []

                for j, pattern_word in enumerate(pattern):
                    word_idx = i + j
                    if word_idx >= len(all_words) or word_idx in processed_indices:
                        match = False
                        break

                    word_text = all_words[word_idx][4].strip()
                    if word_text.lower() != pattern_word.lower():
                        match = False
                        break
                    matched_indices.append(word_idx)

                if match:
                    # Calculate bounding box for the entire compound label
                    first_word = all_words[i]
                    last_word = all_words[i + len(pattern) - 1]
                    label_rect = fitz.Rect(
                        first_word[0], first_word[1],
                        last_word[2], last_word[3]
                    )

                    label_text = " ".join(pattern)
                    found_labels.append({
                        'text': label_text,
                        'rect': label_rect,
                        'indices': matched_indices
                    })

                    # Mark these indices as processed
                    for idx in matched_indices:
                        processed_indices.add(idx)
                    break

        return found_labels

    def _find_value_for_label(self, label_rect: fitz.Rect, all_words: List, processed_indices: set) -> str:
        """Find value for a given label using improved spatial logic."""
        candidates = []

        # Define search areas
        # 1. Right of label (same line)
        right_search = fitz.Rect(
            label_rect.x1 + 2, label_rect.y0 - 3,
            label_rect.x1 + 300, label_rect.y1 + 3
        )

        # 2. Below label (next line)
        below_search = fitz.Rect(
            label_rect.x0 - 20, label_rect.y1,
            label_rect.x1 + 300, label_rect.y1 + 30
        )

        for i, word in enumerate(all_words):
            if i in processed_indices:
                continue

            word_rect = fitz.Rect(word[:4])
            word_text = word[4].strip()

            if not word_text or self._is_form_fill_line(word_text):
                continue

            # Skip checkbox markers and other labels
            if self._is_checkbox_marker(word_text) or word_text.endswith(':'):
                continue

            # Check if word is in search areas
            distance_right = 999999
            distance_below = 999999

            if word_rect.intersects(right_search):
                distance_right = word_rect.x0 - label_rect.x1
            elif word_rect.intersects(below_search):
                distance_below = abs(word_rect.y0 - label_rect.y1) + abs(word_rect.x0 - label_rect.x0) * 0.1
            else:
                continue

            min_distance = min(distance_right, distance_below)
            candidates.append((min_distance, i, word_text, word_rect))

        if not candidates:
            return ""

        # Sort by distance and collect consecutive words
        candidates.sort(key=lambda x: x[0])

        value_parts = []
        last_rect = None

        for distance, idx, text, rect in candidates:
            if len(value_parts) == 0:
                # First word
                value_parts.append(text)
                processed_indices.add(idx)
                last_rect = rect
            elif last_rect and abs(rect.x0 - last_rect.x1) < 20 and abs(rect.y0 - last_rect.y0) < 5:
                # Consecutive word on same line
                value_parts.append(text)
                processed_indices.add(idx)
                last_rect = rect
            else:
                # Gap too large, stop collecting
                break

        return " ".join(value_parts) if value_parts else ""

    def _find_checkbox_options_for_category(self, page: fitz.Page, category_words: List[str], all_words: List,
                                            processed_indices: set) -> List[Dict[str, Any]]:
        """Find checkbox options for a given category."""
        results = []

        for option in category_words:
            for i, word in enumerate(all_words):
                if i in processed_indices:
                    continue

                word_text = word[4].strip()
                word_rect = fitz.Rect(word[:4])

                if word_text == option:
                    # Look for checkbox marker near this option
                    search_area = fitz.Rect(
                        word_rect.x0 - 30, word_rect.y0 - 5,
                        word_rect.x1 + 30, word_rect.y1 + 5
                    )

                    checkbox_value = "Not checked"
                    checkbox_rect = word_rect

                    for j, check_word in enumerate(all_words):
                        if j == i or j in processed_indices:
                            continue

                        check_rect = fitz.Rect(check_word[:4])
                        check_text = check_word[4].strip()

                        if check_rect.intersects(search_area) and self._is_checkbox_marker(check_text):
                            checkbox_value = "Checked"
                            checkbox_rect = check_rect
                            processed_indices.add(j)
                            break

                    processed_indices.add(i)
                    coords_str = f"{checkbox_rect.x0:.1f},{checkbox_rect.y0:.1f},{checkbox_rect.x1:.1f},{checkbox_rect.y1:.1f}"
                    results.append({
                        "key": f"{option} (checkbox)",
                        "value": checkbox_value,
                        "page_num": page.number,
                        "coords": coords_str,
                        "method": "Checkbox Option"
                    })
                    break

        return results

    def _extract_from_widgets(self, page: fitz.Page) -> List[Dict[str, Any]]:
        """Extract data from interactive form widgets."""
        results = []
        for widget in page.widgets():
            if not widget.field_name:
                continue
            key = clean_text(widget.field_name)

            if widget.field_type == fitz.PDF_WIDGET_TYPE_CHECKBOX:
                value = "Checked" if widget.field_value != "Off" else "Not checked"
                key = f"{key} (checkbox)"
            elif widget.field_type == fitz.PDF_WIDGET_TYPE_RADIOBUTTON:
                value = "Checked" if widget.field_value != "Off" else "Not checked"
                key = f"{key} (checkbox)"
            else:
                value = clean_value(widget.field_value if widget.field_value else "")

            if value:
                coords_str = f"{widget.rect.x0:.1f},{widget.rect.y0:.1f},{widget.rect.x1:.1f},{widget.rect.y1:.1f}"
                results.append({
                    "key": key,
                    "value": value,
                    "page_num": page.number,
                    "coords": coords_str,
                    "method": "Widget"
                })
        return results

    def _extract_from_tables(self, page: fitz.Page) -> List[Dict[str, Any]]:
        """Extract data from tables."""
        results = []
        try:
            tables = page.find_tables()
            for i, table in enumerate(tables):
                try:
                    table_data = table.extract()
                    if not table_data or len(table_data) < 2:
                        continue

                    header = [clean_text(h) for h in table_data[0] if h]
                    for row_idx, row in enumerate(table_data[1:]):
                        for col_idx, cell_value in enumerate(row):
                            if cell_value and col_idx < len(header) and header[col_idx]:
                                value = clean_value(str(cell_value))
                                if value and not self._is_form_fill_line(value):
                                    key = f"Table {i + 1} - {header[col_idx]}"
                                    cell_bbox = table.get_cell_bbox((row_idx + 1, col_idx))
                                    coords_str = f"{cell_bbox.x0:.1f},{cell_bbox.y0:.1f},{cell_bbox.x1:.1f},{cell_bbox.y1:.1f}"
                                    results.append({
                                        "key": key,
                                        "value": value,
                                        "page_num": page.number,
                                        "coords": coords_str,
                                        "method": "Table"
                                    })
                except Exception as e:
                    print(f"Warning: Table extraction failed: {e}")
        except:
            pass
        return results

    def _extract_spatial_data(self, page: fitz.Page, processed_keys: set) -> List[Dict[str, Any]]:
        """Extract form fields using advanced spatial analysis."""
        all_words = page.get_text("words")
        processed_indices = set()
        results = []

        # 1. Handle checkbox groups first
        checkbox_groups = [
            ["Mr", "Mrs", "Miss", "Ms"],
            ["Married", "Single"],
            ["Male", "Female"],
            ["Yes", "No"]
        ]

        for group in checkbox_groups:
            checkbox_results = self._find_checkbox_options_for_category(
                page, group, all_words, processed_indices
            )
            for result in checkbox_results:
                if result["key"] not in processed_keys:
                    results.append(result)
                    processed_keys.add(result["key"])

        # 2. Find compound labels
        compound_labels = self._find_compound_labels(all_words, processed_indices)

        for label_info in compound_labels:
            key = label_info['text']
            if key not in processed_keys:
                value = self._find_value_for_label(label_info['rect'], all_words, processed_indices)
                if value:
                    coords_str = f"{label_info['rect'].x0:.1f},{label_info['rect'].y0:.1f},{label_info['rect'].x1 + 100:.1f},{label_info['rect'].y1:.1f}"
                    results.append({
                        "key": key,
                        "value": value,
                        "page_num": page.number,
                        "coords": coords_str,
                        "method": "Compound Label"
                    })
                    processed_keys.add(key)

        # 3. Find simple labels ending with colon
        for i, word in enumerate(all_words):
            if i in processed_indices:
                continue

            word_text = word[4].strip()
            word_rect = fitz.Rect(word[:4])

            if word_text.endswith(':') and len(word_text) > 1:
                key = clean_text(word_text)

                if key and key not in processed_keys and not key.isdigit():
                    value = self._find_value_for_label(word_rect, all_words, processed_indices)

                    if value:
                        processed_indices.add(i)
                        processed_keys.add(key)

                        coords_str = f"{word_rect.x0:.1f},{word_rect.y0:.1f},{word_rect.x1 + 100:.1f},{word_rect.y1:.1f}"
                        results.append({
                            "key": key,
                            "value": value,
                            "page_num": page.number,
                            "coords": coords_str,
                            "method": "Form Field"
                        })

        # 4. Look for standalone labels without colons
        single_labels = [
            "Title", "Surname", "Forename", "Forenames", "Nationality",
            "Address", "Tel", "Cell", "Email", "Branch", "Name",
            "Employer", "Occupation", "Income", "Purpose", "Signature",
            "Dependants", "Accomodation", "Rent", "Mortgage", "Repayment",
            "Limit", "Repayments", "Relationship", "Declaration"
        ]

        for label in single_labels:
            if any(label.lower() in key.lower() for key in processed_keys):
                continue

            for i, word in enumerate(all_words):
                if i in processed_indices:
                    continue

                word_text = word[4].strip()
                if word_text.lower() == label.lower():
                    word_rect = fitz.Rect(word[:4])
                    value = self._find_value_for_label(word_rect, all_words, processed_indices)

                    if value:
                        key = label
                        if key not in processed_keys:
                            processed_indices.add(i)
                            processed_keys.add(key)

                            coords_str = f"{word_rect.x0:.1f},{word_rect.y0:.1f},{word_rect.x1 + 100:.1f},{word_rect.y1:.1f}"
                            results.append({
                                "key": key,
                                "value": value,
                                "page_num": page.number,
                                "coords": coords_str,
                                "method": "Label Match"
                            })
                        break

        return results

    def extract_all(self, doc: fitz.Document) -> List[Dict[str, Any]]:
        """Orchestrates the entire dynamic extraction process for a document."""
        all_results = []
        processed_keys = set()

        for page in doc:
            # Try widgets first (most reliable)
            widget_data = self._extract_from_widgets(page)
            for item in widget_data:
                if item["key"] not in processed_keys:
                    all_results.append(item)
                    processed_keys.add(item["key"])

            # Try tables
            table_data = self._extract_from_tables(page)
            for item in table_data:
                if item["key"] not in processed_keys:
                    all_results.append(item)
                    processed_keys.add(item["key"])

            # Finally spatial analysis
            spatial_data = self._extract_spatial_data(page, processed_keys)
            all_results.extend(spatial_data)

        return all_results
