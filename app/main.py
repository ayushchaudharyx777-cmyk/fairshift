import time
import json
import logging
from datetime import datetime, timezone
from collections import defaultdict
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response, HTTPException, status
from fastapi.responses import JSONResponse, HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.repository import get_repository
from app.seed import seed_database
from app.routers import worker, admin, passport

# Configure Structured Logging
logger = logging.getLogger("fairshift")
logging.basicConfig(
    level=logging.INFO,
    format="%(message)s"
)


# In-memory Rate Limiter for AI endpoints: max 30 requests / 60 seconds per IP
AI_RATE_LIMIT_MAX = 30
AI_RATE_LIMIT_WINDOW = 60.0
_ip_request_timestamps: dict[str, list[float]] = defaultdict(list)


def check_rate_limit(ip: str) -> bool:
    now = time.time()
    timestamps = _ip_request_timestamps[ip]
    # Prune expired
    _ip_request_timestamps[ip] = [t for t in timestamps if now - t < AI_RATE_LIMIT_WINDOW]
    if len(_ip_request_timestamps[ip]) >= AI_RATE_LIMIT_MAX:
        return False
    _ip_request_timestamps[ip].append(now)
    return True


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: Seed in-memory database with sites, workers, shifts, reports, and passports
    repo = get_repository()
    seed_database(repo)
    logger.info(json.dumps({
        "event": "startup_complete",
        "sites_count": len(repo.sites),
        "workers_count": len(repo.workers),
        "shifts_count": len(repo.shifts),
        "message": "FairShift initialized successfully with seeded datasets."
    }))
    yield
    logger.info(json.dumps({"event": "shutdown", "message": "FairShift server terminating."}))


app = FastAPI(
    title="FairShift API",
    description="UN SDG 8 Decent Work Platform for Shift Workers in Construction & Healthcare",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan
)

# CORS
settings = get_settings()
app.add_middleware(
    CORSMiddleware,
    allow_origins=[s.strip() for s in settings.ALLOWED_ORIGINS.split(",") if s.strip()] or ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Middleware 1: Structured JSON Logging & Security Headers & Rate Limiting
@app.middleware("http")
async def app_middleware(request: Request, call_next):
    start_time = time.time()
    client_ip = request.client.host if request.client else "unknown"

    # Enforce AI rate limit on compute-heavy endpoints
    if request.url.path in ["/api/v1/worker/payslip/explain", "/api/v1/worker/safety-reports"] and request.method == "POST":
        if not check_rate_limit(client_ip):
            return JSONResponse(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                content={
                    "error": {
                        "code": "RATE_LIMIT_EXCEEDED",
                        "message": "Too many requests to AI endpoints. Please wait a moment."
                    }
                }
            )

    try:
        response: Response = await call_next(request)
    except Exception as exc:
        duration_ms = round((time.time() - start_time) * 1000, 2)
        logger.error(json.dumps({
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "method": request.method,
            "path": request.url.path,
            "status": 500,
            "duration_ms": duration_ms,
            "client_ip": client_ip,
            "error": str(exc)
        }))
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={
                "error": {
                    "code": "INTERNAL_SERVER_ERROR",
                    "message": "An unexpected server error occurred. Please try again."
                }
            }
        )

    duration_ms = round((time.time() - start_time) * 1000, 2)

    # Structured JSON log line
    logger.info(json.dumps({
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "method": request.method,
        "path": request.url.path,
        "status": response.status_code,
        "duration_ms": duration_ms,
        "client_ip": client_ip
    }))

    # Security Headers
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; "
        "script-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
        "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
        "font-src 'self' https://fonts.gstatic.com data:; "
        "img-src 'self' data: https:; "
        "connect-src 'self' *;"
    )

    return response


# Global Exception Handler (Never return raw stack traces)
@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": {
                "code": f"HTTP_{exc.status_code}",
                "message": exc.detail
            }
        }
    )


@app.exception_handler(Exception)
async def generic_exception_handler(request: Request, exc: Exception):
    logger.exception("Unhandled application exception")
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "error": {
                "code": "INTERNAL_ERROR",
                "message": "A server error occurred. Please contact support."
            }
        }
    )


# Health Check Endpoint
@app.get("/health", tags=["Health"])
async def health_check():
    return {
        "status": "ok",
        "service": "FairShift",
        "version": "1.0.0",
        "timestamp": datetime.now(timezone.utc).isoformat()
    }


# Include Versioned API Routers
app.include_router(worker.router)
app.include_router(admin.router)
app.include_router(passport.router)

# Mount Static Files
app.mount("/static", StaticFiles(directory="static"), name="static")


# HTML Page Serving Routes
@app.get("/", response_class=HTMLResponse, tags=["Pages"])
async def serve_landing():
    return FileResponse("static/index.html")


@app.get("/worker", response_class=HTMLResponse, tags=["Pages"])
async def serve_worker_app():
    return FileResponse("static/worker.html")


@app.get("/admin", response_class=HTMLResponse, tags=["Pages"])
async def serve_admin_dashboard():
    return FileResponse("static/admin.html")


@app.get("/passport/{token}", response_class=HTMLResponse, tags=["Pages"])
async def serve_passport_page(token: str):
    return FileResponse("static/passport.html")
