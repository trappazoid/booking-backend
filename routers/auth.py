from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from pydantic import BaseModel, EmailStr
from models import User, get_db
import jwt
from datetime import datetime, timedelta

router = APIRouter(prefix="/api/auth", tags=["auth"])

# JWT Configuration
SECRET_KEY = "your-secret-key-change-in-production"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24  # 24 hours

# Hardcoded admin credentials
ADMIN_EMAIL = "admin@admin.com"
ADMIN_PASSWORD = "Pass-PanelAdmin"


class RegisterRequest(BaseModel):
    name: str
    email: EmailStr
    password: str


class LoginRequest(BaseModel):
    email: str  # Changed from EmailStr to allow the specific admin email format
    password: str


class UserResponse(BaseModel):
    id: int
    name: str
    email: str
    role: str
    
    class Config:
        from_attributes = True


def create_access_token(data: dict):
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt


def get_current_user(token: str, db: Session = Depends(get_db)):
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id: int = payload.get("user_id")
        if user_id is None:
            raise HTTPException(status_code=401, detail="Invalid token")
        user = db.query(User).filter(User.id == user_id).first()
        if user is None:
            raise HTTPException(status_code=401, detail="User not found")
        return user
    except jwt.PyJWTError:
        raise HTTPException(status_code=401, detail="Invalid token")


@router.post("/register")
def register(request: RegisterRequest, db: Session = Depends(get_db)):
    # Check if user already exists
    existing_user = db.query(User).filter(User.email == request.email).first()
    if existing_user:
        raise HTTPException(status_code=400, detail="Email already registered")
    
    # Create new user
    user = User(
        name=request.name,
        email=request.email,
        password=request.password,  # In production, hash this!
        role="user"
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    
    # Generate token
    token = create_access_token({"user_id": user.id})
    
    return {
        "token": token,
        "user": UserResponse.from_orm(user)
    }


@router.post("/login")
def login(request: LoginRequest, db: Session = Depends(get_db)):
    # Check if it's the hardcoded admin
    if request.email == ADMIN_EMAIL and request.password == ADMIN_PASSWORD:
        # Check if admin user exists in DB, create if not
        admin_user = db.query(User).filter(User.email == ADMIN_EMAIL).first()
        if not admin_user:
            admin_user = User(
                name="Admin",
                email=ADMIN_EMAIL,
                password=ADMIN_PASSWORD,
                role="admin"
            )
            db.add(admin_user)
            db.commit()
            db.refresh(admin_user)
        
        token = create_access_token({"user_id": admin_user.id})
        return {
            "token": token,
            "user": UserResponse.from_orm(admin_user)
        }
    
    # Regular user login
    user = db.query(User).filter(User.email == request.email).first()
    if not user or user.password != request.password:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    
    token = create_access_token({"user_id": user.id})
    
    return {
        "token": token,
        "user": UserResponse.from_orm(user)
    }


@router.get("/me")
def get_me(token: str, db: Session = Depends(get_db)):
    user = get_current_user(token, db)
    return UserResponse.from_orm(user)
