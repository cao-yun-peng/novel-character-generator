"""Read-only web application services (milestone A: snapshot/evidence browsing)."""

from .app import create_app
from .repository import RunRepository, RunSpec, WebRunError
from .service import WebService

__all__ = ["create_app", "RunRepository", "RunSpec", "WebRunError", "WebService"]
