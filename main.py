from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from models import init_db
from routers import auth, events, seats

# Initialize FastAPI app
app = FastAPI(title="Cinema/Concert Booking API")

# CRITICAL: CORS must be added IMMEDIATELY after app creation
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Vite and Create React App
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount static files directory
app.mount("/static", StaticFiles(directory="static"), name="static")

# Include routers
app.include_router(auth.router)
app.include_router(events.router)
app.include_router(seats.router)

# Initialize database on startup
@app.on_event("startup")
def startup_event():
    init_db()
    print("✅ Database initialized successfully")
    print("🚀 Server running on http://localhost:8000")


@app.get("/")
def root():
    return {"message": "Cinema/Concert Booking API", "status": "running"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
