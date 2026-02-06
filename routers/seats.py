from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import List
from datetime import datetime, timedelta
from models import Seat, Booking, User, get_db, SeatStatus
from routers.auth import get_current_user

router = APIRouter(prefix="/api/seats", tags=["seats"])


class SeatResponse(BaseModel):
    id: int
    event_id: int
    zone_name: str
    seat_type: str
    row_label: str
    seat_number: int
    position_x: float
    position_y: float
    price: int
    status: str
    
    class Config:
        from_attributes = True


class LockRequest(BaseModel):
    seat_ids: List[int]


class PayRequest(BaseModel):
    seat_ids: List[int]
    payment_code: str


@router.get("/{event_id}", response_model=List[SeatResponse])
def get_seats(event_id: int, db: Session = Depends(get_db)):
    """
    Public endpoint - Get all seats for an event
    Implements 15-second lazy expiration for locked seats
    """
    print(f"🪑 Fetching seats for event {event_id}")
    
    # LAZY EXPIRATION: Auto-unlock seats that have been locked for more than 15 seconds
    expiration_threshold = datetime.utcnow() - timedelta(seconds=15)
    
    expired_seats = db.query(Seat).filter(
        Seat.event_id == event_id,
        Seat.status == SeatStatus.cart,
        Seat.locked_at.isnot(None),
        Seat.locked_at < expiration_threshold
    ).all()
    
    if expired_seats:
        print(f"⏱️ Auto-unlocking {len(expired_seats)} expired seats")
        for seat in expired_seats:
            seat.status = SeatStatus.available
            seat.locked_by = None
            seat.locked_at = None
        db.commit()
    
    # Get all seats
    seats = db.query(Seat).filter(Seat.event_id == event_id).all()
    
    # Convert enum to string for response
    result = []
    for seat in seats:
        result.append({
            "id": seat.id,
            "event_id": seat.event_id,
            "zone_name": seat.zone_name,
            "seat_type": seat.seat_type.value,
            "row_label": seat.row_label,
            "seat_number": seat.seat_number,
            "position_x": float(seat.position_x) if seat.position_x else 0.0,
            "position_y": float(seat.position_y) if seat.position_y else 0.0,
            "price": seat.price,
            "status": seat.status.value
        })
    
    print(f"✅ Found {len(result)} seats")
    return result


@router.post("/lock")
def lock_seats(request: LockRequest, token: str, db: Session = Depends(get_db)):
    """
    Lock seats for the current user (set status to cart)
    Requires authentication
    """
    print(f"🔒 Locking {len(request.seat_ids)} seats")
    
    # Get current user
    user = get_current_user(token, db)
    
    # Get seats
    seats = db.query(Seat).filter(Seat.id.in_(request.seat_ids)).all()
    
    if len(seats) != len(request.seat_ids):
        raise HTTPException(status_code=404, detail="Some seats not found")
    
    # Check if all seats are available
    for seat in seats:
        if seat.status != SeatStatus.available:
            raise HTTPException(
                status_code=400,
                detail=f"Seat {seat.row_label}-{seat.seat_number} is not available"
            )
    
    # Lock seats (set to cart status with timestamp)
    for seat in seats:
        seat.status = SeatStatus.cart
        seat.locked_by = user.id
        seat.locked_at = datetime.utcnow()
    
    db.commit()
    
    print(f"✅ Locked {len(request.seat_ids)} seats for user {user.id}")
    return {"message": "Seats locked successfully", "seat_ids": request.seat_ids}


@router.post("/unlock")
def unlock_seats(request: LockRequest, token: str, db: Session = Depends(get_db)):
    """
    Unlock seats immediately (set status back to available)
    Used when user deselects seats from cart
    """
    print(f"🔓 Unlocking {len(request.seat_ids)} seats")
    
    # Get current user
    user = get_current_user(token, db)
    
    # Get seats
    seats = db.query(Seat).filter(Seat.id.in_(request.seat_ids)).all()
    
    if len(seats) != len(request.seat_ids):
        raise HTTPException(status_code=404, detail="Some seats not found")
    
    # Unlock seats that are locked by this user
    unlocked_count = 0
    for seat in seats:
        if seat.status == SeatStatus.cart and seat.locked_by == user.id:
            seat.status = SeatStatus.available
            seat.locked_by = None
            seat.locked_at = None
            unlocked_count += 1
        else:
            print(f"⚠️ Seat {seat.id} cannot be unlocked (status: {seat.status}, locked_by: {seat.locked_by}, user: {user.id})")
    
    db.commit()
    
    print(f"✅ Unlocked {unlocked_count} seats")
    return {"message": f"Unlocked {unlocked_count} seats", "unlocked_count": unlocked_count}


@router.post("/pay")
def pay_for_seats(request: PayRequest, token: str, db: Session = Depends(get_db)):
    """
    Process payment for locked seats
    Validates 4-digit code (must be 1212)
    """
    print(f"💳 Processing payment for {len(request.seat_ids)} seats")
    
    # Get current user
    user = get_current_user(token, db)
    
    # Validate payment code
    if request.payment_code != "1212":
        print(f"❌ Invalid payment code: {request.payment_code}")
        raise HTTPException(status_code=400, detail="Invalid payment code")
    
    # Get seats
    seats = db.query(Seat).filter(Seat.id.in_(request.seat_ids)).all()
    
    if len(seats) != len(request.seat_ids):
        raise HTTPException(status_code=404, detail="Some seats not found")
    
    # Verify all seats are locked by this user
    for seat in seats:
        if seat.status != SeatStatus.cart or seat.locked_by != user.id:
            raise HTTPException(
                status_code=400,
                detail=f"Seat {seat.row_label}-{seat.seat_number} is not in your cart"
            )
    
    # Update seats to booked and create bookings
    for seat in seats:
        seat.status = SeatStatus.booked
        
        booking = Booking(
            user_id=user.id,
            seat_id=seat.id,
            payment_code=request.payment_code
        )
        db.add(booking)
    
    db.commit()
    
    print(f"✅ Payment successful for user {user.id}")
    return {"message": "Payment successful", "seat_ids": request.seat_ids}


@router.post("/release")
def release_seats(request: LockRequest, token: str, db: Session = Depends(get_db)):
    """
    Release seats from cart (legacy endpoint, use /unlock instead)
    """
    print(f"🔓 Releasing {len(request.seat_ids)} seats (legacy)")
    
    # Get current user
    user = get_current_user(token, db)
    
    # Get seats
    seats = db.query(Seat).filter(Seat.id.in_(request.seat_ids)).all()
    
    # Release seats that are locked by this user
    released_count = 0
    for seat in seats:
        if seat.status == SeatStatus.cart and seat.locked_by == user.id:
            seat.status = SeatStatus.available
            seat.locked_by = None
            seat.locked_at = None
            released_count += 1
    
    db.commit()
    
    print(f"✅ Released {released_count} seats")
    return {"message": f"Released {released_count} seats"}
