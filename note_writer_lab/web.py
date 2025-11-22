from __future__ import annotations

from pathlib import Path
from typing import List

from fastapi import Depends, FastAPI, HTTPException, Request, Form
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.orm import Session

from .db import get_session
from .models import Note, WriterConfig
from .simulator import BridgeRankSimulator


BASE_DIR = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

app = FastAPI(title="Community Notes AI Writer Lab")


@app.get("/", response_class=HTMLResponse)
def simulator_home(request: Request):
    return templates.TemplateResponse("simulator_home.html", {"request": request})


@app.post("/simulator/run", response_class=HTMLResponse)
def simulator_run(
    request: Request,
    tweet_text: str = Form(...),
    note_text: str = Form(None),
    session: Session = Depends(get_session)
):
    from .grok_client import GrokClient
    from .researcher import GroundingClient
    from .models import Tweet, Note
    
    # Create a dummy tweet object
    tweet = Tweet(tweet_id="sim_tweet", text=tweet_text)
    
    grok = GrokClient()
    simulator = BridgeRankSimulator(session, grok_client=grok)
    
    candidate_notes = []
    
    # Ensure writer exists
    writer = session.scalars(select(WriterConfig)).first()
    if not writer:
         writer = WriterConfig(name="Simulator User", prompt="Default")
         session.add(writer)
         session.flush()

    # Ensure tweet exists in DB for FK
    db_tweet = session.scalar(select(Tweet).where(Tweet.tweet_id == "sim_tweet"))
    if not db_tweet:
        db_tweet = Tweet(tweet_id="sim_tweet", text=tweet_text)
        session.add(db_tweet)
    else:
        # Update text if it changed
        db_tweet.text = tweet_text
    session.flush()

    if note_text:
        # User provided a specific note draft
        draft_note = Note(
            writer_id=writer.id,
            tweet_id="sim_tweet",
            stage="draft",
            text=note_text
        )
        session.add(draft_note)
        session.flush()
        
        simulation_run = simulator.run_simulation(draft_note)
        
        candidate_notes.append({
            "note": draft_note,
            "score": simulation_run.bridge_score,
            "run": simulation_run
        })
        
    else:
        # Legacy/Variant Mode (if note_text is missing)
        variants = grok.generate_note_variants(tweet)
        if not variants:
            variants = [{"strategy": "Default", "text": "Could not generate variants."}]
            
        for variant in variants:
            text = variant.get("text", "")
            draft_note = Note(
                writer_id=writer.id,
                tweet_id="sim_tweet",
                stage="draft",
                text=text
            )
            session.add(draft_note)
            session.flush()
            
            simulation_run = simulator.run_simulation(draft_note)
            
            candidate_notes.append({
                "note": draft_note,
                "score": simulation_run.bridge_score,
                "run": simulation_run
            })
            
    # Always refine the best (or only) note to show improvements
    candidate_notes.sort(key=lambda x: x["score"], reverse=True)
    best_original = candidate_notes[0]
    
    refined_note = simulator.run_refiner(best_original["note"], best_original["run"])
    refined_run = simulator.run_simulation(refined_note)
    
    return templates.TemplateResponse(
        "simulation_result.html",
        {
            "request": request,
            "tweet_text": tweet_text,
            "original_note": best_original["note"].text,
            "bridge_score": best_original["score"],
            "consensus_status": best_original["run"].consensus_status,
            "feedbacks": best_original["run"].persona_feedbacks,
            
            "refined_note": refined_note.text,
            "refined_score": refined_run.bridge_score,
            "refined_feedbacks": refined_run.persona_feedbacks
        }
    )
    

