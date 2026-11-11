import sqlite3
from contextlib import closing, contextmanager
from datetime import UTC, datetime
from pathlib import Path

from zela_ml.dataset import normalize
from zela_ml.settings import CATEGORIES

STATES = {"registrada": "Registrada", "encaminhada": "Encaminhada", "resolvida": "Resolvida"}
REPORT_CATEGORIES = {**CATEGORIES, "outros": "Outros serviços"}
SCHEMA = """
CREATE TABLE IF NOT EXISTS ocorrencias (
    id INTEGER PRIMARY KEY,
    visitante TEXT NOT NULL,
    pedido TEXT NOT NULL,
    descricao TEXT NOT NULL,
    local TEXT NOT NULL,
    local_chave TEXT NOT NULL,
    categoria TEXT,
    sugestao TEXT,
    estado TEXT NOT NULL DEFAULT 'registrada'
        CHECK (estado IN ('registrada', 'encaminhada', 'resolvida')),
    protocolo TEXT,
    foto BLOB,
    criado_em TEXT NOT NULL,
    atualizado_em TEXT NOT NULL,
    UNIQUE(visitante, pedido)
);
CREATE INDEX IF NOT EXISTS ocorrencias_local ON ocorrencias(local_chave, estado);
CREATE TABLE IF NOT EXISTS confirmacoes (
    ocorrencia INTEGER NOT NULL REFERENCES ocorrencias(id),
    visitante TEXT NOT NULL,
    PRIMARY KEY (ocorrencia, visitante)
);
CREATE TABLE IF NOT EXISTS historico (
    id INTEGER PRIMARY KEY,
    ocorrencia INTEGER NOT NULL REFERENCES ocorrencias(id),
    estado TEXT NOT NULL,
    nota TEXT,
    criado_em TEXT NOT NULL
);
"""
SUMMARY = """
SELECT o.id, o.descricao, o.local, o.categoria, o.estado, o.protocolo,
       o.criado_em, o.atualizado_em, o.foto IS NOT NULL AS tem_foto,
       (SELECT COUNT(*) FROM confirmacoes WHERE ocorrencia = o.id) AS confirmacoes,
       EXISTS(SELECT 1 FROM confirmacoes WHERE ocorrencia = o.id AND visitante = ?) AS confirmou
FROM ocorrencias o
"""


class DuplicateLocation(Exception):
    def __init__(self, matches: list[dict]):
        self.matches = matches


class InvalidUpdate(Exception):
    pass


def now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def present(row: sqlite3.Row) -> dict:
    item = dict(row)
    item["codigo"] = f"ZL-{item['id']:04d}"
    item["tipo"] = REPORT_CATEGORIES.get(item["categoria"], "A identificar")
    item["situacao"] = STATES[item["estado"]]
    return item


class Occurrences:
    def __init__(self, path: Path):
        self.path = path

    @contextmanager
    def connect(self):
        with closing(sqlite3.connect(self.path, timeout=5)) as conn, conn:
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA foreign_keys = ON")
            yield conn

    def initialize(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as conn:
            version = conn.execute("PRAGMA user_version").fetchone()[0]
            if version > 1:
                raise RuntimeError("O banco foi criado por uma versão mais recente do ZELA.")
            if version == 0:
                conn.executescript(
                    "BEGIN IMMEDIATE;\n" + SCHEMA + "\nPRAGMA user_version=1; COMMIT;"
                )

    def list(self, person: str, mine: bool = False) -> list[dict]:
        condition = (
            "WHERE EXISTS(SELECT 1 FROM confirmacoes WHERE ocorrencia = o.id AND visitante = ?)"
            if mine
            else ""
        )
        args = (person, person) if mine else (person,)
        with self.connect() as conn:
            rows = conn.execute(
                SUMMARY + condition + " ORDER BY o.estado = 'resolvida', o.atualizado_em DESC, "
                "o.id DESC",
                args,
            )
            return [present(row) for row in rows]

    def detail(self, occurrence: int, person: str, team: bool = False) -> dict | None:
        with self.connect() as conn:
            row = conn.execute(SUMMARY + "WHERE o.id = ?", (person, occurrence)).fetchone()
            if row is None:
                return None
            item = present(row)
            events = conn.execute(
                "SELECT estado, nota, criado_em FROM historico WHERE ocorrencia = ? ORDER BY id",
                (occurrence,),
            )
            item["historico"] = [{**event, "situacao": STATES[event["estado"]]} for event in events]
            if team:
                item["sugestao"] = conn.execute(
                    "SELECT sugestao FROM ocorrencias WHERE id = ?", (occurrence,)
                ).fetchone()[0]
            return item

    def photo(self, occurrence: int) -> bytes | None:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT foto FROM ocorrencias WHERE id = ?", (occurrence,)
            ).fetchone()
            return row["foto"] if row else None

    def create(
        self,
        person: str,
        key: str,
        description: str,
        place: str,
        category: str | None,
        suggestion: str | None,
        photo: bytes | None,
        separate: bool,
    ) -> int:
        timestamp = now()
        place_key = normalize(place)
        with self.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            prior = conn.execute(
                "SELECT id FROM ocorrencias WHERE visitante = ? AND pedido = ?", (person, key)
            ).fetchone()
            if prior:
                return prior["id"]
            if not separate:
                matches = conn.execute(
                    SUMMARY + "WHERE o.local_chave = ? AND o.estado <> 'resolvida' "
                    "ORDER BY o.id DESC LIMIT 5",
                    (person, place_key),
                ).fetchall()
                if matches:
                    raise DuplicateLocation([present(row) for row in matches])
            occurrence = conn.execute(
                """INSERT INTO ocorrencias (
                    visitante, pedido, descricao, local, local_chave, categoria, sugestao,
                    foto, criado_em, atualizado_em
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    person,
                    key,
                    description,
                    place,
                    place_key,
                    category,
                    suggestion,
                    photo,
                    timestamp,
                    timestamp,
                ),
            ).lastrowid
            conn.execute("INSERT INTO confirmacoes VALUES (?, ?)", (occurrence, person))
            conn.execute(
                "INSERT INTO historico (ocorrencia, estado, criado_em) VALUES (?, 'registrada', ?)",
                (occurrence, timestamp),
            )
        return occurrence

    def confirm(self, occurrence: int, person: str) -> None:
        with self.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute(
                "SELECT estado FROM ocorrencias WHERE id = ?", (occurrence,)
            ).fetchone()
            if row is None:
                raise LookupError
            if row["estado"] == "resolvida":
                raise InvalidUpdate("Essa ocorrência já foi resolvida.")
            conn.execute("INSERT OR IGNORE INTO confirmacoes VALUES (?, ?)", (occurrence, person))

    def update(
        self,
        occurrence: int,
        expected: str,
        state: str,
        category: str,
        protocol: str | None,
        note: str | None,
    ) -> None:
        timestamp = now()
        with self.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute(
                "SELECT estado, protocolo FROM ocorrencias WHERE id = ?", (occurrence,)
            ).fetchone()
            if row is None:
                raise LookupError
            if row["estado"] != expected:
                raise InvalidUpdate("O andamento mudou. Abra a ocorrência novamente.")
            allowed = {"registrada": {"encaminhada", "resolvida"}, "encaminhada": {"resolvida"}}
            if state not in allowed.get(expected, set()):
                raise InvalidUpdate("Essa mudança de andamento não está disponível.")
            if state == "encaminhada" and not protocol:
                raise InvalidUpdate("Informe o protocolo recebido no canal oficial.")
            if state == "resolvida" and not note:
                raise InvalidUpdate("Descreva o que foi feito para resolver o problema.")
            protocol = protocol if state == "encaminhada" else row["protocolo"]
            conn.execute(
                "UPDATE ocorrencias SET estado = ?, categoria = ?, protocolo = ?, "
                "atualizado_em = ? WHERE id = ?",
                (state, category, protocol, timestamp, occurrence),
            )
            conn.execute(
                "INSERT INTO historico (ocorrencia, estado, nota, criado_em) VALUES (?, ?, ?, ?)",
                (occurrence, state, note, timestamp),
            )

    def seed_demo(self) -> None:
        examples = (
            (
                "O poste perto da praça não acende desde a última chuva.",
                "Rua das Acácias, 120",
                "iluminacao",
                "encaminhada",
                "EXEMPLO-024",
                "Pedido de reparo registrado.",
            ),
            (
                "A rampa da calçada está quebrada e dificulta a travessia.",
                "Rua das Acácias, 48",
                "acessibilidade",
                "registrada",
                None,
                None,
            ),
            (
                "Sacos de lixo foram deixados perto do ponto de ônibus.",
                "Rua dos Ipês, 85",
                "limpeza",
                "resolvida",
                None,
                "O material foi recolhido pela equipe de limpeza.",
            ),
        )
        with self.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            if conn.execute("SELECT EXISTS(SELECT 1 FROM ocorrencias)").fetchone()[0]:
                return
            for index, (description, place, category, state, protocol, note) in enumerate(examples):
                timestamp = now()
                occurrence = conn.execute(
                    """INSERT INTO ocorrencias (
                        visitante, pedido, descricao, local, local_chave, categoria, estado,
                        protocolo, criado_em, atualizado_em
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        "exemplo",
                        str(index),
                        description,
                        place,
                        normalize(place),
                        category,
                        state,
                        protocol,
                        timestamp,
                        timestamp,
                    ),
                ).lastrowid
                conn.execute("INSERT INTO confirmacoes VALUES (?, 'exemplo')", (occurrence,))
                conn.execute(
                    "INSERT INTO historico (ocorrencia, estado, criado_em) "
                    "VALUES (?, 'registrada', ?)",
                    (occurrence, timestamp),
                )
                if state != "registrada":
                    conn.execute(
                        "INSERT INTO historico (ocorrencia, estado, nota, criado_em) "
                        "VALUES (?, ?, ?, ?)",
                        (occurrence, state, note, timestamp),
                    )

    def backup(self, destination: Path) -> None:
        if destination.resolve() == self.path.resolve():
            raise ValueError("Escolha um arquivo diferente do banco em uso.")
        with destination.open("xb"):
            pass
        try:
            with self.connect() as source, closing(sqlite3.connect(destination)) as target:
                source.backup(target)
        except Exception:
            destination.unlink()
            raise
