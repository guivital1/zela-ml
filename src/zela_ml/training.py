import hashlib
import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import sklearn
from matplotlib.figure import Figure
from sklearn.dummy import DummyClassifier
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    ConfusionMatrixDisplay,
    accuracy_score,
    classification_report,
    f1_score,
    log_loss,
)
from sklearn.pipeline import FeatureUnion, Pipeline

from zela_ml import __version__
from zela_ml.dataset import dataset_hash, load_dataset
from zela_ml.keywords import keywords_prediction
from zela_ml.settings import ARTIFACTS, CATEGORIES, DATA, REPORTS, SEED


def candidates() -> dict[str, Pipeline]:
    def words() -> TfidfVectorizer:
        return TfidfVectorizer(
            strip_accents="unicode", ngram_range=(1, 2), sublinear_tf=True, max_df=0.97
        )

    return {
        "referencia_frequencia": Pipeline(
            [
                ("features", words()),
                ("classifier", DummyClassifier(strategy="prior")),
            ]
        ),
        "tfidf_palavras_c2": Pipeline(
            [
                ("features", words()),
                ("classifier", LogisticRegression(C=2, max_iter=1000, random_state=SEED)),
            ]
        ),
        "tfidf_palavras_c6": Pipeline(
            [
                ("features", words()),
                ("classifier", LogisticRegression(C=6, max_iter=1000, random_state=SEED)),
            ]
        ),
        "tfidf_palavras_caracteres": Pipeline(
            [
                (
                    "features",
                    FeatureUnion(
                        [
                            ("palavras", words()),
                            (
                                "caracteres",
                                TfidfVectorizer(
                                    analyzer="char_wb",
                                    strip_accents="unicode",
                                    ngram_range=(3, 5),
                                    sublinear_tf=True,
                                    max_features=25000,
                                ),
                            ),
                        ],
                        transformer_weights={"palavras": 1.0, "caracteres": 0.65},
                    ),
                ),
                ("classifier", LogisticRegression(C=4, max_iter=1000, random_state=SEED)),
            ]
        ),
    }


def scores(model: Pipeline, frame: pd.DataFrame) -> dict:
    predicted = model.predict(frame["text"])
    probabilities = model.predict_proba(frame["text"])
    per_scenario = frame.assign(correct=predicted == frame["category"])
    return {
        "accuracy": float(accuracy_score(frame["category"], predicted)),
        "f1_macro": float(f1_score(frame["category"], predicted, average="macro")),
        "log_loss": float(log_loss(frame["category"], probabilities, labels=model.classes_)),
        "scenario_all_variants_correct": float(
            per_scenario.groupby("scenario")["correct"].all().mean()
        ),
    }


def acceptance(probabilities: np.ndarray, threshold: float, margin: float) -> np.ndarray:
    ordered = np.sort(probabilities, axis=1)
    return (ordered[:, -1] >= threshold) & ((ordered[:, -1] - ordered[:, -2]) >= margin)


def select_review_policy(model: Pipeline, validation: pd.DataFrame, probes: pd.DataFrame):
    """Escolhe limites usando apenas a validação e os casos de revisão reservados."""
    texts = [*validation["text"], *probes["text"]]
    expected = np.array([*validation["category"], *probes["expected"]])
    probabilities = model.predict_proba(texts)
    predicted = model.classes_[probabilities.argmax(axis=1)]
    in_scope = expected != "revisao"
    rows = []
    for threshold in np.arange(0.40, 0.96, 0.05):
        for margin in (0.10, 0.20, 0.30, 0.40):
            accepted = acceptance(probabilities, threshold, margin)
            count = int(accepted.sum())
            rows.append(
                {
                    "threshold": round(float(threshold), 2),
                    "margin": margin,
                    "precision_accepted": float((predicted[accepted] == expected[accepted]).mean())
                    if count
                    else 0.0,
                    "coverage_in_scope": float(accepted[in_scope].mean()),
                    "probes_accepted": int(accepted[~in_scope].sum()),
                }
            )
    options = pd.DataFrame(rows)
    eligible = options[
        (options["precision_accepted"] >= 0.95) & (options["probes_accepted"] == 0)
    ].sort_values(
        ["coverage_in_scope", "precision_accepted", "threshold", "margin"],
        ascending=[False, False, False, False],
    )
    if eligible.empty:
        policy = {"threshold": 1.01, "margin": 1.0}
    else:
        policy = eligible.iloc[0][["threshold", "margin"]].to_dict()
    return policy, options


def review_scores(model: Pipeline, frame: pd.DataFrame, policy: dict) -> dict:
    probabilities = model.predict_proba(frame["text"])
    predicted = model.classes_[probabilities.argmax(axis=1)]
    accepted = acceptance(probabilities, **policy)
    return {
        "coverage": float(accepted.mean()),
        "accepted_count": int(accepted.sum()),
        "precision_accepted": float(
            (predicted[accepted] == frame["category"].to_numpy()[accepted]).mean()
        )
        if accepted.any()
        else None,
        "review_count": int((~accepted).sum()),
    }


def scenario_interval(test: pd.DataFrame, predicted: np.ndarray) -> dict:
    """Bootstrap por cenário para respeitar a correlação entre suas variações."""
    groups = test["scenario"].unique()
    group_indices = [np.flatnonzero(test["scenario"].to_numpy() == group) for group in groups]
    expected = test["category"].to_numpy()
    rng = np.random.default_rng(SEED)
    estimates = []
    for _ in range(1000):
        sampled = rng.integers(0, len(groups), size=len(groups))
        indices = np.concatenate([group_indices[index] for index in sampled])
        estimates.append(
            f1_score(
                expected[indices],
                predicted[indices],
                labels=list(CATEGORIES),
                average="macro",
                zero_division=0,
            )
        )
    low, high = np.quantile(estimates, [0.025, 0.975])
    return {
        "low": float(low),
        "high": float(high),
        "resamples": 1000,
        "unit": "scenario",
        "scope": "incerteza dentro da base sintética",
    }


def write_json(path: Path, value: dict) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def keyword_comparison(model: Pipeline, test: pd.DataFrame) -> dict:
    predicted = test["text"].map(keywords_prediction)
    covered = predicted != "revisao"
    robustness = pd.read_csv(DATA / "robustez.csv")
    robustness["modelo"] = model.predict(robustness["texto"])
    robustness["regra"] = robustness["texto"].map(keywords_prediction)
    robustness["acerto_modelo"] = robustness["modelo"] == robustness["categoria"]
    robustness["acerto_regra"] = robustness["regra"] == robustness["categoria"]
    robustness.to_csv(REPORTS / "comparacao_robustez.csv", index=False)
    by_type = robustness.groupby("tipo", sort=False)
    summary = by_type.agg(
        relatos=("texto", "size"),
        acertos_modelo=("acerto_modelo", "sum"),
        acertos_regra=("acerto_regra", "sum"),
    )
    return {
        "f1_macro": float(
            f1_score(
                test["category"],
                predicted,
                labels=list(CATEGORIES),
                average="macro",
                zero_division=0,
            )
        ),
        "accuracy": float(accuracy_score(test["category"], predicted)),
        "covered": int(covered.sum()),
        "review_count": int((~covered).sum()),
        "robustez_sintetica": summary.to_dict(orient="index"),
    }


def train() -> dict:
    frame = load_dataset()
    train_set = frame[frame["split"] == "train"]
    validation = frame[frame["split"] == "validation"]
    test = frame[frame["split"] == "test"]
    probes = pd.read_csv(DATA / "probes.csv")
    ARTIFACTS.mkdir(exist_ok=True)
    REPORTS.mkdir(exist_ok=True)
    fitted = candidates()
    comparison = []
    for name, model in fitted.items():
        model.fit(train_set["text"], train_set["category"])
        comparison.append({"model": name, **scores(model, validation)})
    ranking = pd.DataFrame(comparison).sort_values(
        ["f1_macro", "log_loss"], ascending=[False, True]
    )
    ranking.to_csv(REPORTS / "validation_models.csv", index=False)
    best_name = ranking.iloc[0]["model"]
    model = fitted[best_name]
    policy, options = select_review_policy(
        model, validation, probes[probes["split"] == "validation"]
    )
    options.to_csv(REPORTS / "review_policy_validation.csv", index=False)

    # O teste só é consultado depois de fixar o modelo e os limites de revisão.
    predicted = model.predict(test["text"])
    test_probes = probes[probes["split"] == "test"].copy()
    probe_probabilities = model.predict_proba(test_probes["text"])
    test_probes["suggested"] = model.classes_[probe_probabilities.argmax(axis=1)]
    test_probes["score"] = probe_probabilities.max(axis=1)
    test_probes["requires_review"] = ~acceptance(probe_probabilities, **policy)
    test_probes.to_csv(REPORTS / "challenge_predictions.csv", index=False)
    predictions = test.assign(
        predicted=predicted,
        correct=predicted == test["category"],
        score=model.predict_proba(test["text"]).max(axis=1),
    )
    predictions.to_csv(REPORTS / "test_predictions.csv", index=False)
    predictions[~predictions["correct"]].to_csv(REPORTS / "errors.csv", index=False)
    labels = list(model.classes_)
    report = classification_report(
        test["category"],
        predicted,
        labels=labels,
        target_names=[CATEGORIES[label] for label in labels],
        output_dict=True,
        zero_division=0,
    )
    write_json(REPORTS / "classification_report.json", report)
    fig = Figure(figsize=(10, 7))
    ax = fig.subplots()
    ConfusionMatrixDisplay.from_predictions(
        test["category"],
        predicted,
        labels=labels,
        display_labels=[CATEGORIES[label] for label in labels],
        cmap="Blues",
        colorbar=False,
        ax=ax,
        xticks_rotation=32,
    )
    ax.set(
        xlabel="Categoria sugerida",
        ylabel="Categoria esperada",
        title="Teste sintético · cenários separados do treino",
    )
    fig.tight_layout()
    fig.savefig(REPORTS / "confusion_matrix.png", dpi=160)

    metrics = {
        "version": __version__,
        "seed": SEED,
        "dataset_source": "simulado",
        "dataset_sha256": dataset_hash(),
        "rows": len(frame),
        "scenarios": int(frame["scenario"].nunique()),
        "split_rows": frame["split"].value_counts().to_dict(),
        "split_scenarios": frame.groupby("split")["scenario"].nunique().to_dict(),
        "selected_model": best_name,
        "selection_metric": "f1_macro de validação, desempate por log_loss",
        "validation": scores(model, validation),
        "test": scores(model, test),
        "test_f1_macro_ci95": scenario_interval(test, predicted),
        "baseline_test": scores(fitted["referencia_frequencia"], test),
        "keywords_test": keyword_comparison(model, test),
        "review_policy": policy,
        "test_selective": review_scores(model, test, policy),
        "challenge_test": {
            "total": len(test_probes),
            "sent_to_review": int(test_probes["requires_review"].sum()),
            "accepted_incorrectly": int((~test_probes["requires_review"]).sum()),
        },
        "limitations": [
            "Base sintética de 180 cenários; variações do mesmo cenário são correlacionadas.",
            "Vocabulário e estilos de escrita compartilham um catálogo controlado.",
            "Métricas estimam desempenho nesta simulação; validação de campo permanece pendente.",
            "Pontuações do modelo exigem validação em dados reais antes de uso operacional.",
            "Relatos com vários serviços, negação ou contexto privado podem ser mal classificados.",
            "O responsável revisa o pedido antes de encaminhá-lo ao órgão público.",
        ],
    }
    write_json(REPORTS / "metrics.json", metrics)
    bundle = {"model": model, "policy": policy, "metrics": metrics, "categories": CATEGORIES}
    artifact_path = ARTIFACTS / "model.joblib"
    temporary_path = ARTIFACTS / "model.joblib.tmp"
    joblib.dump(bundle, temporary_path, compress=3)
    temporary_path.replace(artifact_path)
    write_json(
        ARTIFACTS / "manifest.json",
        {
            "version": __version__,
            "sklearn_version": sklearn.__version__,
            "dataset_sha256": dataset_hash(),
            "model_sha256": hashlib.sha256(artifact_path.read_bytes()).hexdigest(),
            "probes_sha256": hashlib.sha256((DATA / "probes.csv").read_bytes()).hexdigest(),
            "model": best_name,
        },
    )
    return metrics
