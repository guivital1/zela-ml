import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.openapi.docs import get_swagger_ui_html
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field

from zela_ml.access import TeamAccess
from zela_ml.inference import Classifier
from zela_ml.product import require_team, router
from zela_ml.settings import ARTIFACTS, INSTANCE, REPORTS, ROOT
from zela_ml.zeladoria import Occurrences

STATIC = Path(__file__).parent / "static"


class ClassificationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    text: str = Field(min_length=12, max_length=2000, strict=True)


def create_app(
    artifact_dir: Path = ARTIFACTS,
    database_path: Path | None = None,
    demo: bool = False,
    team_password: str | None = None,
) -> FastAPI:
    filename = "zela-exemplo.sqlite3" if demo else "zela.sqlite3"
    occurrences = Occurrences(database_path or (INSTANCE / filename))
    access = TeamAccess(team_password or os.environ.get("ZELA_SENHA_EQUIPE"))

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        occurrences.initialize()
        if demo:
            occurrences.seed_demo()
        try:
            app.state.classifier = Classifier(artifact_dir)
        except (FileNotFoundError, ValueError):
            logging.getLogger(__name__).warning("Classificador indisponível; triagem manual ativa.")
            app.state.classifier = None
        yield

    app = FastAPI(
        title="ZELA",
        version="0.1.0",
        lifespan=lifespan,
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )
    app.state.occurrences = occurrences
    app.state.demo = demo
    app.state.access = access
    app.mount("/assets", StaticFiles(directory=STATIC), name="assets")
    app.include_router(router)

    @app.middleware("http")
    async def request_boundary(request: Request, call_next):
        if request.method in {"POST", "PATCH"}:
            origin = request.headers.get("origin")
            site = f"{request.url.scheme}://{request.url.netloc}"
            if (origin and origin != site) or request.headers.get("sec-fetch-site") == "cross-site":
                return JSONResponse({"detail": "Ação disponível apenas dentro do ZELA."}, 403)
        response = await call_next(request)
        if not request.url.path.startswith("/assets/"):
            response.headers["Cache-Control"] = "no-store"
        return response

    @app.get("/", include_in_schema=False)
    def index():
        return FileResponse(STATIC / "index.html")

    @app.get("/equipe/tecnica", include_in_schema=False, dependencies=[Depends(require_team)])
    def technical():
        return FileResponse(Path(__file__).with_name("technical.html"))

    @app.get("/docs", include_in_schema=False, dependencies=[Depends(require_team)])
    def documentation():
        return get_swagger_ui_html(openapi_url="/openapi.json", title="ZELA · Documentação")

    @app.get("/openapi.json", include_in_schema=False, dependencies=[Depends(require_team)])
    def openapi():
        return app.openapi()

    @app.get("/equipe/notebook", include_in_schema=False, dependencies=[Depends(require_team)])
    def notebook():
        filename = "01_classificacao_relatos.ipynb"
        return FileResponse(ROOT / "notebooks" / filename, filename=filename)

    @app.get(
        "/evaluation/confusion-matrix.png",
        include_in_schema=False,
        dependencies=[Depends(require_team)],
    )
    def confusion_matrix():
        return FileResponse(REPORTS / "confusion_matrix.png")

    @app.get("/health")
    def health(request: Request):
        return {"status": "ok"}

    @app.get("/model", dependencies=[Depends(require_team)])
    def metadata(request: Request):
        classifier = model(request)
        return {"categories": classifier.categories, "metrics": classifier.metrics}

    @app.post("/classify", dependencies=[Depends(require_team)])
    def classify(payload: ClassificationRequest, request: Request):
        try:
            return model(request).predict(payload.text)
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error

    return app


def model(request: Request) -> Classifier:
    classifier = request.app.state.classifier
    if classifier is None:
        raise HTTPException(503, "O classificador está indisponível.")
    return classifier


app = create_app()
