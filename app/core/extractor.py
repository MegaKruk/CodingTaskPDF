import fitz
import re
from typing import Tuple, Optional, List, Dict
from collections import defaultdict


class Extractor:
    """A toolbox of precise extraction methods. The text extractor uses a robust,
    line-based sequential parsing model to correctly identify field boundaries."""

    @staticmethod
    def _clean_value(value: str) -> str:
        """Aggressively cleans the extracted value."""
        if not value: return ""
        # Remove sequences of underscores or dots and surrounding whitespace
        cleaned = re.sub(r'(\s*[_\.]{2,}\s*)', ' ', value)
        # Remove common junk characters and artifacts
        cleaned = re.sub(r'[\(\)\[\]\|:]', '', cleaned)
        # Collapse multiple spaces and strip
        cleaned = re.sub(r'\s+', ' ', cleaned).strip()
        return cleaned

    def find_all_fields_on_page(self, page: fitz.Page, fields_config: List[Dict]) -> List[Dict]:
        """
        Processes an entire page to find all configured fields using a robust,
        line-based sequential parsing model with perfected boundary detection.
        """
        results = {}
        all_labels = [f['label'] for f in fields_config]
        words = page.get_text("words")
        if not words:
            return []

        lines = defaultdict(list)
        for w in words:
            lines[round(w[3] / 10.0)].append(w)

        for y_key in sorted(lines.keys()):
            line_words = sorted(lines[y_key], key=lambda w: w[0])

            i = 0
            while i < len(line_words):
                # Multi-word label mtching
                found_label, matched_word_count = None, 0
                for label in sorted(all_labels, key=len, reverse=True):
                    label_words_list = label.split()
                    if i + len(label_words_list) <= len(line_words):
                        page_phrase = " ".join(line_words[i + j][4] for j in range(len(label_words_list)))
                        if page_phrase == label:
                            found_label, matched_word_count = label, len(label_words_list)
                            break

                if found_label:
                    value_words = []
                    start_index = i + matched_word_count

                    # Boundary detection
                    for k in range(start_index, len(line_words)):
                        current_word = line_words[k][4]

                        # Check if the current word is the start of ANY other label
                        is_next_label = False
                        for other_label in all_labels:
                            if current_word == other_label.split()[0]:
                                # To be sure, check if the full label matches from here
                                other_label_words = other_label.split()
                                if k + len(other_label_words) <= len(line_words):
                                    page_phrase_preview = " ".join(
                                        line_words[k + j][4] for j in range(len(other_label_words)))
                                    if page_phrase_preview == other_label:
                                        is_next_label = True
                                        break
                        if is_next_label:
                            break  # Boundary detected. Stop.

                        value_words.append(line_words[k])

                    value_text = self._clean_value(" ".join(w[4] for w in value_words))
                    field_name = next((f['name'] for f in fields_config if f['label'] == found_label), found_label)

                    if value_words:
                        value_rect = fitz.Rect(value_words[0][:4])
                        for w in value_words[1:]: value_rect.include_rect(w[:4])
                    else:
                        label_rect_end = line_words[i + matched_word_count - 1]
                        value_rect = fitz.Rect(label_rect_end[2], label_rect_end[1], label_rect_end[2] + 50,
                                               label_rect_end[3])

                    results[field_name] = (value_text, value_rect)
                    i += matched_word_count + len(value_words)
                else:
                    i += 1

        return [{"name": name, "value": val, "rect": rect} for name, (val, rect) in results.items()]

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
