import fitz
import re
from typing import Tuple, Optional, List, Dict
from collections import defaultdict


class Extractor:
    """Enhanced precise extraction using robust line-based parsing with improved boundary detection."""

    def _clean_value(self, value: str) -> str:
        """Clean extracted value by removing form artifacts while preserving real data."""
        if not value:
            return ""

        # Remove sequences of underscores or dots
        cleaned = re.sub(r'[_]{3,}', '', value)  # Remove 3+ underscores
        cleaned = re.sub(r'[\.]{3,}', '', cleaned)  # Remove 3+ dots

        # Remove standalone underscores and dots at boundaries
        cleaned = re.sub(r'^\s*[_\.]+\s*|\s*[_\.]+\s*$', '', cleaned)

        # Remove common form artifacts but preserve real punctuation
        cleaned = re.sub(r'\s*\|\s*', '', cleaned)  # Remove pipes

        # Clean up excessive whitespace
        cleaned = re.sub(r'\s+', ' ', cleaned)

        return cleaned.strip()

    def find_all_fields_on_page(self, page: fitz.Page, fields_config: List[Dict]) -> List[Dict]:
        """
        Extract all configured fields using enhanced line-based parsing.
        This method groups words by lines and uses smart boundary detection.
        """
        results = {}
        all_labels = [f['label'] for f in fields_config]
        words = page.get_text("words")

        if not words:
            return []

        # Group words into lines based on Y coordinate
        lines = defaultdict(list)
        for w in words:
            # Round Y coordinate to group words on same line
            y_key = round(w[1] / 5.0) * 5  # Group within 5 pixels
            lines[y_key].append(w)

        # Sort lines by Y coordinate
        sorted_lines = sorted(lines.items(), key=lambda x: x[0])

        # Process each line
        for line_idx, (y_key, line_words) in enumerate(sorted_lines):
            # Sort words in line by X coordinate
            line_words = sorted(line_words, key=lambda w: w[0])

            i = 0
            while i < len(line_words):
                # Try to match multi-word labels
                found_label = None
                matched_word_count = 0

                # Try each label, longest first
                for label in sorted(all_labels, key=len, reverse=True):
                    label_words = label.split()

                    if i + len(label_words) <= len(line_words):
                        # Build phrase from current position
                        page_phrase = " ".join(line_words[i + j][4] for j in range(len(label_words)))

                        if page_phrase == label:
                            found_label = label
                            matched_word_count = len(label_words)
                            break

                if found_label:
                    # Found a label, now extract its value
                    value_words = []
                    start_index = i + matched_word_count

                    # First, try to get value from the same line
                    for k in range(start_index, len(line_words)):
                        current_word = line_words[k][4]

                        # Stop if we hit another label
                        is_next_label = False
                        for other_label in all_labels:
                            if other_label == found_label:
                                continue
                            other_words = other_label.split()
                            if current_word == other_words[0]:
                                # Check if full label matches from here
                                if k + len(other_words) <= len(line_words):
                                    test_phrase = " ".join(line_words[k + j][4] for j in range(len(other_words)))
                                    if test_phrase == other_label:
                                        is_next_label = True
                                        break

                        if is_next_label:
                            break

                        # Add word to value
                        value_words.append(line_words[k])

                    # If no value found on same line, check next line
                    if not value_words and line_idx + 1 < len(sorted_lines):
                        next_y_key, next_line_words = sorted_lines[line_idx + 1]

                        # Check if next line is close enough (within 30 pixels)
                        if next_y_key - y_key <= 30:
                            next_line_words = sorted(next_line_words, key=lambda w: w[0])

                            # Get label position for alignment check
                            label_x = line_words[i][0]

                            for word in next_line_words:
                                # Check if word is roughly aligned with label or to its right
                                if word[0] >= label_x - 10:
                                    word_text = word[4]

                                    # Stop if it's another label
                                    is_label = False
                                    for other_label in all_labels:
                                        if word_text == other_label.split()[0]:
                                            is_label = True
                                            break

                                    if is_label:
                                        break

                                    value_words.append(word)

                                    # For single line values below label, often just take first aligned word/phrase
                                    if word[0] > label_x + 200:  # Stop if too far to the right
                                        break

                    # Build and clean the value
                    value_text = self._clean_value(" ".join(w[4] for w in value_words))

                    # Get field name from config
                    field_name = next((f['name'] for f in fields_config if f['label'] == found_label), found_label)

                    # Calculate bounding rectangle
                    if value_words:
                        value_rect = fitz.Rect(value_words[0][:4])
                        for w in value_words[1:]:
                            value_rect.include_rect(fitz.Rect(w[:4]))
                    else:
                        # If no value, use area after label
                        label_rect_end = line_words[i + matched_word_count - 1]
                        value_rect = fitz.Rect(
                            label_rect_end[2], label_rect_end[1],
                            label_rect_end[2] + 50, label_rect_end[3]
                        )

                    # Store result if we have a value or if field expects empty values
                    if value_text or field_name in ['Title', 'Cell', 'e-mail']:
                        results[field_name] = (value_text, value_rect)

                    # Move index past this label and its value
                    i += matched_word_count + len([w for w in value_words if w in line_words[start_index:]])
                else:
                    i += 1

        return [{"name": name, "value": val, "rect": rect} for name, (val, rect) in results.items()]

    def find_checkbox_near_label(self, page: fitz.Page, label: str, search_radius: int = 50,
                                 instance: int = 0, **kwargs) -> Tuple[str, Optional[fitz.Rect]]:
        """Find checkbox state near a label using multiple detection methods."""

        # Search for the label
        label_instances = page.search_for(label)
        if not label_instances or len(label_instances) <= instance:
            # Try with colon
            label_with_colon = label + ":"
            label_instances = page.search_for(label_with_colon)
            if not label_instances or len(label_instances) <= instance:
                return "Not Found", None

        label_rect = label_instances[instance]

        # Define search area (primarily to the left of the label for checkboxes)
        search_area = fitz.Rect(
            label_rect.x0 - search_radius,
            label_rect.y0 - 5,
            label_rect.x0 + 10,  # Small area to the right
            label_rect.y1 + 5
        )

        # Method 1: Look for checkbox marks (X, checkmarks) in text
        words = page.get_text("words")
        checkbox_markers = ['x', 'X', '✓', '✔', '☑', '☒', '✗', '✘']

        for word in words:
            word_rect = fitz.Rect(word[:4])
            word_text = word[4].strip()

            if word_rect.intersects(search_area):
                if word_text in checkbox_markers:
                    return "Checked", word_rect

        # Method 2: Look for drawn rectangles/squares (checkbox shapes)
        shapes = page.get_drawings()
        potential_checkboxes = []

        for shape in shapes:
            if "rect" in shape:
                rect = shape["rect"]
                # Check if it's checkbox-sized and near label
                if (rect.intersects(search_area) and
                        not rect.is_empty and
                        5 < rect.width < 30 and
                        5 < rect.height < 30):
                    potential_checkboxes.append(rect)

        if potential_checkboxes:
            # Find closest checkbox to label
            def distance_to_label(r):
                label_center_x = (label_rect.x0 + label_rect.x1) / 2
                label_center_y = (label_rect.y0 + label_rect.y1) / 2
                r_center_x = (r.x0 + r.x1) / 2
                r_center_y = (r.y0 + r.y1) / 2
                return ((label_center_x - r_center_x) ** 2 + (label_center_y - r_center_y) ** 2) ** 0.5

            checkbox_rect = min(potential_checkboxes, key=distance_to_label)

            # Check if there's a mark inside the checkbox
            text_in_box = page.get_text("text", clip=checkbox_rect).strip().lower()

            for marker in ['x', '✓', '✔']:
                if marker in text_in_box:
                    return "Checked", checkbox_rect

            # No mark found, checkbox is unchecked
            return "Unchecked", checkbox_rect

        # Method 3: Check form widgets
        for widget in page.widgets():
            if widget.rect.intersects(search_area):
                if widget.field_type in [fitz.PDF_WIDGET_TYPE_CHECKBOX, fitz.PDF_WIDGET_TYPE_RADIOBUTTON]:
                    if widget.field_value and widget.field_value != "Off":
                        return "Checked", widget.rect
                    else:
                        return "Unchecked", widget.rect

        # No checkbox found
        return "Unchecked", label_rect