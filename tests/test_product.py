import base64
from io import BytesIO
from secrets import token_urlsafe
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from zela_ml.api import create_app
from zela_ml.zeladoria import SCHEMA, Occurrences


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
        "/api/equipe/avaliacao",
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


def test_structured_address_matches_abbreviations_and_respects_neighborhood(app):
    web, _ = app
    with TestClient(web) as client:
        address = {"local": None, "rua": "Rua das Acácias", "numero": "72", "bairro": "Vila Nova"}
        item = create(client, report(**address))
        duplicate = client.post(
            "/api/ocorrencias",
            json=report(
                **{
                    **address,
                    "rua": "R. das ACACIAS",
                    "numero": "nº072",
                }
            ),
        )
        assert duplicate.status_code == 409
        assert duplicate.json()["detail"]["ocorrencias"][0]["id"] == item["id"]
        other = create(client, report(**{**address, "bairro": "Centro"}))
        assert other["id"] != item["id"]


def test_version_one_database_keeps_the_protocol_and_matches_existing_addresses(app):
    web, _ = app
    store = web.state.occurrences
    with store.connect() as conn:
        conn.executescript(SCHEMA)
        conn.execute("PRAGMA user_version = 1")
        conn.execute(
            """INSERT INTO ocorrencias (
                id, visitante, pedido, descricao, local, local_chave, estado, protocolo,
                criado_em, atualizado_em
            ) VALUES (1, 'visitante', 'pedido', 'Um poste está apagado.', 'Rua das Acácias, 72',
                'rua das acacias, 72', 'encaminhada', 'EXEMPLO-120', '2026-11-10', '2026-11-10')"""
        )
        conn.execute(
            "INSERT INTO historico (ocorrencia, estado, criado_em) "
            "VALUES (1, 'encaminhada', '2026-11-10')"
        )
    with TestClient(web) as client:
        duplicate = client.post(
            "/api/ocorrencias",
            json=report(
                local=None,
                rua="R. das Acácias",
                numero="72",
                bairro="Centro",
            ),
        )
        assert duplicate.status_code == 409
        item = client.get("/api/ocorrencias/1").json()
        assert item["protocolo"] == item["historico"][0]["protocolo"] == "EXEMPLO-120"
    store.initialize()


def test_feedback_reopens_with_evidence_and_keeps_previous_protocol(app):
    web, password = app
    with TestClient(web) as resident, TestClient(web) as staff:
        item = create(resident)
        occurrence = item["id"]
        path = f"/api/equipe/ocorrencias/{occurrence}"
        public = f"/api/ocorrencias/{occurrence}"
        assert staff.post("/api/equipe/entrar", json={"senha": password}).status_code == 200
        assert (
            staff.patch(
                path,
                json={
                    "estado_anterior": "registrada",
                    "estado": "encaminhada",
                    "categoria": "iluminacao",
                    "protocolo": "EXEMPLO-1",
                },
            ).status_code
            == 200
        )
        closed = staff.patch(
            path,
            json={
                "estado_anterior": "encaminhada",
                "estado": "resolvida",
                "categoria": "iluminacao",
                "nota": "A luminária foi trocada.",
            },
        ).json()
        photo = BytesIO()
        Image.new("RGB", (8, 8)).save(photo, "PNG")
        feedback = {
            "fechamento": closed["fechamento"],
            "resolvido": False,
            "nota": "O poste continua apagado.",
            "foto": base64.b64encode(photo.getvalue()).decode(),
        }
        reopened = resident.post(public + "/retorno", json=feedback)
        assert reopened.status_code == 200
        item = reopened.json()
        assert item["estado"] == "reaberta"
        assert item["protocolo"] == "EXEMPLO-1"
        event = item["historico"][-1]
        assert event["tem_foto"]
        assert resident.get(public + f"/retornos/{event['id']}/foto").status_code == 200
        repeated = resident.post(public + "/retorno", json=feedback).json()
        assert repeated["historico"] == item["historico"]
        new = staff.patch(
            path,
            json={
                "estado_anterior": "reaberta",
                "estado": "encaminhada",
                "versao": item["versao"],
                "categoria": "iluminacao",
                "protocolo": "EXEMPLO-2",
            },
        ).json()
        assert new["protocolo"] == "EXEMPLO-2"
        assert new["historico"][1]["protocolo"] == "EXEMPLO-1"
        closed_again = staff.patch(
            path,
            json={
                "estado_anterior": "encaminhada",
                "estado": "resolvida",
                "categoria": "iluminacao",
                "nota": "O conector foi reparado.",
            },
        ).json()
        result = resident.post(
            public + "/retorno",
            json={
                "fechamento": closed_again["fechamento"],
                "resolvido": True,
            },
        ).json()
        assert result["estado"] == "resolvida"
        assert result["retorno_enviado"]
        assert result["historico"][-1]["estado"] == "reparo_confirmado"


def test_category_review_records_corrections_without_changing_status(app):
    web, password = app
    with TestClient(web) as client:
        item = create(client)
        path = f"/api/equipe/ocorrencias/{item['id']}/categoria"
        payload = {"categoria": "limpeza", "versao": item["versao"]}
        assert client.patch(path, json=payload).status_code == 401
        assert client.post("/api/equipe/entrar", json={"senha": password}).status_code == 200
        revised = client.patch(path, json=payload).json()
        assert revised["categoria_revisada"]
        assert revised["sugestao"] == "iluminacao"
        assert revised["estado"] == "registrada"
        assert client.patch(path, json=payload).status_code == 409
        result = client.get("/api/equipe/avaliacao").json()
        assert result["modelos"][0]["modelo"] == "0.1.0"
        assert result["modelos"][0]["com_sugestao"] == 1
        assert result["modelos"][0]["confirmadas"] == 0
        assert result["correcoes"][0]["id"] == item["id"]


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
