import base64
import binascii
from datetime import date
from io import BytesIO
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from PIL import Image, ImageOps
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from zela_ml.access import visitor
from zela_ml.endereco import Endereco
from zela_ml.zeladoria import REPORT_CATEGORIES, DuplicateLocation, InvalidUpdate

router = APIRouter(prefix="/api")


def require_team(request: Request) -> None:
    request.app.state.access.require(request)


def valid_category(value: str | None) -> str | None:
    if value is not None and value not in REPORT_CATEGORIES:
        raise ValueError("Escolha um tipo de problema da lista.")
    return value


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class Report(Input):
    pedido: UUID
    descricao: str = Field(min_length=12, max_length=1000)
    local: str | None = Field(default=None, min_length=5, max_length=160)
    rua: str | None = Field(default=None, min_length=3, max_length=100)
    numero: str = Field(default="", max_length=16)
    bairro: str = Field(default="", max_length=40)
    categoria: str | None = None
    foto: str | None = Field(default=None, max_length=2_800_000)
    outro_problema: bool = False

    @model_validator(mode="after")
    def has_address(self):
        if self.rua is None and self.local is None:
            raise ValueError("Informe a rua ou o local da ocorrência.")
        return self

    def address(self) -> Endereco:
        if self.rua is None:
            assert self.local is not None
            return Endereco.legado(self.local)
        local = self.rua
        if self.numero:
            local += f", {self.numero}"
        if self.bairro:
            local += f" · {self.bairro}"
        return Endereco(local, self.rua, self.numero, self.bairro)

    @field_validator("categoria")
    @classmethod
    def category(cls, value: str | None) -> str | None:
        return valid_category(value)

    @field_validator("descricao")
    @classmethod
    def description(cls, value: str) -> str:
        value = " ".join(value.split())
        if len(value) < 12 or sum(character.isalpha() for character in value) < 8:
            raise ValueError("Descreva o que aconteceu com algumas palavras.")
        return value


class CategoryReview(Input):
    categoria: str
    versao: int = Field(ge=0)

    @field_validator("categoria")
    @classmethod
    def category(cls, value: str) -> str:
        valid_category(value)
        return value


class Update(CategoryReview):
    estado_anterior: Literal["registrada", "encaminhada", "resolvida", "reaberta"]
    estado: Literal["encaminhada", "resolvida"]
    versao: int | None = Field(default=None, ge=0)
    protocolo: str | None = Field(default=None, max_length=80)
    nota: str | None = Field(default=None, max_length=300)


class Feedback(Input):
    fechamento: int = Field(gt=0)
    resolvido: bool
    nota: str | None = Field(default=None, max_length=300)
    foto: str | None = Field(default=None, max_length=2_800_000)


class Login(BaseModel):
    senha: str = Field(min_length=1, max_length=256)


class MunicipalReply(Input):
    pedido: UUID
    versao: int = Field(ge=0)
    recebido_em: date
    resposta: str = Field(min_length=3, max_length=500)
    proximo_passo: str = Field(min_length=3, max_length=240)

    @field_validator("recebido_em")
    @classmethod
    def received_date(cls, value: date) -> date:
        if value > date.today():
            raise ValueError("Informe a data em que a resposta foi recebida.")
        return value


def prepare_photo(encoded: str | None) -> bytes | None:
    if not encoded:
        return None
    try:
        raw = base64.b64decode(encoded, validate=True)
        if len(raw) > 2 * 1024 * 1024:
            raise ValueError("photo size")
        with Image.open(BytesIO(raw), formats=("JPEG", "PNG", "WEBP")) as image:
            if image.width * image.height > 16_000_000:
                raise ValueError("photo dimensions")
            picture = ImageOps.exif_transpose(image).convert("RGB")
            picture.thumbnail((1280, 1280))
            output = BytesIO()
            picture.save(output, "JPEG", quality=85)
            return output.getvalue()
    except (binascii.Error, Image.DecompressionBombError, OSError, ValueError) as error:
        raise HTTPException(422, "Escolha uma foto JPG, PNG ou WebP de até 2 MB.") from error


def find_detail(request: Request, occurrence: int, person: str) -> dict:
    team = request.app.state.access.authorized(request)
    detail = request.app.state.occurrences.detail(occurrence, person, team)
    if detail is None:
        raise HTTPException(404, "Ocorrência não encontrada.")
    return detail


@router.get("/ocorrencias")
def list_occurrences(request: Request, response: Response, minhas: bool = False):
    person = visitor(request, response)
    return {
        "ocorrencias": request.app.state.occurrences.list(person, minhas),
        "exemplo": request.app.state.demo,
        "categorias": REPORT_CATEGORIES,
    }


@router.post("/ocorrencias", status_code=201)
def create_occurrence(payload: Report, request: Request, response: Response):
    person = visitor(request, response)
    photo = prepare_photo(payload.foto)
    classifier = request.app.state.classifier
    suggestion = classifier.predict(payload.descricao)["category"] if classifier else None
    try:
        occurrence = request.app.state.occurrences.create(
            person,
            str(payload.pedido),
            payload.descricao,
            payload.address(),
            payload.categoria,
            suggestion,
            photo,
            payload.outro_problema,
            classifier.version if classifier else None,
        )
    except DuplicateLocation as error:
        raise HTTPException(409, {"ocorrencias": error.matches}) from error
    return find_detail(request, occurrence, person)


@router.get("/ocorrencias/{occurrence}")
def occurrence_detail(occurrence: int, request: Request, response: Response):
    return find_detail(request, occurrence, visitor(request, response))


@router.get("/ocorrencias/{occurrence}/foto")
def occurrence_photo(occurrence: int, request: Request):
    photo = request.app.state.occurrences.photo(occurrence)
    if photo is None:
        raise HTTPException(404, "Foto indisponível.")
    return Response(photo, media_type="image/jpeg", headers={"X-Content-Type-Options": "nosniff"})


@router.post("/ocorrencias/{occurrence}/retorno")
def send_feedback(occurrence: int, payload: Feedback, request: Request, response: Response):
    person = visitor(request, response)
    photo = prepare_photo(payload.foto)
    if not payload.resolvido and not (payload.nota or photo):
        raise HTTPException(422, "Conte o que ainda acontece ou inclua uma foto.")
    try:
        request.app.state.occurrences.feedback(
            occurrence, person, payload.fechamento, payload.resolvido, payload.nota, photo
        )
    except LookupError as error:
        raise HTTPException(404, "Ocorrência não encontrada.") from error
    except InvalidUpdate as error:
        raise HTTPException(409, str(error)) from error
    return find_detail(request, occurrence, person)


@router.get("/ocorrencias/{occurrence}/retornos/{event}/foto")
def feedback_photo(occurrence: int, event: int, request: Request):
    photo = request.app.state.occurrences.feedback_photo(occurrence, event)
    if photo is None:
        raise HTTPException(404, "Foto indisponível.")
    return Response(photo, media_type="image/jpeg", headers={"X-Content-Type-Options": "nosniff"})


@router.post("/ocorrencias/{occurrence}/confirmar")
def confirm_occurrence(occurrence: int, request: Request, response: Response):
    person = visitor(request, response)
    try:
        request.app.state.occurrences.confirm(occurrence, person)
    except LookupError as error:
        raise HTTPException(404, "Ocorrência não encontrada.") from error
    except InvalidUpdate as error:
        raise HTTPException(409, str(error)) from error
    return find_detail(request, occurrence, person)


@router.get("/equipe")
def team_session(request: Request):
    return {"autorizado": request.app.state.access.authorized(request)}


@router.post("/equipe/entrar")
def team_login(payload: Login, request: Request, response: Response):
    request.app.state.access.login(payload.senha, request, response)
    return {"autorizado": True}


@router.post("/equipe/sair")
def team_logout(request: Request, response: Response):
    request.app.state.access.logout(request, response)
    return {"autorizado": False}


@router.get("/equipe/avaliacao", dependencies=[Depends(require_team)])
def team_evaluation(request: Request):
    occurrences = request.app.state.occurrences
    return {
        "exemplo": request.app.state.demo,
        "modelos": occurrences.evaluation(),
        "correcoes": occurrences.corrections(),
    }


@router.post("/equipe/ocorrencias/{occurrence}/resposta", dependencies=[Depends(require_team)])
def record_municipal_reply(
    occurrence: int, payload: MunicipalReply, request: Request, response: Response
):
    try:
        request.app.state.occurrences.municipal_reply(
            occurrence,
            str(payload.pedido),
            payload.versao,
            payload.recebido_em.isoformat(),
            payload.resposta,
            payload.proximo_passo,
        )
    except LookupError as error:
        raise HTTPException(404, "Ocorrência não encontrada.") from error
    except InvalidUpdate as error:
        raise HTTPException(409, str(error)) from error
    return find_detail(request, occurrence, visitor(request, response))


@router.patch("/equipe/ocorrencias/{occurrence}/categoria", dependencies=[Depends(require_team)])
def review_category(occurrence: int, payload: CategoryReview, request: Request, response: Response):
    try:
        request.app.state.occurrences.review_category(occurrence, payload.categoria, payload.versao)
    except LookupError as error:
        raise HTTPException(404, "Ocorrência não encontrada.") from error
    except InvalidUpdate as error:
        raise HTTPException(409, str(error)) from error
    return find_detail(request, occurrence, visitor(request, response))


@router.patch("/equipe/ocorrencias/{occurrence}", dependencies=[Depends(require_team)])
def update_occurrence(occurrence: int, payload: Update, request: Request, response: Response):
    try:
        request.app.state.occurrences.update(
            occurrence,
            payload.estado_anterior,
            payload.estado,
            payload.categoria,
            payload.protocolo,
            payload.nota,
            payload.versao,
        )
    except LookupError as error:
        raise HTTPException(404, "Ocorrência não encontrada.") from error
    except InvalidUpdate as error:
        raise HTTPException(409, str(error)) from error
    return find_detail(request, occurrence, visitor(request, response))
