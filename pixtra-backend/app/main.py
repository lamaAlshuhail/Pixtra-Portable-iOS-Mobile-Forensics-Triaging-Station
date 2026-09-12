from contextlib import asynccontextmanager
from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.routers import auth, cases, devices, acquisitions, analysis, reports, sim
from app.routers.auth import get_current_examiner
from app.services.database import init_db
from app.services.device_profiles import load_device_profiles

import subprocess
import sys


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    load_device_profiles()
    yield


app = FastAPI(
    title="Pixtra",
    description="Mobile forensics acquisition and analysis platform",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:5173", "http://127.0.0.1:*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

_AUTHED = [Depends(get_current_examiner)]

app.include_router(auth.router, prefix="/api/auth", tags=["Auth"])
app.include_router(cases.router, prefix="/api/cases", tags=["Cases"], dependencies=_AUTHED)
app.include_router(devices.router, prefix="/api/devices", tags=["Devices"], dependencies=_AUTHED)
app.include_router(acquisitions.router, prefix="/api/acquisitions", tags=["Acquisitions"], dependencies=_AUTHED)
app.include_router(analysis.router, prefix="/api/analysis", tags=["Analysis"], dependencies=_AUTHED)
app.include_router(reports.router, prefix="/api/reports", tags=["Reports"], dependencies=_AUTHED)
app.include_router(sim.router, prefix="/api/sim", tags=["SIM"], dependencies=_AUTHED)


@app.get("/api/health")
async def health():
    import shutil
    tools = {}

    try:
        r = subprocess.run(
            [sys.executable, "-m", "pymobiledevice3", "--version"],
            capture_output=True, text=True, timeout=5,
        )
        tools["pymobiledevice3"] = {
            "installed": r.returncode == 0,
            "version": r.stdout.strip() if r.returncode == 0 else None,
        }
    except Exception:
        tools["pymobiledevice3"] = {"installed": False, "version": None}

    adb_path = shutil.which("adb")
    if adb_path:
        try:
            r = subprocess.run(["adb", "version"], capture_output=True, text=True, timeout=5)
            ver = r.stdout.split("\n")[0] if r.returncode == 0 else None
            tools["adb"] = {"installed": True, "version": ver, "path": adb_path}
        except Exception:
            tools["adb"] = {"installed": True, "version": None, "path": adb_path}
    else:
        tools["adb"] = {"installed": False, "version": None}

    tools["palera1n"] = {"installed": shutil.which("palera1n") is not None}

    tools["irecovery"] = {"installed": shutil.which("irecovery") is not None}

    return {
        "status": "ok",
        "version": "0.1.0",
        "platform": "pixtra",
        "tools": tools,
    }


import os
from fastapi.responses import FileResponse

STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")
INDEX_HTML = os.path.join(STATIC_DIR, "index.html")

if os.path.isdir(STATIC_DIR):
    assets_dir = os.path.join(STATIC_DIR, "assets")
    if os.path.isdir(assets_dir):
        app.mount("/assets", StaticFiles(directory=assets_dir), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    async def spa_fallback(full_path: str):
        if full_path.startswith("api/"):
            raise HTTPException(status_code=404, detail="Not Found")
        if full_path:
            candidate = os.path.join(STATIC_DIR, full_path)
            if os.path.isfile(candidate):
                return FileResponse(candidate)
        return FileResponse(INDEX_HTML)
