import base64
from io import BytesIO
from secrets import token_urlsafe
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from zela_ml.api import create_app
from zela_ml.zeladoria import Occurrences


@pytest.fixture
def app(tmp_path):
    password = token_urlsafe(16)
    path = tmp_path / "test.sqlite3"
    return create_app(database_path=path, team_password=password), password


def report(**changes):
    return {
        "pedido": str(uuid4()),
        "descricao": "O poste perto do ponto de ônibus não acende à noite.",
        "local": "Rua das Acácias, 72",
        **changes,
    }


def create(client, payload=None):
    response = client.post("/api/ocorrencias", json=payload or report())
    assert response.status_code == 201
    return response.json()


@pytest.mark.parametrize(
    "url",
    [
        "/equipe/tecnica",
        "/model",
        "/docs",
        "/openapi.json",
        "/equipe/notebook",
        "/evaluation/confusion-matrix.png",
    ],
)
def test_direct_technical_links_require_a_session(app, url):
    web, password = app
    with TestClient(web) as client:
        assert client.get(url).status_code == 401
        assert client.post("/api/equipe/entrar", json={"senha": password}).status_code == 200
        assert client.get(url).status_code == 200
        client.post("/api/equipe/sair")
        assert client.get(url).status_code == 401


def test_report_is_idempotent_and_duplicate_location_can_be_reviewed(app):
    web, _ = app
    with TestClient(web) as client:
        payload = report()
        item = create(client, payload)
        assert create(client, payload)["id"] == item["id"]
        assert item["estado"] == "registrada"
        assert item["confirmacoes"] == 1
        assert "sugestao" not in item
        duplicate = report(local="RUA DAS ACACIAS, 72")
        response = client.post("/api/ocorrencias", json=duplicate)
        assert response.status_code == 409
        assert response.json()["detail"]["ocorrencias"][0]["id"] == item["id"]
        other = create(client, {**duplicate, "outro_problema": True})
        assert other["id"] != item["id"]


def test_confirmations_are_idempotent_and_appear_in_tracking(app):
    web, _ = app
    with TestClient(web) as creator:
        item = create(creator)
        with TestClient(web) as neighbor:
            assert neighbor.get("/api/ocorrencias?minhas=true").json()["ocorrencias"] == []
            for _ in range(2):
                response = neighbor.post(f"/api/ocorrencias/{item['id']}/confirmar")
                assert response.json()["confirmacoes"] == 2
            tracked = neighbor.get("/api/ocorrencias?minhas=true").json()["ocorrencias"]
            assert [occurrence["id"] for occurrence in tracked] == [item["id"]]


def test_team_records_protocol_and_resolution_and_public_can_track(app):
    web, password = app
    with TestClient(web) as client:
        item = create(client)
        target = f"/api/equipe/ocorrencias/{item['id']}"
        forwarded = {
            "estado_anterior": "registrada",
            "estado": "encaminhada",
            "categoria": "iluminacao",
            "protocolo": "EXEMPLO-123",
        }
        assert client.patch(target, json=forwarded).status_code == 401
        assert (
            client.post("/api/equipe/entrar", json={"senha": "senha-incorreta"}).status_code == 401
        )
        assert client.post("/api/equipe/entrar", json={"senha": password}).status_code == 200
        assert client.patch(target, json={**forwarded, "protocolo": None}).status_code == 409
        assert client.patch(target, json=forwarded).json()["protocolo"] == "EXEMPLO-123"
        assert client.patch(target, json=forwarded).status_code == 409
        closed = client.patch(
            target,
            json={
                "estado_anterior": "encaminhada",
                "estado": "resolvida",
                "categoria": "iluminacao",
                "nota": "Luminária trocada.",
            },
        )
        assert closed.status_code == 200
        assert client.post("/api/equipe/sair").status_code == 200
        public = client.get(f"/api/ocorrencias/{item['id']}").json()
        assert public["estado"] == "resolvida"
        assert public["protocolo"] == "EXEMPLO-123"
        assert public["historico"][-1]["nota"] == "Luminária trocada."
        assert "sugestao" not in public


def test_report_and_photo_survive_restart_and_backup(app, tmp_path):
    web, _ = app
    image = BytesIO()
    Image.new("RGB", (40, 40), "#19a99a").save(image, "PNG")
    encoded = base64.b64encode(image.getvalue()).decode()
    with TestClient(web) as client:
        item = create(client, report(foto=encoded))
        assert item["tem_foto"]
        path = web.state.occurrences.path
        backup = tmp_path / "copia.sqlite3"
        Occurrences(path).backup(backup)
        assert client.post("/api/ocorrencias", json=report(foto="inválida")).status_code == 422
    for db in (path, backup):
        with TestClient(create_app(database_path=db)) as client:
            detail = client.get(f"/api/ocorrencias/{item['id']}")
            assert detail.json()["descricao"] == item["descricao"]
            photo = client.get(f"/api/ocorrencias/{item['id']}/foto")
            assert photo.headers["content-type"] == "image/jpeg"
            with Image.open(BytesIO(photo.content)) as picture:
                assert not picture.getexif()


def test_public_intake_stays_available_without_a_classifier(tmp_path):
    web = create_app(artifact_dir=tmp_path / "empty", database_path=tmp_path / "test.sqlite3")
    with TestClient(web) as client:
        assert create(client, report(categoria="outros"))["tipo"] == "Outros serviços"
        assert (
            client.post(
                "/api/ocorrencias", json=report(), headers={"Origin": "https://external.invalid"}
            ).status_code
            == 403
        )


def test_public_home_contains_only_product_navigation(app):
    web, _ = app
    with TestClient(web) as client:
        html = client.get("/").text
        assert "Novo relato" in html
        assert "Matriz de confusão" not in html
        assert 'href="/docs"' not in html
        assert client.post("/classify", json={"text": report()["descricao"]}).status_code == 401
