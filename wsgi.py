"""Legacy entrypoint removed in FastAPI migration.
Run: uvicorn app.main:app --host 0.0.0.0 --port 8000
"""

raise RuntimeError("wsgi.py is deprecated. Use app.main:app with uvicorn")
