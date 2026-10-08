from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.dependencies import get_current_admin, get_db
from app.db.models.location import Location
from app.db.models.user import User
from app.schemas.common import APIResponse, MessageResponse
from app.schemas.location import LocationRead, LocationCreate, LocationUpdate

router = APIRouter(prefix="/api/v1/locations", tags=["Locations"])


@router.get("/cities", response_model=APIResponse[List[str]])
def get_cities(db: Session = Depends(get_db)):
    cities = db.query(Location.city_name).distinct().all()
    city_list = [c[0] for c in cities if c[0]]
    if not city_list:
        # Default NCR locations if empty
        city_list = ["Palwal", "Faridabad", "Gurugram", "Sonipat", "Hodal", "Delhi"]
    return APIResponse(status="success", data=city_list)


@router.get("", response_model=APIResponse[List[LocationRead]])
def get_locations(db: Session = Depends(get_db)):
    locations = db.query(Location).order_by(Location.city_name.asc()).all()
    return APIResponse(status="success", data=[LocationRead.model_validate(l) for l in locations])


@router.post("", response_model=APIResponse[LocationRead])
def create_location(
    req: LocationCreate,
    admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db)
):
    location = Location(
        city_name=req.city_name.strip(),
        state=req.state.strip(),
        category=req.category,
        latitude=req.latitude,
        longitude=req.longitude
    )
    db.add(location)
    db.commit()
    db.refresh(location)
    return APIResponse(status="success", data=LocationRead.model_validate(location))


@router.put("/{location_id}", response_model=APIResponse[LocationRead])
def update_location(
    location_id: int,
    req: LocationUpdate,
    admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db)
):
    loc = db.query(Location).filter(Location.id == location_id).first()
    if not loc:
        raise HTTPException(status_code=404, detail="Location not found.")
    if req.city_name is not None:
        name = req.city_name.strip()
        if not name:
            raise HTTPException(status_code=400, detail="City name is required.")
        if len(name) > 100:
            raise HTTPException(status_code=400, detail="City name cannot exceed 100 characters.")
        loc.city_name = name
    if req.state is not None:
        loc.state = req.state.strip()
    if req.category is not None:
        loc.category = req.category
    if req.latitude is not None:
        loc.latitude = req.latitude
    if req.longitude is not None:
        loc.longitude = req.longitude
    db.commit()
    db.refresh(loc)
    return APIResponse(status="success", data=LocationRead.model_validate(loc))


@router.delete("/{location_id}", response_model=MessageResponse)
@router.post("/{location_id}/delete", response_model=MessageResponse)
def delete_location(
    location_id: int,
    admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db)
):
    loc = db.query(Location).filter(Location.id == location_id).first()
    if not loc:
        raise HTTPException(status_code=404, detail="Location not found.")
    db.delete(loc)
    db.commit()
    return MessageResponse(status="success", message="Location deleted successfully.")
