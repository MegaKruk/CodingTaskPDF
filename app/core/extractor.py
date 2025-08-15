import fitz
from typing import Tuple, Optional
from app.utils.utils import clean_value

class Extractor:
    """A toolbox of precise, proximity-aware extraction methods called by config files."""

    @staticmethod
    def _get_rect_center(rect: fitz.Rect) -> fitz.Point:
        """Correctly calculates the center point of a fitz.Rect object."""
        return fitz.Point((rect.x0 + rect.x1) / 2, (rect.y0 + rect.y1) / 2)

    def find_field_value(self, page: fitz.Page, label: str, max_distance: int = 300, y_tolerance: int = 10,
                         instance: int = 0, **kwargs) -> Optional[Tuple[str, fitz.Rect]]:
        """
        Finds a text label and extracts the closest value to its right,
        handling multi-column layouts and vertical misalignments.
        """
        label_instances = page.search_for(label)
        if not label_instances or len(label_instances) <= instance:
            return None, None

        label_rect = label_instances[instance]

        # 1. Gather all candidate words in a reasonable area to the right
        search_rect = fitz.Rect(label_rect.x1, label_rect.y0 - y_tolerance, label_rect.x1 + max_distance,
                                label_rect.y1 + y_tolerance)
        words = page.get_text("words", clip=search_rect)
        if not words:
            return "", label_rect

        # Calculate the center point
        label_center = self._get_rect_center(label_rect)

        # 2. Find the single closest word to the label to start the value
        min_dist = float('inf')
        start_word = None

        for word_info in words:
            word_rect = fitz.Rect(word_info[:4])

            # Calculate the word's center for distance calculation
            word_center = self._get_rect_center(word_rect)
            dist = label_center.distance_to(word_center)

            if dist < min_dist:
                min_dist = dist
                start_word = word_info

        if not start_word:
            return "", label_rect

        # 3. Chain adjacent words to form the complete value
        value_words = [start_word]
        last_word_rect = fitz.Rect(start_word[:4])

        remaining_words = sorted([w for w in words if w != start_word], key=lambda w: w[0])

        for word_info in remaining_words:
            word_rect = fitz.Rect(word_info[:4])
            if word_rect.x0 - last_word_rect.x1 < 10 and abs(word_rect.y0 - last_word_rect.y0) < 3:
                value_words.append(word_info)
                last_word_rect.include_rect(word_rect)

        raw_value_text = " ".join(w[4] for w in value_words)
        value_text = clean_value(raw_value_text)

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

        # Use the helper to calculate centers
        label_center = self._get_rect_center(label_rect)

        def distance_to_center(r):
            r_center = self._get_rect_center(r)
            return label_center.distance_to(r_center)

        checkbox_rect = min(potential_checkboxes, key=distance_to_center)

        text_in_box = page.get_text("text", clip=checkbox_rect).strip().lower()
        return ("Checked" if 'x' in text_in_box or '✓' in text_in_box else "Unchecked"), checkbox_rect
