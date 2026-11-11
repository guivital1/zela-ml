from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field

from zela_ml.inference import Classifier
from zela_ml.settings import ARTIFACTS, REPORTS

STATIC = Path(__file__).parent / "static"


class ClassificationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    text: str = Field(min_length=12, max_length=2000, strict=True)


def create_app(artifact_dir: Path = ARTIFACTS) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.classifier = Classifier(artifact_dir)
        yield

    app = FastAPI(title="ZELA · Classificação de relatos", version="0.1.0", lifespan=lifespan)
    app.mount("/assets", StaticFiles(directory=STATIC), name="assets")

    @app.get("/", include_in_schema=False)
    def index():
        return FileResponse(STATIC / "index.html")

    @app.get("/evaluation/confusion-matrix.png", include_in_schema=False)
    def confusion_matrix():
        return FileResponse(REPORTS / "confusion_matrix.png")

    @app.get("/health")
    def health(request: Request):
        classifier = request.app.state.classifier
        return {"status": "ok", "model_version": classifier.version}

    @app.get("/model")
    def metadata(request: Request):
        classifier = request.app.state.classifier
        return {"categories": classifier.categories, "metrics": classifier.metrics}

    @app.post("/classify")
    def classify(payload: ClassificationRequest, request: Request):
        try:
            return request.app.state.classifier.predict(payload.text)
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error

    return app


app = create_app()
