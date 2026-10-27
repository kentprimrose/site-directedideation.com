"""Local FastAPI development scaffold."""

from fastapi import FastAPI

app = FastAPI(title="site-directedideation.com API")


@app.get("/")
def hello_world() -> dict[str, str]:
    """Return a greeting."""
    return {"message": "Hello, world!"}
