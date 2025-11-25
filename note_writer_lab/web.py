from __future__ import annotations

from pathlib import Path
from typing import List

from fastapi import Depends, FastAPI, HTTPException, Request, Form
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.orm import Session

from .db import get_session
from .models import Note, WriterConfig, NoteScore
from .simulator import BridgeRankSimulator
from .grok_client import GrokClient
from .x_client import XClient
from .admission_engine import AdmissionEngine
from .config import settings


BASE_DIR = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

app = FastAPI(title="Community Notes AI Writer Lab")


@app.get("/", response_class=HTMLResponse)
def simulator_home(request: Request):
    return templates.TemplateResponse("simulator_home.html", {"request": request})


@app.post("/simulator/run", response_class=HTMLResponse)
def simulator_run(
    request: Request,
    tweet_url: str = Form(None),
    tweet_text: str = Form(None), # Fallback or for manual entry
    note_text: str = Form(None),
    action: str = Form("check"), # check (practice) or submit (exam)
    fix_mode: bool = Form(False),
    failure_reasons: str = Form(None),
    session: Session = Depends(get_session)
):
    try:
        # Get Writer (simplified)
        writer = session.query(WriterConfig).first()
        if not writer:
            writer = WriterConfig(
                name="Default Writer",
                prompt="You are a Community Notes writer. Write clear, neutral, fact-based notes."
            )
            session.add(writer)
            session.commit()

        # Initialize Engine
        grok = GrokClient(api_key=settings.grok_api_key)
        x_client = XClient()
        engine = AdmissionEngine(session, grok_client=grok, x_client=x_client)

        # 1. Handle Input (URL vs Text)
        tweet_id = "sim_tweet"
        current_tweet_text = tweet_text or "No text provided"
        
        if tweet_url:
            extracted_id = x_client.extract_tweet_id(tweet_url)
            if extracted_id:
                tweet_id = extracted_id
                # Try to fetch text if not provided
                if not tweet_text:
                    fetched_text = x_client.fetch_tweet_text(tweet_id)
                    if fetched_text:
                        current_tweet_text = fetched_text
        
        # 2. Handle Fix Mode (if triggered from results page)
        current_note_text = note_text
        fixed_message = None
        
        if fix_mode and failure_reasons:
            reasons_list = failure_reasons.split(",")
            # Create temp note for fixing
            temp_note = Note(text=note_text, writer_id=writer.id, tweet_id=tweet_id)
            current_note_text = engine.fix_note(temp_note, reasons_list)
            fixed_message = f"Note auto-fixed by agents: {', '.join(reasons_list)}"

        # Create/Update Note
        draft_note = Note(
            writer_id=writer.id,
            tweet_id=tweet_id,
            stage="draft",
            text=current_note_text
        )
        session.add(draft_note)
        session.flush()
        
        result = {}
        
        if action == "submit":
            # Exam Mode
            result = engine.submit_final(draft_note, tweet_id=tweet_id)
        else:
            # Practice Mode (default)
            result = engine.run_practice(draft_note, tweet_id=tweet_id)
        
        # Save Score (if applicable)
        scores = result.get("scores", {})
        if scores:
             note_score = NoteScore(
                note_id=draft_note.id,
                claim_opinion_score=scores.get("claim_opinion_score", 0.0),
                url_validity_score=scores.get("url_validity_score", 0.0),
                harassment_abuse_score=scores.get("harassment_abuse_score", 0.0),
                url_pass=result["passed"],
                raw_payload=result.get("raw_response")
            )
             session.add(note_score)
             session.commit()
        
        return templates.TemplateResponse(
            "simulation_result.html",
            {
                "request": request,
                "tweet_url": tweet_url,
                "tweet_text": current_tweet_text,
                "note_text": current_note_text,
                "result": result,
                "fixed_message": fixed_message,
                "tweet_id": tweet_id,
                "error": result.get("error") # Pass error if present in result
            }
        )
    except Exception as e:
        return templates.TemplateResponse(
            "simulation_result.html",
            {
                "request": request,
                "tweet_url": tweet_url,
                "tweet_text": tweet_text or "Error",
                "note_text": note_text or "Error",
                "error": str(e),
                "result": {"passed": False, "scores": {}, "failure_reasons": ["System Error"], "mode": "error"}
            }
        )
