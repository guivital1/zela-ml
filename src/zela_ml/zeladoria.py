from __future__ import annotations

import sqlite3
from contextlib import closing, contextmanager
from datetime import UTC, datetime
from pathlib import Path

from zela_ml.dataset import normalize
from zela_ml.endereco import Endereco, chave
from zela_ml.settings import CATEGORIES

STATES = {
    "registrada": "Registrada",
    "encaminhada": "Encaminhada",
    "resolvida": "Resolvida",
    "reaberta": "Em nova revisão",
    "reparo_confirmado": "Reparo confirmado por morador",
    "resposta_prefeitura": "Resposta da prefeitura",
}
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
MIGRATION = (
    "ALTER TABLE ocorrencias ADD COLUMN rua_chave TEXT NOT NULL DEFAULT ''",
    "ALTER TABLE ocorrencias ADD COLUMN numero_chave TEXT NOT NULL DEFAULT ''",
    "ALTER TABLE ocorrencias ADD COLUMN bairro_chave TEXT NOT NULL DEFAULT ''",
    "ALTER TABLE ocorrencias ADD COLUMN reaberta INTEGER NOT NULL DEFAULT 0",
    "ALTER TABLE ocorrencias ADD COLUMN versao INTEGER NOT NULL DEFAULT 0",
    "ALTER TABLE ocorrencias ADD COLUMN modelo TEXT",
    "ALTER TABLE historico ADD COLUMN fechamento INTEGER REFERENCES historico(id)",
    "ALTER TABLE historico ADD COLUMN visitante TEXT",
    "ALTER TABLE historico ADD COLUMN foto BLOB",
    "ALTER TABLE historico ADD COLUMN protocolo TEXT",
    "CREATE INDEX ocorrencias_endereco ON ocorrencias(rua_chave, numero_chave, bairro_chave)",
    "CREATE UNIQUE INDEX retorno_por_fechamento ON historico(fechamento, visitante)",
    """CREATE TABLE revisoes_categoria (
        id INTEGER PRIMARY KEY,
        ocorrencia INTEGER NOT NULL REFERENCES ocorrencias(id),
        categoria TEXT NOT NULL,
        criado_em TEXT NOT NULL
    )""",
    "CREATE INDEX revisoes_por_ocorrencia ON revisoes_categoria(ocorrencia, id)",
)
MUNICIPAL_MIGRATION = (
    "ALTER TABLE historico ADD COLUMN recebido_em TEXT",
    "ALTER TABLE historico ADD COLUMN proximo_passo TEXT",
    "ALTER TABLE historico ADD COLUMN pedido_resposta TEXT",
    "CREATE UNIQUE INDEX pedido_resposta_por_ocorrencia ON historico(ocorrencia, pedido_resposta)",
)
REVIEW_MIGRATION = (
    "ALTER TABLE ocorrencias ADD COLUMN segunda_sugestao TEXT",
    "ALTER TABLE ocorrencias ADD COLUMN requer_revisao INTEGER",
)
SUMMARY = """
SELECT o.id, o.descricao, o.local, o.categoria, o.estado, o.reaberta, o.versao, o.protocolo,
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
    if item.pop("reaberta"):
        item["estado"] = "reaberta"
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
            conn.execute("BEGIN IMMEDIATE")
            version = conn.execute("PRAGMA user_version").fetchone()[0]
            if version > 4:
                raise RuntimeError("O banco foi criado por uma versão mais recente do ZELA.")
            if version == 0:
                for statement in SCHEMA.split(";"):
                    if statement.strip():
                        conn.execute(statement)
            if version < 2:
                for statement in MIGRATION:
                    conn.execute(statement)
                for row in conn.execute("SELECT id, local FROM ocorrencias"):
                    self.save_address(conn, row["id"], Endereco.legado(row["local"]))
                conn.execute(
                    """UPDATE historico SET protocolo = (
                        SELECT protocolo FROM ocorrencias WHERE id = historico.ocorrencia
                    ) WHERE estado = 'encaminhada'"""
                )
                conn.execute("PRAGMA user_version = 2")
            if version < 3:
                for statement in MUNICIPAL_MIGRATION:
                    conn.execute(statement)
                conn.execute("PRAGMA user_version = 3")
            if version < 4:
                for statement in REVIEW_MIGRATION:
                    conn.execute(statement)
                conn.execute("PRAGMA user_version = 4")

    @staticmethod
    def save_address(conn: sqlite3.Connection, occurrence: int, address: Endereco) -> None:
        conn.execute(
            "UPDATE ocorrencias SET rua_chave = ?, numero_chave = ?, bairro_chave = ? WHERE id = ?",
            (address.rua_chave, address.numero_chave, chave(address.bairro), occurrence),
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
            conn.execute("BEGIN")
            row = conn.execute(SUMMARY + "WHERE o.id = ?", (person, occurrence)).fetchone()
            if row is None:
                return None
            item = present(row)
            events = conn.execute(
                "SELECT id, estado, nota, criado_em, protocolo, recebido_em, proximo_passo, "
                "foto IS NOT NULL AS tem_foto "
                "FROM historico WHERE ocorrencia = ? ORDER BY id",
                (occurrence,),
            )
            item["historico"] = [{**event, "situacao": STATES[event["estado"]]} for event in events]
            replies = (
                event
                for event in item["historico"]
                if event["estado"] == "resposta_prefeitura"
                and event["protocolo"] == item["protocolo"]
            )
            item["resposta_prefeitura"] = max(
                replies,
                key=lambda event: (event["recebido_em"], event["id"]),
                default=None,
            )
            if item["estado"] == "resolvida":
                closed = next(
                    event for event in reversed(item["historico"]) if event["estado"] == "resolvida"
                )
                item["fechamento"] = closed["id"]
                item["retorno_enviado"] = bool(
                    conn.execute(
                        "SELECT 1 FROM historico WHERE fechamento = ? AND visitante = ?",
                        (closed["id"], person),
                    ).fetchone()
                )
            if team:
                suggestion = conn.execute(
                    "SELECT sugestao, segunda_sugestao, requer_revisao FROM ocorrencias "
                    "WHERE id = ?",
                    (occurrence,),
                ).fetchone()
                item.update(suggestion)
                item["categoria_revisada"] = bool(
                    conn.execute(
                        "SELECT 1 FROM revisoes_categoria WHERE ocorrencia = ?", (occurrence,)
                    ).fetchone()
                )
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
        address: Endereco,
        category: str | None,
        suggestion: str | None,
        photo: bytes | None,
        separate: bool,
        model: str | None = None,
        alternative: str | None = None,
        requires_review: bool | None = None,
    ) -> int:
        timestamp = now()
        place_key = normalize(address.local)
        with self.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            prior = conn.execute(
                "SELECT id FROM ocorrencias WHERE visitante = ? AND pedido = ?", (person, key)
            ).fetchone()
            if prior:
                return prior["id"]
            if not separate:
                matches = conn.execute(
                    SUMMARY
                    + """WHERE o.estado <> 'resolvida' AND (
                        o.local_chave = ? OR (
                            o.rua_chave <> '' AND o.rua_chave = ? AND o.numero_chave = ?
                            AND (o.bairro_chave = ? OR o.bairro_chave = '' OR ? = '')
                        )
                    ) ORDER BY o.id DESC LIMIT 5""",
                    (
                        person,
                        place_key,
                        address.rua_chave,
                        address.numero_chave,
                        chave(address.bairro),
                        chave(address.bairro),
                    ),
                ).fetchall()
                if matches:
                    raise DuplicateLocation([present(row) for row in matches])
            occurrence = conn.execute(
                """INSERT INTO ocorrencias (
                    visitante, pedido, descricao, local, local_chave, categoria, sugestao,
                    foto, criado_em, atualizado_em, modelo, segunda_sugestao, requer_revisao
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    person,
                    key,
                    description,
                    address.local,
                    place_key,
                    category,
                    suggestion,
                    photo,
                    timestamp,
                    timestamp,
                    model,
                    alternative,
                    requires_review,
                ),
            ).lastrowid
            self.save_address(conn, occurrence, address)
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
        version: int | None = None,
    ) -> None:
        timestamp = now()
        with self.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute(
                "SELECT estado, reaberta, versao, protocolo FROM ocorrencias WHERE id = ?",
                (occurrence,),
            ).fetchone()
            if row is None:
                raise LookupError
            current = "reaberta" if row["reaberta"] else row["estado"]
            if current != expected or (version is not None and row["versao"] != version):
                raise InvalidUpdate("O andamento mudou. Abra a ocorrência novamente.")
            allowed = {
                "registrada": {"encaminhada", "resolvida"},
                "encaminhada": {"resolvida"},
                "reaberta": {"encaminhada", "resolvida"},
            }
            if state not in allowed.get(expected, set()):
                raise InvalidUpdate("Essa mudança de andamento não está disponível.")
            if current == "reaberta" and state == "encaminhada" and not protocol:
                protocol = row["protocolo"]
            if state == "encaminhada" and not protocol:
                raise InvalidUpdate("Informe o protocolo recebido no canal oficial.")
            if state == "resolvida" and not note:
                raise InvalidUpdate("Descreva o que foi feito para resolver o problema.")
            protocol = protocol if state == "encaminhada" else row["protocolo"]
            conn.execute(
                "UPDATE ocorrencias SET estado = ?, categoria = ?, protocolo = ?, "
                "atualizado_em = ?, reaberta = 0, versao = versao + 1 WHERE id = ?",
                (state, category, protocol, timestamp, occurrence),
            )
            conn.execute(
                "INSERT INTO historico (ocorrencia, estado, nota, criado_em, protocolo) "
                "VALUES (?, ?, ?, ?, ?)",
                (occurrence, state, note, timestamp, protocol if state == "encaminhada" else None),
            )
            self.record_category(conn, occurrence, category, timestamp)

    def feedback(
        self,
        occurrence: int,
        person: str,
        closure: int,
        repaired: bool,
        note: str | None,
        photo: bytes | None,
    ) -> None:
        timestamp = now()
        with self.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute(
                "SELECT estado, protocolo FROM ocorrencias WHERE id = ?", (occurrence,)
            ).fetchone()
            if row is None:
                raise LookupError
            prior = conn.execute(
                "SELECT estado FROM historico WHERE ocorrencia = ? AND fechamento = ? "
                "AND visitante = ?",
                (occurrence, closure, person),
            ).fetchone()
            event = "reparo_confirmado" if repaired else "reaberta"
            if prior and prior["estado"] == event:
                return
            latest = conn.execute(
                "SELECT MAX(id) FROM historico WHERE ocorrencia = ? AND estado = 'resolvida'",
                (occurrence,),
            ).fetchone()[0]
            if prior or row["estado"] != "resolvida" or latest != closure:
                raise InvalidUpdate("O andamento mudou ou seu retorno já foi registrado.")
            conn.execute(
                """INSERT INTO historico (
                    ocorrencia, estado, nota, criado_em, fechamento, visitante, foto
                ) VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (occurrence, event, note, timestamp, closure, person, photo),
            )
            conn.execute("INSERT OR IGNORE INTO confirmacoes VALUES (?, ?)", (occurrence, person))
            if not repaired:
                state = "encaminhada" if row["protocolo"] else "registrada"
                conn.execute(
                    "UPDATE ocorrencias SET estado = ?, reaberta = 1, atualizado_em = ?, "
                    "versao = versao + 1 WHERE id = ?",
                    (state, timestamp, occurrence),
                )

    def municipal_reply(
        self, occurrence: int, key: str, version: int, received: str, reply: str, next_step: str
    ) -> None:
        timestamp = now()
        with self.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute(
                "SELECT protocolo, versao FROM ocorrencias WHERE id = ?", (occurrence,)
            ).fetchone()
            if row is None:
                raise LookupError
            if conn.execute(
                "SELECT 1 FROM historico WHERE ocorrencia = ? AND pedido_resposta = ?",
                (occurrence, key),
            ).fetchone():
                return
            if row["versao"] != version:
                raise InvalidUpdate("A ocorrência mudou. Abra o relato novamente.")
            if not row["protocolo"]:
                raise InvalidUpdate("Registre o protocolo antes de incluir a resposta.")
            conn.execute(
                """INSERT INTO historico (
                    ocorrencia, estado, nota, criado_em, protocolo, recebido_em,
                    proximo_passo, pedido_resposta
                ) VALUES (?, 'resposta_prefeitura', ?, ?, ?, ?, ?, ?)""",
                (occurrence, reply, timestamp, row["protocolo"], received, next_step, key),
            )
            conn.execute(
                "UPDATE ocorrencias SET atualizado_em = ?, versao = versao + 1 WHERE id = ?",
                (timestamp, occurrence),
            )

    def feedback_photo(self, occurrence: int, event: int) -> bytes | None:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT foto FROM historico WHERE ocorrencia = ? AND id = ?", (occurrence, event)
            ).fetchone()
            return row["foto"] if row else None

    @staticmethod
    def record_category(conn, occurrence: int, category: str, timestamp: str) -> bool:
        last = conn.execute(
            "SELECT categoria FROM revisoes_categoria WHERE ocorrencia = ? "
            "ORDER BY id DESC LIMIT 1",
            (occurrence,),
        ).fetchone()
        if last and last["categoria"] == category:
            return False
        conn.execute(
            "INSERT INTO revisoes_categoria (ocorrencia, categoria, criado_em) VALUES (?, ?, ?)",
            (occurrence, category, timestamp),
        )
        return True

    def review_category(self, occurrence: int, category: str, version: int) -> None:
        timestamp = now()
        with self.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute(
                "SELECT versao FROM ocorrencias WHERE id = ?", (occurrence,)
            ).fetchone()
            if row is None:
                raise LookupError
            if row["versao"] != version:
                raise InvalidUpdate("A ocorrência mudou. Abra a ocorrência novamente.")
            if self.record_category(conn, occurrence, category, timestamp):
                conn.execute(
                    "UPDATE ocorrencias SET categoria = ?, versao = versao + 1 WHERE id = ?",
                    (category, occurrence),
                )

    def evaluation(self) -> list[dict]:
        with self.connect() as conn:
            rows = conn.execute(
                """SELECT o.modelo, COUNT(*) AS revisadas,
                          SUM(o.sugestao IS NOT NULL) AS com_sugestao,
                          SUM(CASE WHEN o.sugestao = r.categoria THEN 1 ELSE 0 END) AS confirmadas
                   FROM revisoes_categoria r JOIN ocorrencias o ON o.id = r.ocorrencia
                   WHERE r.id = (
                       SELECT MAX(id) FROM revisoes_categoria WHERE ocorrencia = r.ocorrencia
                   )
                   GROUP BY o.modelo ORDER BY o.modelo"""
            )
            return [dict(row) for row in rows]

    def corrections(self) -> list[dict]:
        with self.connect() as conn:
            rows = conn.execute(
                """SELECT o.id, o.sugestao, r.categoria
                   FROM revisoes_categoria r JOIN ocorrencias o ON o.id = r.ocorrencia
                   WHERE o.sugestao <> r.categoria AND r.id = (
                       SELECT MAX(id) FROM revisoes_categoria WHERE ocorrencia = r.ocorrencia
                   ) ORDER BY r.id DESC LIMIT 20"""
            )
            return [
                {
                    "id": row["id"],
                    "codigo": f"ZL-{row['id']:04d}",
                    "sugestao": REPORT_CATEGORIES[row["sugestao"]],
                    "categoria": REPORT_CATEGORIES[row["categoria"]],
                }
                for row in rows
            ]

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
                self.save_address(conn, occurrence, Endereco.legado(place))
                conn.execute("INSERT INTO confirmacoes VALUES (?, 'exemplo')", (occurrence,))
                conn.execute(
                    "INSERT INTO historico (ocorrencia, estado, criado_em) "
                    "VALUES (?, 'registrada', ?)",
                    (occurrence, timestamp),
                )
                if state != "registrada":
                    conn.execute(
                        "INSERT INTO historico (ocorrencia, estado, nota, criado_em, protocolo) "
                        "VALUES (?, ?, ?, ?, ?)",
                        (occurrence, state, note, timestamp, protocol),
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
