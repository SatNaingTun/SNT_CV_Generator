import pandas as pd
import os

class UniversityValidator:
    def __init__(self, csv_path="world-universities.csv"):
        self.universities = []
        if os.path.exists(csv_path):
            df = pd.read_csv(csv_path, header=None)
            # Assuming column index 1 contains university names
            self.universities = df[1].dropna().astype(str).tolist()

    def normalize_institution(self, name: str) -> str:
        # Clean or return normalized name if needed
        return name.strip()

    def isValidatedUniversity(self, name: str) -> bool:
        if not name:
            return False
        name_lower = name.lower()
        for uni in self.universities:
            uni_lower = uni.lower()
            if uni_lower in name_lower or name_lower in uni_lower:
                return True
        return False