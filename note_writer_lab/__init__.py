"""
Core package for the Community Notes AI Writer Lab.

This package provides:
- DB models and session helpers
- Clients for X (Community Notes) and Grok
- The lab pipeline that generates, scores, optionally rewrites, and submits notes
- A small FastAPI-based dashboard for per-writer metrics
"""

__all__ = [
    "config",
    "db",
    "models",
    "x_client",
    "grok_client",
    "evaluator",
    "lab_runner",
]

