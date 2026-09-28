"""FastAPI application factory and server entry point."""

from fastapi import FastAPI

from app.routes.router import router


def create_app() -> FastAPI:
    """Construct the API and register its public and protected routers."""
    application = FastAPI(
        title="Slack Support Assistant",
        version="0.1.0",
        description="Standalone spreadsheet-backed support assistant.",
    )
    application.include_router(router)
    return application


app = create_app()
