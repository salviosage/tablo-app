from fastapi import APIRouter

router = APIRouter()


@router.get("/status")
async def status():
    """API status check."""
    return {
        "service": "tablo-api",
        "status": "running",
        "features": {
            "intake": False,
            "extractors": False,
            "normalize": False,
            "reconcile": False,
            "dashboard": False,
        },
    }