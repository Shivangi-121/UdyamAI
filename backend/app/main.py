from contextlib import asynccontextmanager
import logging

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from starlette.middleware.cors import CORSMiddleware

from app.api.routes import router
from app.core.config import get_settings
from app.db.session import engine
from app.services.csv_data import MAX_CSV_BYTES

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
logger = logging.getLogger("udyamai")
settings = get_settings()


@asynccontextmanager
async def lifespan(_: FastAPI):
    if settings.app_env.lower() == "production":
        try:
            with engine.connect() as connection:
                connection.execute(text("SELECT 1"))
        except SQLAlchemyError:
            logger.error("Production database startup check failed; verify DATABASE_URL and database availability.")
            raise RuntimeError("Production database connectivity check failed.") from None
    yield


app = FastAPI(
    title="UdyamAI API",
    version="0.3.0",
    description="Merchant-first business records, transparent calculations, and assistant APIs.",
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-CSRF-Token"],
    expose_headers=["Content-Disposition"],
)


@app.middleware("http")
async def limit_request_size(request: Request, call_next):
    content_length = request.headers.get("content-length")
    if content_length:
        try:
            max_bytes = (
                settings.sarvam_max_audio_bytes + 65_536
                if request.url.path.endswith("/assistant/voice")
                else MAX_CSV_BYTES + 65_536
                if request.url.path.endswith(("/imports/preview", "/imports/confirm"))
                else settings.max_request_bytes
            )
            too_large = int(content_length) > max_bytes
        except ValueError:
            return JSONResponse(status_code=400, content={"error": "invalid_content_length", "message": "Invalid content length."})
        if too_large:
            return JSONResponse(status_code=413, content={"error": "request_too_large", "message": "Request body exceeds the configured size limit."})
    return await call_next(request)


@app.exception_handler(HTTPException)
async def http_error_handler(request: Request, exc: HTTPException):
    message = exc.detail if isinstance(exc.detail, str) else "The request could not be completed."
    return JSONResponse(
        status_code=exc.status_code,
        headers=exc.headers,
        content={"error": "request_failed", "message": message},
    )


@app.exception_handler(RequestValidationError)
async def validation_error_handler(request: Request, exc: RequestValidationError):
    return JSONResponse(
        status_code=422,
        content={
            "error": "validation_error",
            "message": "Request data did not pass validation.",
            "details": [
                {"location": error.get("loc", []), "message": error.get("msg", "Invalid value"), "type": error.get("type", "value_error")}
                for error in exc.errors()
            ],
        },
    )


@app.exception_handler(Exception)
async def unexpected_error_handler(request: Request, exc: Exception):
    logger.exception("Unhandled request error on %s", request.url.path)
    return JSONResponse(status_code=500, content={"error": "internal_error", "message": "The request could not be completed."})


@app.get("/")
def root():
    return {"name": "UdyamAI API", "docs": "/docs", "health": "/api/health"}


app.include_router(router)
