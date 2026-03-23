"""
HRV Biofeedback Control Panel — Entry Point.
Launches the FastAPI server via uvicorn.
"""

import uvicorn


def main():
    uvicorn.run(
        "app:app",
        host="0.0.0.0",
        port=8000,
        reload=False,
        log_level="info",
    )


if __name__ == "__main__":
    main()
