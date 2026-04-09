from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from models import init_db
from config import ALLOWED_ORIGINS
from routes.schedule import router as schedule_router
from routes.registration import router as registration_router
from routes.rental import router as rental_router

app = FastAPI(title="Garcia Folklorico Studio API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(schedule_router, prefix="/api", tags=["schedule"])
app.include_router(registration_router, prefix="/api", tags=["registration"])
app.include_router(rental_router, prefix="/api", tags=["rental"])


@app.on_event("startup")
def startup():
    init_db()


@app.get("/api/health")
def health():
    return {"status": "ok"}
