import os
from pathlib import Path
from dataclasses import dataclass

@dataclass
class Config:
    dataset_root: Path
    output_dir: Path

    @classmethod
    def create(cls, dataset_path: str, output_path: str = None) -> "Config":
        root = Path(dataset_path).resolve()
        if output_path:
            out = Path(output_path).resolve()
        else:
            # Default to sekeron/outputs relative to the project root
            project_root = Path(__file__).resolve().parent.parent
            out = project_root / "outputs"
        
        return cls(dataset_root=root, output_dir=out)
