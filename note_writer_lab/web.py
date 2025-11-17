from __future__ import annotations

from pathlib import Path
from typing import List

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.orm import Session

from .db import get_session
from .metrics import WriterDashboard, build_writer_dashboard
from .models import WriterConfig


BASE_DIR = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

app = FastAPI(title="Community Notes AI Writer Lab")


@app.get("/", response_class=HTMLResponse)
def writers_index(
    request: Request, session: Session = Depends(get_session)
) -> HTMLResponse:
    writers: List[WriterConfig] = list(
        session.scalars(select(WriterConfig).order_by(WriterConfig.id.asc()))
    )
    dashboards: List[WriterDashboard] = [
        build_writer_dashboard(session, w, recent_limit=5) for w in writers
    ]
    return templates.TemplateResponse(
        "writers.html",
        {
            "request": request,
            "dashboards": dashboards,
        },
    )


@app.get("/writers/{writer_id}", response_class=HTMLResponse)
def writer_detail(
    writer_id: int, request: Request, session: Session = Depends(get_session)
) -> HTMLResponse:
    writer = session.get(WriterConfig, writer_id)
    if writer is None:
        raise HTTPException(status_code=404, detail="Writer not found")

    dashboard = build_writer_dashboard(session, writer, recent_limit=50)
    return templates.TemplateResponse(
        "writer_detail.html",
        {
            "request": request,
            "dashboard": dashboard,
        },
    )


