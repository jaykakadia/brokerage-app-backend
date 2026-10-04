# Entry point for cPanel "Setup Python App" (Phusion Passenger), which only speaks WSGI.
# a2wsgi wraps the FastAPI ASGI app so Passenger can serve it.
import os
import sys

APP_ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, APP_ROOT)
# Settings load ".env" relative to the working directory, so run from the app root.
os.chdir(APP_ROOT)

from a2wsgi import ASGIMiddleware  # noqa: E402

from app.main import app as asgi_app  # noqa: E402

application = ASGIMiddleware(asgi_app)
