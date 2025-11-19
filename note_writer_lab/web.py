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
from .models import Note, WriterConfig
from .simulator import BridgeRankSimulator


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



@app.post("/simulate/{note_id}")
def run_simulation(
    note_id: int, request: Request, session: Session = Depends(get_session)
):
    note = session.get(Note, note_id)
    if not note:
        raise HTTPException(status_code=404, detail="Note not found")

    simulator = BridgeRankSimulator(session)
    
    # 1. Architect
    architect_output = simulator.run_architect(note.tweet.text)
    
    # 2. Simulator
    simulator.run_simulation(note, architect_output.personas)
    
    # Redirect back to writer detail
    return HTMLResponse(
        status_code=303, headers={"Location": f"/writers/{note.writer_id}"}
    )


@app.post("/refine/{note_id}")
def run_refinement(
    note_id: int, request: Request, session: Session = Depends(get_session)
):
    note = session.get(Note, note_id)
    if not note:
        raise HTTPException(status_code=404, detail="Note not found")
    
    # Get the latest simulation
    if not note.simulations:
         raise HTTPException(status_code=400, detail="No simulation found for this note")
    
    simulation = note.simulations[-1] # Get latest
    
    simulator = BridgeRankSimulator(session)
    simulator.run_refiner(note, simulation)
    
    return HTMLResponse(
        status_code=303, headers={"Location": f"/writers/{note.writer_id}"}
    )
