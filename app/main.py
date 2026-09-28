"""FastAPI application factory and server entry point."""

from fastapi import FastAPI

from app.views.router import router


def create_app() -> FastAPI:
    application = FastAPI(
        title="Slack Support Assistant",
        version="0.1.0",
        description="Standalone support assistant — scaffold baseline.",
    )
    application.include_router(router)
    return application


app = create_app()
