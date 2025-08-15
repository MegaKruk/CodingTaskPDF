import os
from typing import Dict, Any
import yaml


class ConfigManager:
    """Manages loading and providing access to form extraction configurations."""
    def __init__(self, config_dir: str = "configs"):
        self.config_dir = config_dir
        self.configs = self._load_configs()
        print(f"Loaded {len(self.configs)} configurations from '{self.config_dir}'.")

    def _load_configs(self) -> Dict[str, Any]:
        """Loads all .yml or .yaml files from the config directory."""
        loaded_configs = {}
        if not os.path.exists(self.config_dir):
            os.makedirs(self.config_dir)
            print(f"Warning: Configuration directory '{self.config_dir}' not found. Created it.")
            return loaded_configs
        for filename in os.listdir(self.config_dir):
            if filename.endswith((".yml", ".yaml")):
                filepath = os.path.join(self.config_dir, filename)
                with open(filepath, 'r') as f:
                    try:
                        config_data = yaml.safe_load(f)
                        form_type = config_data.get("form_type")
                        if form_type:
                            loaded_configs[form_type] = config_data
                    except yaml.YAMLError as e:
                        print(f"Error loading YAML file {filename}: {e}")
        return loaded_configs

    def identify_form_type(self, pdf_document) -> str:
        """Identifies the form type by searching for unique strings."""
        page_text = pdf_document[0].get_text("text")
        for form_type, config in self.configs.items():
            id_string = config.get("identification_string")
            if id_string and id_string in page_text:
                return form_type
        return None
