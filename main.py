import os
from contextlib import asynccontextmanager
from fastapi.staticfiles import StaticFiles
from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException
import uvicorn
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
from core.database import engine, AsyncSessionLocal, Base
from core.config import settings
from routers import routes
from services.moderator_service import get_moderator_by_email, create_moderator
from services.blocking_reason_service import seed_blocking_reasons
from schemas.moderator import ModeratorCreateRequest, ModeratorRole
from core.errors import error_code_for_status

load_dotenv()


@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        async with AsyncSessionLocal() as db:
            admin = await get_moderator_by_email(db, settings.ADMIN_EMAIL)
            if not admin:
                await create_moderator(
                    db,
                    ModeratorCreateRequest(
                        email=settings.ADMIN_EMAIL,
                        password=settings.ADMIN_PASSWORD,
                        first_name="Admin",
                        last_name="Moderator",
                        role=ModeratorRole.ADMIN,
                    ),
                    is_admin=True,
                )
            elif not admin.is_admin:
                admin.is_admin = True
            await seed_blocking_reasons(db)
            await db.commit()
    except Exception as e:
        print(f"Failed to initialize database: {e}")
        if settings.ENV == "production":
            raise

    print("Application started successfully")

    yield

    await engine.dispose()


app = FastAPI(
    title="NEO Moderation", version="1.0.0",
    lifespan=lifespan, debug=settings.DEBUG
)


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(_, exc: StarletteHTTPException):
    if isinstance(exc.detail, dict) and "code" in exc.detail and "message" in exc.detail:
        payload = exc.detail
    else:
        payload = {
            "code": error_code_for_status(exc.status_code),
            "message": str(exc.detail) if exc.detail else "HTTP error",
        }
    return JSONResponse(status_code=exc.status_code, content=payload)


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(_, exc: RequestValidationError):
    return JSONResponse(
        status_code=400,
        content={
            "code": "BAD_REQUEST",
            "message": "Validation error",
            "details": {"errors": exc.errors()},
        },
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(_, __):
    return JSONResponse(
        status_code=500,
        content={"code": "INTERNAL_ERROR", "message": "Internal server error"},
    )

app.add_middleware(
    CORSMiddleware,
    allow_origins=['http://localhost:5173'],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


for router in routes:
    app.include_router(router, prefix="/api")

os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
app.mount("/uploads", StaticFiles(directory=settings.UPLOAD_DIR), name="uploads")

if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host=settings.APP_HOST,
        port=settings.APP_PORT,
        reload=settings.APP_RELOAD,
        log_level=settings.APP_LOG_LEVEL.lower()
    )
