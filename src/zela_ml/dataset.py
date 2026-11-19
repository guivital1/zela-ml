import hashlib
import json
import random
import unicodedata

import pandas as pd

from zela_ml.settings import CATEGORIES, DATA, SEED

PREFIXES = ("", "Bom dia. ", "Gostaria de registrar o seguinte problema. ", "No bairro, ")
SUFFIXES = (
    "",
    " Isso acontece há alguns dias.",
    " Fica no caminho de quem vai trabalhar.",
    " Outras pessoas também perceberam o problema.",
)


def normalize(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text.casefold())
    return " ".join("".join(c for c in decomposed if not unicodedata.combining(c)).split())


def build_dataset() -> pd.DataFrame:
    """Mantém todas as versões de um cenário na mesma partição."""
    scenarios = json.loads((DATA / "scenarios.json").read_text(encoding="utf-8"))
    rows = []
    for category, sentences in scenarios.items():
        indices = list(range(len(sentences)))
        random.Random(f"{SEED}-{category}").shuffle(indices)
        split_for = {
            index: "train" if position < 18 else "validation" if position < 24 else "test"
            for position, index in enumerate(indices)
        }
        for index, sentence in enumerate(sentences):
            group = f"{category}-{index + 1:02d}"
            variants = (
                sentence,
                normalize(sentence),
                PREFIXES[(index % 3) + 1] + sentence[0].lower() + sentence[1:],
                sentence + SUFFIXES[(index % 3) + 1],
                normalize(sentence)
                .replace("que ", "q ")
                .replace("não ", "nao ")
                .replace("precisamos", "precisamo")
                .replace("esta ", "ta "),
            )
            for variant, text in enumerate(dict.fromkeys(variants)):
                rows.append(
                    {
                        "id": f"{group}-{variant}",
                        "scenario": group,
                        "text": text,
                        "category": category,
                        "split": split_for[index],
                        "source": "simulado",
                    }
                )
    frame = pd.DataFrame(rows)
    validate_dataset(frame)
    frame.to_csv(DATA / "reports.csv", index=False)
    return frame


def validate_dataset(frame: pd.DataFrame) -> None:
    required = {"id", "scenario", "text", "category", "split", "source"}
    if not required.issubset(frame.columns):
        raise ValueError("Dataset sem todas as colunas obrigatórias.")
    if frame.empty or frame[list(required)].isna().any().any():
        raise ValueError("Dataset vazio ou com valores ausentes.")
    if set(frame["category"]) != set(CATEGORIES):
        raise ValueError("O dataset deve conter as seis categorias previstas.")
    if set(frame["split"]) != {"train", "validation", "test"}:
        raise ValueError("São necessárias as partições train, validation e test.")
    if frame["id"].duplicated().any():
        raise ValueError("IDs duplicados no dataset.")
    if frame.groupby("scenario")["split"].nunique().gt(1).any():
        raise ValueError("Cenários compartilhados entre partições.")
    if frame.groupby("scenario")["category"].nunique().gt(1).any():
        raise ValueError("Um cenário possui categorias conflitantes.")
    normalized = frame.assign(normalized=frame["text"].map(normalize))
    if normalized.groupby("normalized")["split"].nunique().gt(1).any():
        raise ValueError("Textos equivalentes compartilhados entre partições.")
    if frame.groupby("split")["category"].nunique().ne(len(CATEGORIES)).any():
        raise ValueError("Cada partição precisa representar as seis categorias.")


def load_dataset() -> pd.DataFrame:
    frame = pd.read_csv(DATA / "reports.csv", keep_default_na=False)
    validate_dataset(frame)
    return frame


def dataset_hash() -> str:
    return hashlib.sha256((DATA / "reports.csv").read_bytes()).hexdigest()
