#!/usr/bin/env python3
"""
PDF Form Data Extractor

A robust application for extracting structured data from PDF forms using configurable
data models. Handles complex forms with checkboxes, text fields, and handwritten content.

Key features:
- YAML-based configuration for different form types
- Multi-method extraction approach with debugging
- Advanced pattern matching and text analysis
- Export to CSV and structured output
- Error handling and logging

Author: Filip
Date: 2025
"""

import os
import sys
import yaml
import pandas as pd
import fitz  # PyMuPDF
import re
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass, field
from pathlib import Path
import logging

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


@dataclass
class FormField:
    """Represents a form field with its properties and extraction rules"""
    name: str
    label: str
    field_type: str = "text"  # text, checkbox, select
    required: bool = False
    validation_pattern: Optional[str] = None
    page_num: Optional[int] = None
    instance: int = 0  # For handling multiple fields with same label
    extraction_hints: List[str] = field(default_factory=list)  # Additional patterns


@dataclass
class ExtractionResult:
    """Container for extraction results with metadata"""
    form_type: str
    file_path: str
    extracted_data: Dict[str, Any] = field(default_factory=dict)
    confidence_scores: Dict[str, float] = field(default_factory=dict)
    errors: List[str] = field(default_factory=list)
    processing_time: float = 0.0
    debug_info: Dict[str, Any] = field(default_factory=dict)


class FormConfigLoader:
    """Loads and manages form configurations from YAML files"""

    def __init__(self, config_dir: str = "configs"):
        self.config_dir = Path(config_dir)
        self.configs = {}
        self._load_configs()

    def _load_configs(self):
        """Load all YAML configuration files"""
        if not self.config_dir.exists():
            logger.warning(f"Config directory {self.config_dir} not found")
            return

        for config_file in self.config_dir.glob("*.yml"):
            try:
                with open(config_file, 'r', encoding='utf-8') as f:
                    config = yaml.safe_load(f)
                    form_type = config.get('form_type', config_file.stem)
                    self.configs[form_type] = config
                    logger.info(f"Loaded config for {form_type}")
            except Exception as e:
                logger.error(f"Error loading config {config_file}: {e}")

    def get_config(self, form_type: str) -> Optional[Dict]:
        """Get configuration for specific form type"""
        return self.configs.get(form_type)

    def detect_form_type(self, text: str) -> Optional[str]:
        """Detect form type based on text content"""
        for form_type, config in self.configs.items():
            identification_string = config.get('identification_string', '')
            if identification_string.lower() in text.lower():
                return form_type
        return None


class AdvancedTextAnalyzer:
    """Advanced text analysis for PDF form extraction"""

    def __init__(self, debug=False):
        self.debug = debug

    def analyze_text_structure(self, text: str) -> Dict[str, Any]:
        """Analyze the structure of extracted PDF text"""
        lines = text.split('\n')

        analysis = {
            'total_lines': len(lines),
            'non_empty_lines': [line.strip() for line in lines if line.strip()],
            'field_markers': [],
            'user_inputs': [],
            'form_structure': []
        }

        # Find lines with field markers (underscores, dots)
        for i, line in enumerate(lines):
            if re.search(r'_{3,}', line):
                analysis['field_markers'].append((i, line.strip()))
            elif re.search(r'\.{3,}', line):
                analysis['field_markers'].append((i, line.strip()))

        # Find potential user inputs (text that looks like filled data)
        for i, line in enumerate(lines):
            stripped_line = line.strip()
            if self._looks_like_user_input(stripped_line):
                analysis['user_inputs'].append((i, stripped_line))

        return analysis

    def _looks_like_user_input(self, text: str) -> bool:
        """Identify if text looks like user input rather than form structure"""
        if not text or len(text) < 2:
            return False

        # Skip obvious form elements
        form_indicators = [
            r'^[_\.]{3,}',  # Starts with underscores or dots
            r'^\d+\.\s*[A-Z]',  # Numbered sections
            r'^[A-Z][a-z]+\s*:',  # Form labels
            r'^\([A-Za-z]+\)',  # Instructions in parentheses
        ]

        for pattern in form_indicators:
            if re.match(pattern, text):
                return False

        # Look for user input characteristics
        user_input_patterns = [
            r'^[A-Z][a-z]+$',  # Single capitalized word (name)
            r'^\d{1,2}/\d{1,2}/\d{4}$',  # Date
            r'^\d+$',  # Numbers
            r'^[A-Z][a-z]+\s+[A-Z][a-z]+',  # Multiple names
            r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$',  # Email
        ]

        return any(re.match(pattern, text) for pattern in user_input_patterns)

    def extract_field_context(self, text: str, field_label: str) -> Dict[str, Any]:
        """Extract context around a field label for better value extraction"""
        lines = text.split('\n')
        label_clean = field_label.rstrip(':').strip()

        context = {
            'label_line': -1,
            'surrounding_lines': [],
            'potential_values': [],
            'line_structure': None
        }

        # Find the line containing the label
        for i, line in enumerate(lines):
            if label_clean.lower() in line.lower():
                context['label_line'] = i
                context['line_structure'] = line.strip()

                # Get surrounding lines for context
                start = max(0, i - 2)
                end = min(len(lines), i + 3)
                context['surrounding_lines'] = [lines[j].strip() for j in range(start, end)]

                # Look for potential values in the same line and nearby lines
                same_line_value = self._extract_from_line(line, label_clean)
                if same_line_value:
                    context['potential_values'].append(('same_line', same_line_value))

                # Check next few lines for standalone values
                for j in range(i + 1, min(len(lines), i + 4)):
                    next_line = lines[j].strip()
                    if self._looks_like_user_input(next_line):
                        context['potential_values'].append(('next_line', next_line))

                break

        return context

    def _extract_from_line(self, line: str, label: str) -> Optional[str]:
        """Extract value from the same line as the label"""
        label_escaped = re.escape(label)

        # Remove the label and everything before it
        after_label = re.sub(rf'.*?{label_escaped}[:\s]*', '', line, flags=re.IGNORECASE)

        # Remove common form artifacts
        cleaned = re.sub(r'_{3,}.*$', '', after_label)  # Remove trailing underscores
        cleaned = re.sub(r'\.{3,}.*$', '', cleaned)  # Remove trailing dots
        cleaned = cleaned.strip()

        # Check if what's left looks like valid input
        if cleaned and len(cleaned) > 1 and not re.match(r'^[_.\-\s]+$', cleaned):
            # Additional cleaning
            cleaned = re.sub(r'\s+', ' ', cleaned)  # Normalize whitespace
            cleaned = cleaned.strip()
            return cleaned

        return None


class PDFDataExtractor:
    """Main class for extracting data from PDF forms"""

    def __init__(self, config_loader: FormConfigLoader, debug=False):
        self.config_loader = config_loader
        self.text_analyzer = AdvancedTextAnalyzer(debug=debug)
        self.debug = debug

    def extract_from_file(self, file_path: str) -> ExtractionResult:
        """Extract data from a single PDF file"""
        import time
        start_time = time.time()

        result = ExtractionResult(
            form_type="unknown",
            file_path=file_path
        )

        try:
            # Open PDF and extract text
            doc = fitz.open(file_path)
            full_text = ""

            for page_num in range(len(doc)):
                page = doc.load_page(page_num)
                full_text += page.get_text()

            if self.debug:
                result.debug_info['raw_text_sample'] = full_text[:500]
                result.debug_info['text_analysis'] = self.text_analyzer.analyze_text_structure(full_text)

            # Detect form type
            form_type = self.config_loader.detect_form_type(full_text)
            if not form_type:
                result.errors.append("Could not detect form type")
                return result

            result.form_type = form_type
            config = self.config_loader.get_config(form_type)

            # Extract form fields
            result.extracted_data = self._extract_form_data(doc, config, full_text, result)

            doc.close()

        except Exception as e:
            result.errors.append(f"Error processing PDF: {str(e)}")
            logger.error(f"Error processing {file_path}: {e}")

        result.processing_time = time.time() - start_time
        return result

    def _extract_form_data(self, doc: fitz.Document, config: Dict, full_text: str, result: ExtractionResult) -> Dict[
        str, Any]:
        """Extract form data using advanced analysis"""
        extracted_data = {}

        # Get field definitions
        fields = config.get('data_elements', {}).get('fields', [])
        checkboxes = config.get('data_elements', {}).get('checkboxes', [])

        if self.debug:
            result.debug_info['extraction_attempts'] = {}

        # Extract text fields using context-aware approach
        for field_config in fields:
            field_name = field_config['name']
            field_label = field_config['label']

            # Get field context for better extraction
            context = self.text_analyzer.extract_field_context(full_text, field_label)

            value = self._extract_field_with_context(full_text, field_label, field_name, context)

            if self.debug:
                result.debug_info['extraction_attempts'][field_name] = {
                    'context': context,
                    'extracted_value': value
                }

            if value:
                extracted_data[field_name] = value

        # Extract checkboxes
        checkbox_data = self._extract_checkboxes_advanced(doc, full_text, checkboxes)
        extracted_data.update(checkbox_data)

        return extracted_data

    def _extract_field_with_context(self, text: str, label: str, field_name: str, context: Dict) -> Optional[str]:
        """Extract field value using contextual information"""

        # First, try values found in context analysis
        for source, potential_value in context.get('potential_values', []):
            if self._is_valid_field_value(potential_value, field_name):
                logger.debug(f"Extracted {field_name}: '{potential_value}' from {source}")
                return potential_value

        # Fallback to pattern matching on the full text
        return self._extract_with_patterns(text, label, field_name)

    def _extract_with_patterns(self, text: str, label: str, field_name: str) -> Optional[str]:
        """Extract using pattern matching as fallback"""
        label_clean = label.rstrip(':').strip()
        label_escaped = re.escape(label_clean)

        # Build field-specific patterns
        patterns = self._build_extraction_patterns(label_escaped, field_name)

        # Try each pattern
        for i, pattern in enumerate(patterns):
            matches = re.finditer(pattern, text, re.IGNORECASE | re.MULTILINE | re.DOTALL)
            for match in matches:
                if match.lastindex and match.lastindex >= 1:
                    value = match.group(1).strip()
                    if self._is_valid_field_value(value, field_name):
                        logger.debug(f"Extracted {field_name}: '{value}' using pattern {i + 1}")
                        return value

        return None

    def _build_extraction_patterns(self, label_escaped: str, field_name: str) -> List[str]:
        """Build field-specific extraction patterns"""
        patterns = []

        # Field-specific patterns based on expected data type
        if 'name' in field_name.lower() or 'surname' in field_name.lower() or 'forename' in field_name.lower():
            # Names: Look for capitalized words after label
            patterns.extend([
                rf'{label_escaped}[:\s]*([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)',
                rf'{label_escaped}[:\s]*\w*\s*([A-Z][a-z]+)',
            ])

        elif 'date' in field_name.lower() or 'birth' in field_name.lower():
            # Dates: Look for DD/MM/YYYY format
            patterns.extend([
                rf'{label_escaped}[:\s]*(\d{{1,2}}/\d{{1,2}}/\d{{4}})',
                rf'{label_escaped}[:\s]*\w*\s*(\d{{1,2}}/\d{{1,2}}/\d{{4}})',
            ])

        elif 'id' in field_name.lower() or 'number' in field_name.lower() or 'no' in field_name.lower() or 'passport' in field_name.lower():
            # Numbers/IDs: Look for digit sequences
            patterns.extend([
                rf'{label_escaped}[:\s]*(\d+)',
                rf'{label_escaped}[:\s]*\w*\s*(\d+)',
            ])

        elif 'email' in field_name.lower() or 'e-mail' in field_name.lower():
            # Emails
            patterns.extend([
                rf'{label_escaped}[:\s]*([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{{2,}})',
            ])

        elif 'income' in field_name.lower() or 'amount' in field_name.lower():
            # Money amounts
            patterns.extend([
                rf'{label_escaped}[:\s]*\$?\s*(\d{{1,3}}(?:,\d{{3}})*(?:\.\d{{2}})?)',
                rf'{label_escaped}[:\s]*\w*\s*(\d+)',
            ])

        elif 'dependant' in field_name.lower():
            # Small numbers for dependants
            patterns.extend([
                rf'{label_escaped}[:\s]*(\d+)',
                rf'{label_escaped}[:\s]*\w*\s*(\d)',
            ])

        elif 'education' in field_name.lower() or 'level' in field_name.lower():
            # Education levels
            patterns.extend([
                rf'{label_escaped}[:\s]*(Degree|Diploma|Certificate|Masters|PhD)',
                rf'{label_escaped}[:\s]*\w*\s*(Degree|Diploma|Certificate)',
            ])

        elif 'nationality' in field_name.lower():
            # Nationality
            patterns.extend([
                rf'{label_escaped}[:\s]*([A-Z][a-z]+)',
                rf'{label_escaped}[:\s]*\w*\s*([A-Z][a-z]+)',
            ])

        # General patterns as fallback
        patterns.extend([
            rf'{label_escaped}[:\s]*([^\n\r_]+?)(?:\s+[A-Z][a-z]+[:\s]|\s*_{{3,}}|\n)',
            rf'{label_escaped}[:\s]*([A-Za-z0-9@.,/\-\s]+?)(?:\s{{3,}}|\n|$)',
        ])

        return patterns

    def _is_valid_field_value(self, value: str, field_name: str) -> bool:
        """Enhanced validation for extracted values"""
        if not value or len(value.strip()) < 1:
            return False

        value = value.strip()

        # Filter out form artifacts and placeholders
        invalid_patterns = [
            r'^[_.\-\s]+$',  # Only punctuation/spaces
            r'^\.{3,}',  # Starts with dots
            r'^_{3,}',  # Starts with underscores
            r'specify\s*\)$',  # Form instructions
            r'maximum\s+\d+',  # Form instructions
            r'state\s+in\s+years',  # Form instructions
            r'degree\s*,?\s*diploma',  # Form label text
        ]

        for pattern in invalid_patterns:
            if re.search(pattern, value, re.IGNORECASE):
                return False

        # Field-specific validation
        if 'date' in field_name.lower() or 'birth' in field_name.lower():
            return bool(re.match(r'^\d{1,2}/\d{1,2}/\d{4}$', value))

        elif 'email' in field_name.lower():
            return bool(re.match(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$', value))

        elif 'id' in field_name.lower() or 'passport' in field_name.lower():
            return bool(re.match(r'^\d+$', value)) and len(value) >= 4

        elif 'dependant' in field_name.lower():
            return bool(re.match(r'^\d+$', value)) and int(value) <= 20

        elif 'name' in field_name.lower() or 'surname' in field_name.lower() or 'forename' in field_name.lower():
            return bool(re.match(r'^[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*$', value))

        elif 'nationality' in field_name.lower():
            return bool(re.match(r'^[A-Z][a-z]+$', value))

        elif 'education' in field_name.lower():
            return value.lower() in ['degree', 'diploma', 'certificate', 'masters', 'phd']

        # General validation
        return len(value) >= 2 and bool(re.search(r'[a-zA-Z0-9]', value))

    def _extract_checkboxes_advanced(self, doc: fitz.Document, text: str, checkbox_configs: List[Dict]) -> Dict[
        str, bool]:
        """Advanced checkbox extraction using multiple methods"""
        checkbox_data = {}

        # Initialize all checkboxes as unchecked
        for checkbox_config in checkbox_configs:
            checkbox_name = checkbox_config['name']
            checkbox_data[checkbox_name] = False

        try:
            # Method 1: Look for form fields
            for page_num in range(len(doc)):
                page = doc.load_page(page_num)
                widgets = page.widgets()
                for widget in widgets:
                    if widget.field_type == fitz.PDF_WIDGET_TYPE_CHECKBOX:
                        field_name = widget.field_name or ""
                        field_value = widget.field_value

                        # Match to our checkboxes
                        for checkbox_config in checkbox_configs:
                            checkbox_name = checkbox_config['name']
                            if checkbox_name.lower() in field_name.lower():
                                checkbox_data[checkbox_name] = bool(field_value)

            # Method 2: Text analysis for checked boxes
            for checkbox_config in checkbox_configs:
                checkbox_name = checkbox_config['name']
                label = checkbox_config.get('label', checkbox_name)

                if self._detect_checked_box_in_text(text, label):
                    checkbox_data[checkbox_name] = True

        except Exception as e:
            logger.warning(f"Error in checkbox extraction: {e}")

        return checkbox_data

    def _detect_checked_box_in_text(self, text: str, label: str) -> bool:
        """Detect if a checkbox is checked based on text patterns"""
        checked_patterns = [
            rf'{re.escape(label)}\s*[xX✓√☑✔]',  # Label followed by check mark
            rf'[xX✓√☑✔]\s*{re.escape(label)}',  # Check mark before label
            rf'{re.escape(label)}\s*\[\s*[xX✓√☑✔]\s*\]',  # Checked box notation
        ]

        return any(re.search(pattern, text, re.IGNORECASE) for pattern in checked_patterns)


class DataProcessor:
    """Processes and exports extracted data"""

    def __init__(self, output_dir: str = "output"):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(exist_ok=True)

    def process_results(self, results: List[ExtractionResult]) -> pd.DataFrame:
        """Process multiple extraction results into a DataFrame"""
        all_data = []

        for result in results:
            row_data = {
                'file_path': result.file_path,
                'form_type': result.form_type,
                'processing_time': result.processing_time,
                'error_count': len(result.errors)
            }

            # Add extracted data
            row_data.update(result.extracted_data)
            all_data.append(row_data)

        return pd.DataFrame(all_data)

    def export_to_csv(self, df: pd.DataFrame, filename: str = "extracted_data.csv"):
        """Export DataFrame to CSV file"""
        output_path = self.output_dir / filename
        df.to_csv(output_path, index=False)
        logger.info(f"Data exported to {output_path}")
        return output_path

    def export_debug_info(self, results: List[ExtractionResult], filename: str = "debug_info.txt"):
        """Export debug information to text file"""
        output_path = self.output_dir / filename

        with open(output_path, 'w', encoding='utf-8') as f:
            for result in results:
                f.write(f"File: {result.file_path}\n")
                f.write(f"Form Type: {result.form_type}\n")
                f.write("=" * 50 + "\n")

                if 'debug_info' in result.__dict__ and result.debug_info:
                    for key, value in result.debug_info.items():
                        f.write(f"\n{key.upper()}:\n")
                        if isinstance(value, dict):
                            for sub_key, sub_value in value.items():
                                f.write(f"  {sub_key}: {sub_value}\n")
                        else:
                            f.write(f"  {value}\n")

                f.write("\n" + "=" * 50 + "\n\n")

        logger.info(f"Debug info exported to {output_path}")
        return output_path

    def print_summary(self, results: List[ExtractionResult]):
        """Print extraction summary to console"""
        print("\n" + "=" * 60)
        print("PDF FORM DATA EXTRACTION SUMMARY")
        print("=" * 60)

        for i, result in enumerate(results, 1):
            print(f"\nFile {i}: {Path(result.file_path).name}")
            print(f"Form Type: {result.form_type}")
            print(f"Processing Time: {result.processing_time:.2f}s")

            if result.errors:
                print(f"Errors: {len(result.errors)}")
                for error in result.errors:
                    print(f"  - {error}")

            print("Extracted Data:")
            if result.extracted_data:
                for key, value in result.extracted_data.items():
                    print(f"  {key}: {value}")
            else:
                print("  No data extracted")

            print("-" * 40)


def create_enhanced_config():
    """Create enhanced configuration file"""
    config_dir = Path("configs")
    config_dir.mkdir(exist_ok=True)

    config_file = config_dir / "personal_loan_form.yml"

    enhanced_config = {
        'form_type': 'PERSONAL_LOAN_V1',
        'identification_string': 'Personal Loan Application Form',
        'data_elements': {
            'fields': [
                {'name': 'Surname', 'label': 'Surname:', 'required': True, 'field_type': 'name'},
                {'name': 'Forename(s)', 'label': 'Forename(s):', 'required': True, 'field_type': 'name'},
                {'name': 'Date of Birth', 'label': 'Date of Birth:', 'field_type': 'date'},
                {'name': 'I.D Card No.', 'label': 'I.D Card No.:', 'field_type': 'id'},
                {'name': 'Passport No.', 'label': 'Passport No.:', 'field_type': 'id'},
                {'name': 'Level of Education (Degree, Diploma,)', 'label': 'Level of Education (Degree, Diploma,)',
                 'field_type': 'education'},
                {'name': 'No of Dependants', 'label': 'No of Dependants:', 'field_type': 'number'},
                {'name': 'Nationality', 'label': 'Nationality:', 'field_type': 'nationality'},
                {'name': 'Residential Address', 'label': 'Residential Address:', 'field_type': 'text'},
                {'name': 'Period of residence (State in years)', 'label': 'Period of residence (State in years)',
                 'field_type': 'number'},
                {'name': 'Tel', 'label': 'Tel:', 'field_type': 'phone'},
                {'name': 'Cell', 'label': 'Cell:', 'field_type': 'phone'},
                {'name': 'e-mail', 'label': 'e-mail', 'field_type': 'email'},
                {'name': 'Occupation', 'label': 'Occupation:', 'field_type': 'text'},
                {'name': 'Gross monthly income $', 'label': 'Gross monthly income $', 'field_type': 'money'},
                {'name': 'Net monthly income $', 'label': 'Net monthly income $', 'field_type': 'money'},
                {'name': 'Loan Amount Required', 'label': '(Specify) $', 'field_type': 'money'},
                {'name': 'Term preferred', 'label': 'Term preferred:', 'field_type': 'text'},
                {'name': 'Loan Purpose', 'label': 'Loan Purpose:', 'field_type': 'text'}
            ],
            'checkboxes': [
                {'name': 'Mr', 'label': 'Mr'},
                {'name': 'Mrs', 'label': 'Mrs'},
                {'name': 'Miss', 'label': 'Miss'},
                {'name': 'Ms', 'label': 'Ms'},
                {'name': 'Male', 'label': 'Male'},
                {'name': 'Female', 'label': 'Female'},
                {'name': 'Married', 'label': 'Married'},
                {'name': 'Single', 'label': 'Single'}
            ]
        }
    }

    with open(config_file, 'w', encoding='utf-8') as f:
        yaml.dump(enhanced_config, f, default_flow_style=False, sort_keys=False)

    logger.info(f"Created enhanced config at {config_file}")


def main():
    """Main application entry point"""
    print("PDF Form Data Extractor v2.0")
    print("-" * 30)

    # Enable debug mode
    debug_mode = True

    # Setup directories and config
    forms_dir = Path("Filled Forms")
    if not forms_dir.exists():
        print(f"Error: {forms_dir} directory not found!")
        sys.exit(1)

    # Create enhanced config
    create_enhanced_config()

    # Initialize components
    config_loader = FormConfigLoader()
    extractor = PDFDataExtractor(config_loader, debug=debug_mode)
    processor = DataProcessor()

    # Find PDF files
    pdf_files = list(forms_dir.glob("*.pdf"))
    if not pdf_files:
        print(f"No PDF files found in {forms_dir}")
        sys.exit(1)

    print(f"Found {len(pdf_files)} PDF file(s) to process")

    # Process all PDF files
    results = []
    for pdf_file in pdf_files:
        print(f"Processing: {pdf_file.name}")
        result = extractor.extract_from_file(str(pdf_file))
        results.append(result)

    # Process and export results
    df = processor.process_results(results)
    csv_path = processor.export_to_csv(df)

    # Export debug info if in debug mode
    if debug_mode:
        debug_path = processor.export_debug_info(results)
        print(f"Debug info saved to: {debug_path}")

    # Print summary
    processor.print_summary(results)

    print(f"\nResults saved to: {csv_path}")
    print("Processing complete!")


if __name__ == "__main__":
    main()
