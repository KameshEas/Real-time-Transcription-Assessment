"""ASGI entrypoint: `uvicorn hinglish.main:app`."""

from hinglish.bootstrap.app import create_app

app = create_app()
