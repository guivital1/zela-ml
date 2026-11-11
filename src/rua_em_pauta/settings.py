from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data"
ARTIFACTS = ROOT / "artifacts"
REPORTS = ROOT / "reports"
SEED = 42

CATEGORIES = {
    "iluminacao": "Iluminação pública",
    "limpeza": "Limpeza urbana",
    "pavimentacao": "Pavimentação",
    "drenagem": "Drenagem",
    "acessibilidade": "Acessibilidade",
    "areas_verdes": "Áreas verdes",
}
