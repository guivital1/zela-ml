import hashlib
import json
import re
from io import BytesIO
from pathlib import Path

import joblib
import numpy as np

from zela_ml.settings import ARTIFACTS


class Classifier:
    def __init__(self, artifact_dir: Path = ARTIFACTS):
        manifest = json.loads((artifact_dir / "manifest.json").read_text(encoding="utf-8"))
        model_path = artifact_dir / "model.joblib"
        model_bytes = model_path.read_bytes()
        digest = hashlib.sha256(model_bytes).hexdigest()
        if digest != manifest["model_sha256"]:
            raise ValueError("O artefato diverge do manifesto. Execute o treino novamente.")
        bundle = joblib.load(BytesIO(model_bytes))
        self.model = bundle["model"]
        self.policy = bundle["policy"]
        self.metrics = bundle["metrics"]
        self.categories = bundle["categories"]
        self.version = manifest["version"]

    def predict(self, text: str) -> dict:
        text = re.sub(r"\s+", " ", text).strip()
        if len(text) < 12 or len(text) > 2000 or sum(c.isalpha() for c in text) < 8:
            raise ValueError("Descreva o problema com 12 a 2.000 caracteres e ao menos 8 letras.")
        probabilities = self.model.predict_proba([text])[0]
        ranking = np.argsort(probabilities)[::-1]
        top, second = ranking[:2]
        category = str(self.model.classes_[top])
        score = float(probabilities[top])
        margin = float(probabilities[top] - probabilities[second])
        review_reasons = []
        if score < self.policy["threshold"]:
            review_reasons.append("A pontuação ficou abaixo do limite escolhido na validação.")
        if margin < self.policy["margin"]:
            review_reasons.append("Há proximidade entre as duas primeiras sugestões.")
        return {
            "category": category,
            "label": self.categories[category],
            "score": round(score, 4),
            "margin": round(margin, 4),
            "requires_review": bool(review_reasons),
            "review_reasons": review_reasons,
            "suggestions": [
                {
                    "category": str(self.model.classes_[i]),
                    "label": self.categories[str(self.model.classes_[i])],
                    "score": round(float(probabilities[i]), 4),
                }
                for i in ranking[:3]
            ],
            "evidence_terms": self.evidence(text, int(top)),
            "model_version": self.version,
            "dataset_source": "simulado",
        }

    def evidence(self, text: str, category_index: int) -> list[dict]:
        features = self.model.named_steps["features"]
        vector = features.transform([text]).tocoo()
        names = features.get_feature_names_out()
        weights = self.model.named_steps["classifier"].coef_[category_index]
        contributions = sorted(
            ((int(i), float(value * weights[i])) for i, value in zip(vector.col, vector.data)),
            key=lambda entry: entry[1],
            reverse=True,
        )
        terms = []
        for index, contribution in contributions:
            name = str(names[index])
            if name.startswith("caracteres__") or contribution <= 0:
                continue
            terms.append(
                {"term": name.removeprefix("palavras__"), "contribution": round(contribution, 4)}
            )
            if len(terms) == 5:
                break
        return terms
