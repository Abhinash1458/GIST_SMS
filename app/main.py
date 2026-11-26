from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.config import settings
from app.database import create_db_and_tables
from app.routers.auth import router as auth_router
from app.routers.register import router as register_router
from app.routers.hod import router as hod_router
from app.routers.management import router as management_router
from app.routers.mentor import router as mentor_router
from app.routers.student import router as student_router
from app.routers.trainer import router as trainer_router
from app.services.role_menus import ROLE_HOME, build_role_menu
from app.admin import setup_admin


BASE_DIR = Path(__file__).resolve().parent.parent

STATIC_DIR = BASE_DIR / "app" / "static"
TEMPLATES_DIR = BASE_DIR / "app" / "templates"


@asynccontextmanager
async def lifespan(app: FastAPI):
    create_db_and_tables()
    print(f"{settings.APP_NAME} started successfully!")
    yield
    print("Application shutting down...")


app = FastAPI(
    title=settings.APP_NAME,
    lifespan=lifespan
)

app.mount(
    "/static",
    StaticFiles(directory=str(STATIC_DIR)),
    name="static"
)

templates = Jinja2Templates(
    directory=str(TEMPLATES_DIR)
)

app.state.templates = templates


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(
    request: Request, exc: StarletteHTTPException
):
    """Render a friendly page for 403s; keep other status codes/headers."""
    if exc.status_code == 403:
        current_user = getattr(request.state, "current_user", None)
        role = (
            current_user.role.value
            if current_user is not None
            else None
        )
        return templates.TemplateResponse(
            request=request,
            name="403.html",
            context={
                "title": "Access Denied",
                "app_name": settings.APP_NAME,
                "current_user": current_user,
                "menu_links": build_role_menu(role) if role else [],
                "role_home": ROLE_HOME.get(role, "/login"),
                "message": (
                    exc.detail
                    if exc.detail
                    else "You do not have permission to access this page."
                ),
            },
            status_code=403,
        )

    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail},
        headers=exc.headers,
    )


# Register existing authentication routes
app.include_router(auth_router)

# Register public student registration routes
app.include_router(register_router)

# Register HOD approval routes
app.include_router(hod_router)

# Register Management dashboard (the only role that links to SQLADMIN)
app.include_router(management_router)

# Register the remaining role-specific dashboards
app.include_router(mentor_router)
app.include_router(trainer_router)
app.include_router(student_router)

# Mount SQLADMIN at /admin with its own signed session
setup_admin(app, templates, str(TEMPLATES_DIR))


@app.get("/health")
def health_check():
    return {"status": "ok"}


@app.get("/")
def home():
    return RedirectResponse(
        url="/login",
        status_code=302
    )
