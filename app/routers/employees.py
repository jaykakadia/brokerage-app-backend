import random
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.core.dependencies import get_current_admin, get_db
from app.db.models.user import User
from app.db.models.employee import Employee
from app.db.models.listing import Listing
from app.schemas.common import APIResponse, MessageResponse
from app.schemas.employee import EmployeeRead, EmployeeCreate, EmployeeUpdate, RefCodeItem

router = APIRouter(prefix="/api/v1/employees", tags=["Employees"])


def generate_ref_code() -> str:
    chars = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    while True:
        code = "".join(random.choice(chars) for _ in range(6))
        if any(c.isalpha() for c in code) and any(c.isdigit() for c in code):
            return code


@router.get("/ref-codes", response_model=APIResponse[List[RefCodeItem]])
def get_ref_codes(
    q: Optional[str] = Query(None),
    db: Session = Depends(get_db)
):
    """Public lookup for active Field Associate reference codes."""
    query = db.query(Employee).filter(Employee.status == "active")
    if q:
        search_filter = f"%{q.strip().upper()}%"
        query = query.filter(
            (Employee.reference_code.ilike(search_filter)) |
            (Employee.name.ilike(f"%{q.strip()}%"))
        )
    employees = query.order_by(Employee.reference_code.asc()).all()
    data = [RefCodeItem(reference_code=e.reference_code, name=e.name) for e in employees]
    return APIResponse(status="success", data=data)


@router.get("", response_model=APIResponse[List[EmployeeRead]])
def list_employees(
    admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db)
):
    """Admin endpoint to list all field associates with listing counts."""
    employees = db.query(Employee).order_by(Employee.id.desc()).all()
    
    # Calculate listing counts per reference code
    counts = dict(
        db.query(Listing.reference_code, func.count(Listing.id))
        .filter(Listing.reference_code.isnot(None), Listing.status != "deleted")
        .group_by(Listing.reference_code)
        .all()
    )

    result = []
    for emp in employees:
        emp_read = EmployeeRead(
            id=emp.id,
            name=emp.name,
            reference_code=emp.reference_code,
            status=emp.status,
            phone=emp.phone,
            email=emp.email,
            listings_created=counts.get(emp.reference_code, 0),
            created_at=emp.created_at,
            updated_at=emp.updated_at
        )
        result.append(emp_read)

    return APIResponse(status="success", data=result)


@router.get("/{employee_id}", response_model=APIResponse[EmployeeRead])
def get_employee(
    employee_id: int,
    admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db)
):
    """Admin endpoint to get single employee details."""
    emp = db.query(Employee).filter(Employee.id == employee_id).first()
    if not emp:
        raise HTTPException(status_code=404, detail="Business Associate not found.")

    count = (
        db.query(func.count(Listing.id))
        .filter(Listing.reference_code == emp.reference_code, Listing.status != "deleted")
        .scalar() or 0
    )

    data = EmployeeRead(
        id=emp.id,
        name=emp.name,
        reference_code=emp.reference_code,
        status=emp.status,
        phone=emp.phone,
        email=emp.email,
        listings_created=count,
        created_at=emp.created_at,
        updated_at=emp.updated_at
    )
    return APIResponse(status="success", data=data)


@router.post("", response_model=APIResponse[EmployeeRead])
def create_or_update_employee(
    req: EmployeeCreate,
    employee_id: Optional[int] = Query(None),
    admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db)
):
    """Admin create or update field associate."""
    ref_code = (req.reference_code or "").strip().upper()
    if not ref_code:
        ref_code = generate_ref_code()

    if employee_id and employee_id > 0:
        emp = db.query(Employee).filter(Employee.id == employee_id).first()
        if not emp:
            raise HTTPException(status_code=404, detail="Business Associate not found.")
        
        # Check duplicate code
        exists = db.query(Employee).filter(Employee.reference_code == ref_code, Employee.id != employee_id).first()
        if exists:
            raise HTTPException(status_code=400, detail="Reference code already in use.")

        emp.name = req.name.strip()
        emp.status = req.status
        emp.phone = req.phone
        emp.email = req.email
        db.commit()
        db.refresh(emp)
    else:
        # Check unique ref code
        exists = db.query(Employee).filter(Employee.reference_code == ref_code).first()
        if exists:
            raise HTTPException(status_code=400, detail="Reference code already in use.")

        emp = Employee(
            name=req.name.strip(),
            reference_code=ref_code,
            status=req.status,
            phone=req.phone,
            email=req.email
        )
        db.add(emp)
        db.commit()
        db.refresh(emp)

    count = (
        db.query(func.count(Listing.id))
        .filter(Listing.reference_code == emp.reference_code, Listing.status != "deleted")
        .scalar() or 0
    )

    data = EmployeeRead(
        id=emp.id,
        name=emp.name,
        reference_code=emp.reference_code,
        status=emp.status,
        phone=emp.phone,
        email=emp.email,
        listings_created=count,
        created_at=emp.created_at,
        updated_at=emp.updated_at
    )
    return APIResponse(status="success", data=data)


@router.delete("/{employee_id}", response_model=MessageResponse)
def delete_employee(
    employee_id: int,
    admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db)
):
    """Admin delete field associate."""
    emp = db.query(Employee).filter(Employee.id == employee_id).first()
    if not emp:
        raise HTTPException(status_code=404, detail="Business Associate not found.")

    db.delete(emp)
    db.commit()
    return MessageResponse(status="success", message="Business Associate deleted successfully.")
