import fitz
import re
from typing import Tuple, Optional, List


class Extractor:
    """A toolbox of precise extraction methods called by config files."""

    @staticmethod
    def _clean_value(value: str) -> str:
        """Aggressively cleans the extracted value to remove placeholders and artifacts."""
        if not value:
            return ""
        # Remove sequences of underscores or dots
        cleaned = re.sub(r'[_\.]{2,}', ' ', value)
        # Remove common junk characters and artifacts from OCR
        cleaned = re.sub(r'[\(\)\[\]\|]', '', cleaned)
        # Remove standalone single letters that are likely noise, but keep real single letter values like A, B, etc.
        # This looks for a single letter surrounded by spaces or at the boundaries of the string.
        cleaned = re.sub(r'\s+[a-zA-Z]\s+', ' ', f' {cleaned} ')
        # Collapse multiple spaces and strip
        cleaned = re.sub(r'\s+', ' ', cleaned).strip()
        return cleaned

    def find_text_right_of_label(self, page: fitz.Page, label: str, all_labels: List[str], max_distance: int = 400,
                                 y_tolerance: int = 5, instance: int = 0, **kwargs) -> Optional[Tuple[str, fitz.Rect]]:
        """
        Finds a text label and extracts the value to its right, intelligently stopping at the next label or a large gap.
        """
        label_instances = page.search_for(label)
        if not label_instances or len(label_instances) <= instance:
            return None, None

        label_rect = label_instances[instance]

        # Define a search area to the right of the label
        search_rect = fitz.Rect(label_rect.x1, label_rect.y0 - y_tolerance, label_rect.x1 + max_distance,
                                label_rect.y1 + y_tolerance)
        words = page.get_text("words", clip=search_rect)
        if not words:
            return "", label_rect

        # Sort candidate words by their left coordinate
        words.sort(key=lambda w: w[0])

        value_words = []
        last_word_x1 = label_rect.x1

        # Boundary aware logic
        for word_info in words:
            word_rect = fitz.Rect(word_info[:4])
            word_text = word_info[4]

            # Stop if the horizontal gap is too large, indicating a new column/field
            if word_rect.x0 - last_word_x1 > 20 and value_words:
                break

            # Stop if the current word is the start of another known label
            is_next_label = False
            # Create a string from the current word onwards to check for multi-word labels
            remaining_text_preview = " ".join(w[4] for w in words if w[0] >= word_info[0])
            for other_label in all_labels:
                if remaining_text_preview.startswith(other_label) and label != other_label:
                    is_next_label = True
                    break

            if is_next_label:
                break  # Stop collecting words if we've hit the next field's label

            value_words.append(word_info)
            last_word_x1 = word_rect.x1

        if not value_words:
            return "", label_rect

        raw_value_text = " ".join(w[4] for w in value_words)
        value_text = self._clean_value(raw_value_text)

        # Create a bounding box for the accurately captured value words
        final_value_rect = fitz.Rect(value_words[0][:4])
        for w_info in value_words[1:]:
            final_value_rect.include_rect(w_info[:4])

        return value_text, final_value_rect

    def find_checkbox_near_label(self, page: fitz.Page, label: str, search_radius: int = 50, instance: int = 0,
                                 **kwargs) -> Tuple[str, fitz.Rect]:
        label_instances = page.search_for(label)
        if not label_instances or len(label_instances) <= instance:
            return "Not Found", None

        label_rect = label_instances[instance]
        search_area = label_rect + (-search_radius, -search_radius, search_radius, search_radius)
        shapes = page.get_drawings()
        potential_checkboxes = [s["rect"] for s in shapes if
                                s["rect"].intersects(search_area) and not s["rect"].is_empty and 5 < s[
                                    "rect"].width < 100 and 5 < s["rect"].height < 100]

        if not potential_checkboxes:
            return "Not Found", label_rect

        label_center_x = (label_rect.x0 + label_rect.x1) / 2
        label_center_y = (label_rect.y0 + label_rect.y1) / 2

        def distance(r):
            r_center_x = (r.x0 + r.x1) / 2
            r_center_y = (r.y0 + r.y1) / 2
            return ((label_center_x - r_center_x) ** 2 + (label_center_y - r_center_y) ** 2) ** 0.5

        checkbox_rect = min(potential_checkboxes, key=distance)

        text_in_box = page.get_text("text", clip=checkbox_rect).strip().lower()
        return ("Checked" if 'x' in text_in_box or '✓' in text_in_box else "Unchecked"), checkbox_rect
