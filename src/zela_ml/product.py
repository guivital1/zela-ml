import base64
import binascii
from io import BytesIO
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from PIL import Image, ImageOps
from pydantic import BaseModel, ConfigDict, Field, field_validator

from zela_ml.access import visitor
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
    local: str = Field(min_length=5, max_length=160)
    categoria: str | None = None
    foto: str | None = Field(default=None, max_length=2_800_000)
    outro_problema: bool = False

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


class Update(Input):
    estado_anterior: Literal["registrada", "encaminhada", "resolvida"]
    estado: Literal["encaminhada", "resolvida"]
    categoria: str
    protocolo: str | None = Field(default=None, max_length=80)
    nota: str | None = Field(default=None, max_length=300)

    @field_validator("categoria")
    @classmethod
    def category(cls, value: str) -> str:
        valid_category(value)
        return value


class Login(BaseModel):
    senha: str = Field(min_length=1, max_length=256)


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
            payload.local,
            payload.categoria,
            suggestion,
            photo,
            payload.outro_problema,
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
        )
    except LookupError as error:
        raise HTTPException(404, "Ocorrência não encontrada.") from error
    except InvalidUpdate as error:
        raise HTTPException(409, str(error)) from error
    return find_detail(request, occurrence, visitor(request, response))
