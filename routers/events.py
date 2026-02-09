from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from sqlalchemy.orm import Session
from sqlalchemy import desc
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime
from models import Event, Venue, Seat, User, get_db, SeatType, SeatStatus
from routers.auth import get_current_user
import json
import shutil
from pathlib import Path

router = APIRouter(prefix="/api/events", tags=["events"])


class EventResponse(BaseModel):
    id: int
    title: str
    description: Optional[str]
    date: datetime
    poster_url: Optional[str]
    venue_id: Optional[int]
    
    class Config:
        from_attributes = True


class EventDetailResponse(BaseModel):
    id: int
    title: str
    description: Optional[str]
    date: datetime
    poster_url: Optional[str]
    venue_id: Optional[int]
    venue_schema: Optional[dict] = None
    
    class Config:
        from_attributes = True


class PaginatedEventsResponse(BaseModel):
    events: List[EventResponse]
    total: int
    page: int
    per_page: int
    total_pages: int


@router.get("/", response_model=PaginatedEventsResponse)
def get_events(page: int = 1, per_page: int = 10, db: Session = Depends(get_db)):
    """
    Public endpoint - Get paginated list of events
    No authentication required
    """
    print(f"📋 Fetching events - Page {page}, Per page {per_page}")
    
    # Calculate offset
    offset = (page - 1) * per_page
    
    # Get total count
    total = db.query(Event).count()
    
    # Get events sorted by date descending (newest first)
    events = db.query(Event).order_by(desc(Event.date)).offset(offset).limit(per_page).all()
    
    total_pages = (total + per_page - 1) // per_page  # Ceiling division
    
    print(f"✅ Found {len(events)} events (Total: {total})")
    
    return {
        "events": events,
        "total": total,
        "page": page,
        "per_page": per_page,
        "total_pages": total_pages
    }


@router.get("/{event_id}")
def get_event(event_id: int, db: Session = Depends(get_db)):
    """
    Public endpoint - Get event details by ID
    No authentication required - guests can view events
    """
    print(f"🔍 Fetching event with ID: {event_id}")
    
    # Query event from database
    event = db.query(Event).filter(Event.id == event_id).first()
    
    # Return 404 if not found
    if not event:
        print(f"❌ Event {event_id} not found")
        raise HTTPException(status_code=404, detail="Event not found")
    
    print(f"✅ Event found: {event.title}")
    
    # Build response manually to avoid serialization issues
    venue_schema = None
    if event.venue and event.venue.schema_json:
        try:
            venue_schema = json.loads(event.venue.schema_json)
            print(f"✅ Venue schema loaded ({len(venue_schema.get('zones', []))} zones)")
        except Exception as e:
            print(f"⚠️ Warning: Could not parse venue schema: {e}")
            venue_schema = None
    
    # Return plain dict response
    response = {
        "id": event.id,
        "title": event.title,
        "description": event.description,
        "date": event.date.isoformat() if event.date else None,
        "poster_url": event.poster_url,
        "venue_id": event.venue_id,
        "venue_schema": venue_schema
    }
    
    print(f"✅ Returning event data for: {event.title}")
    return response


@router.post("/", response_model=EventResponse)
async def create_event(
    title: str = Form(...),
    description: str = Form(...),
    date: str = Form(...),  # ISO format datetime string
    venue_schema: str = Form(...),  # JSON string of seat zones
    poster: UploadFile = File(None),
    schematic: UploadFile = File(None),
    token: str = Form(...),
    db: Session = Depends(get_db)
):
    """
    Admin-only endpoint - Create new event
    Requires authentication token
    """
    print(f"📝 Creating new event: {title}")
    
    # Verify user is admin
    user = get_current_user(token, db)
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    
    # Parse date
    try:
        event_date = datetime.fromisoformat(date.replace('Z', '+00:00'))
    except:
        raise HTTPException(status_code=400, detail="Invalid date format")
    
    # Save uploaded files
    poster_url = None
    schematic_url = None
    upload_dir = Path("static/uploads")
    upload_dir.mkdir(parents=True, exist_ok=True)
    
    if poster:
        poster_filename = f"{datetime.now().timestamp()}_{poster.filename}"
        poster_path = upload_dir / poster_filename
        with poster_path.open("wb") as buffer:
            shutil.copyfileobj(poster.file, buffer)
        poster_url = f"/static/uploads/{poster_filename}"
        print(f"✅ Poster saved: {poster_url}")
    
    if schematic:
        schematic_filename = f"{datetime.now().timestamp()}_{schematic.filename}"
        schematic_path = upload_dir / schematic_filename
        with schematic_path.open("wb") as buffer:
            shutil.copyfileobj(schematic.file, buffer)
        schematic_url = f"/static/uploads/{schematic_filename}"
        print(f"✅ Schematic saved: {schematic_url}")
    
    # Create venue
    venue = Venue(
        name=f"Venue for {title}",
        schematic_url=schematic_url,
        schema_json=venue_schema
    )
    db.add(venue)
    db.commit()
    db.refresh(venue)
    print(f"✅ Venue created with ID: {venue.id}")
    
    # Create event
    event = Event(
        title=title,
        description=description,
        date=event_date,
        poster_url=poster_url,
        venue_id=venue.id
    )
    db.add(event)
    db.commit()
    db.refresh(event)
    print(f"✅ Event created with ID: {event.id}")
    
    # Parse venue schema and create seats
    try:
        schema = json.loads(venue_schema)
        seats_to_create = []
        
        for zone in schema.get("zones", []):
            zone_name = zone.get("name", "Unknown")
            seat_type = SeatType[zone.get("type", "sitting")]
            rows = zone.get("rows", 0)
            cols = zone.get("cols", 0)
            row_label = zone.get("rowLabel", "")
            start_row = zone.get("startRowIndex", 1)
            start_seat = zone.get("startSeatIndex", 1)
            price = zone.get("price", 1000)  # Default price in cents
            positions = zone.get("positions", [])  # Array of {x, y} positions
            
            idx = 0
            for r in range(rows):
                for c in range(cols):
                    pos_x = positions[idx]["x"] if idx < len(positions) else 0
                    pos_y = positions[idx]["y"] if idx < len(positions) else 0
                    
                    seat = Seat(
                        event_id=event.id,
                        zone_name=zone_name,
                        seat_type=seat_type,
                        row_label=f"{row_label}{start_row + r}",
                        seat_number=start_seat + c,
                        position_x=pos_x,
                        position_y=pos_y,
                        price=price,
                        status=SeatStatus.available
                    )
                    seats_to_create.append(seat)
                    idx += 1
        
        db.bulk_save_objects(seats_to_create)
        db.commit()
        print(f"✅ Created {len(seats_to_create)} seats")
    except Exception as e:
        # If seat creation fails, still return the event
        print(f"⚠️ Error creating seats: {e}")
    
    print(f"✅ Event '{title}' created successfully")
    return EventResponse.from_orm(event)


@router.delete("/{event_id}")
def delete_event(event_id: int, token: str, db: Session = Depends(get_db)):
    """
    Admin-only endpoint - Delete event by ID
    """
    print(f"🗑️ Deleting event with ID: {event_id}")

    # If this admin
    user = get_current_user(token, db)
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")

    # 2. find event
    event = db.query(Event).filter(Event.id == event_id).first()
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")

    # 3. delete event
    try:
        db.delete(event)
        db.commit()
        print(f"✅ Event {event_id} deleted successfully")
        return {"message": "Event deleted successfully"}
    except Exception as e:
        db.rollback()
        print(f"❌ Error deleting event: {e}")
        raise HTTPException(status_code=500, detail=str(e))
