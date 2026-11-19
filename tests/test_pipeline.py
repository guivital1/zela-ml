import json
from secrets import token_urlsafe

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from zela_ml.api import create_app
from zela_ml.dataset import load_dataset, validate_dataset
from zela_ml.inference import Classifier
from zela_ml.settings import ARTIFACTS, CATEGORIES, REPORTS


@pytest.fixture(scope="module")
def classifier():
    return Classifier()


@pytest.fixture(scope="module")
def client(tmp_path_factory):
    password = token_urlsafe(16)
    path = tmp_path_factory.mktemp("pipeline") / "test.sqlite3"
    with TestClient(create_app(database_path=path, team_password=password)) as session:
        assert session.post("/api/equipe/entrar", json={"senha": password}).status_code == 200
        yield session


def test_split_rejects_same_scenario_in_training_and_test():
    frame = load_dataset()
    leaked = frame.iloc[[0]].copy()
    leaked["id"] = "leaked-row"
    leaked["split"] = "test"
    with pytest.raises(ValueError, match="Cenários compartilhados"):
        validate_dataset(pd.concat([frame, leaked], ignore_index=True))


def test_split_rejects_equivalent_text_from_another_scenario():
    frame = load_dataset()
    leaked = frame.iloc[[0]].copy()
    leaked["id"] = "leaked-text"
    leaked["scenario"] = "another-scenario"
    leaked["split"] = "test"
    leaked["text"] = leaked["text"].str.upper()
    with pytest.raises(ValueError, match="Textos equivalentes"):
        validate_dataset(pd.concat([frame, leaked], ignore_index=True))


@pytest.mark.parametrize("text", ["", "         ", "ajuda", "12345678901234", "a" * 2001])
def test_inference_rejects_unusable_descriptions(classifier, text):
    with pytest.raises(ValueError):
        classifier.predict(text)


def test_artifact_checksum_is_checked_before_loading(tmp_path):
    (tmp_path / "manifest.json").write_bytes((ARTIFACTS / "manifest.json").read_bytes())
    (tmp_path / "model.joblib").write_bytes(b"invalid model")
    with pytest.raises(ValueError, match="diverge do manifesto"):
        Classifier(tmp_path)


def test_prediction_contract_and_readable_evidence(classifier):
    result = classifier.predict("O poste da esquina não acende e a rua fica escura à noite.")
    assert result["category"] == "iluminacao"
    assert result["dataset_source"] == "simulado"
    assert len(result["suggestions"]) == 3
    assert all(item["category"] in CATEGORIES for item in result["suggestions"])
    scores = [item["score"] for item in result["suggestions"]]
    assert scores == sorted(scores, reverse=True)
    assert 0 < sum(scores) <= 1.0001
    assert all("__" not in term["term"] for term in result["evidence_terms"])


def test_out_of_scope_is_flagged_for_review(classifier):
    result = classifier.predict("Quero marcar uma consulta com o dentista na próxima semana.")
    assert result["requires_review"] is True
    assert result["review_reasons"]


def test_api_serves_model_and_demo(client):
    assert client.get("/health").json()["status"] == "ok"
    assert client.get("/").status_code == 200
    assert "ZELA · Zeladoria urbana" in client.get("/").text
    assert client.get("/assets/app.js").status_code == 200
    assert client.get("/assets/logo.jpg").status_code == 200
    assert client.get("/evaluation/confusion-matrix.png").headers["content-type"] == "image/png"
    assert len(client.get("/model").json()["categories"]) == 6
    assert (
        client.post("/classify", json={"text": "A boca de lobo está entupida."}).json()["category"]
        == "drenagem"
    )


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"text": 1234567890123},
        {"text": " " * 20},
        {"text": "1" * 50},
        {"text": "a" * 2001},
        {"text": "O poste está apagado.", "role": "admin"},
    ],
)
def test_api_rejects_invalid_payloads(client, payload):
    assert client.post("/classify", json=payload).status_code == 422


def test_saved_predictions_match_executable_artifact(classifier):
    predictions = pd.read_csv(REPORTS / "test_predictions.csv")
    actual = classifier.model.predict(predictions["text"])
    assert list(actual) == list(predictions["predicted"])
    metrics = json.loads((REPORTS / "metrics.json").read_text())
    assert metrics["rows"] == len(load_dataset())
    assert metrics["test"]["f1_macro"] > metrics["baseline_test"]["f1_macro"]
