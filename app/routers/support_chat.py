import json
import uuid
from datetime import datetime, timezone
from typing import Dict, List, Optional, Set
from fastapi import APIRouter, Depends, HTTPException, Query, Request, WebSocket, WebSocketDisconnect
from sqlalchemy import func, or_, and_, desc
from sqlalchemy.orm import Session

from app.core.dependencies import get_current_admin, get_optional_user, get_db
from app.db.session import SessionLocal
from app.db.models.support_chat import SupportConversation, SupportMessage
from app.db.models.user import User
from app.schemas.common import APIResponse, MessageResponse
from app.schemas.support_chat import (
    SupportConversationInit,
    SupportMessageCreate,
    SupportConversationResponse,
    SupportConversationListItem,
    SupportMessageResponse,
    SupportStatusUpdate,
)

router = APIRouter(prefix="/api/v1", tags=["Customer Support Live Chat"])

WELCOME_MESSAGE = (
    "Welcome to TradeCall India Support! We have received your request and an agent will reply shortly. "
    "Please let us know how we can assist you today."
)


# ============================================================================
# WebSocket Connection Manager
# ============================================================================

class SupportConnectionManager:
    def __init__(self):
        self.session_connections: Dict[str, Set[WebSocket]] = {}
        self.socket_sessions: Dict[WebSocket, Set[str]] = {}
        self.admin_connections: Set[WebSocket] = set()

    async def connect_session(self, session_id: str, websocket: WebSocket):
        await websocket.accept()
        self.subscribe_session(session_id, websocket)

    def subscribe_session(self, session_id: str, websocket: WebSocket):
        if not session_id:
            return
        if session_id not in self.session_connections:
            self.session_connections[session_id] = set()
        self.session_connections[session_id].add(websocket)
        if websocket not in self.socket_sessions:
            self.socket_sessions[websocket] = set()
        self.socket_sessions[websocket].add(session_id)

    def disconnect_session(self, session_id: str, websocket: WebSocket):
        sessions = list(self.socket_sessions.pop(websocket, {session_id}))
        for sid in sessions:
            if sid in self.session_connections:
                self.session_connections[sid].discard(websocket)
                if not self.session_connections[sid]:
                    del self.session_connections[sid]

    async def connect_admin(self, websocket: WebSocket):
        await websocket.accept()
        self.admin_connections.add(websocket)

    def disconnect_admin(self, websocket: WebSocket):
        self.admin_connections.discard(websocket)

    async def broadcast_to_session(self, session_id: str, payload: dict):
        if session_id in self.session_connections:
            text = json.dumps(payload, default=str)
            dead_sockets = set()
            for ws in list(self.session_connections[session_id]):
                try:
                    await ws.send_text(text)
                except Exception:
                    dead_sockets.add(ws)
            for ws in dead_sockets:
                self.disconnect_session(session_id, ws)

    async def broadcast_to_admins(self, payload: dict):
        text = json.dumps(payload, default=str)
        dead_sockets = set()
        for ws in list(self.admin_connections):
            try:
                await ws.send_text(text)
            except Exception:
                dead_sockets.add(ws)
        for ws in dead_sockets:
            self.admin_connections.discard(ws)

    async def broadcast_message(self, session_id: str, payload: dict):
        await self.broadcast_to_session(session_id, payload)
        await self.broadcast_to_admins(payload)


manager = SupportConnectionManager()


# ============================================================================
# Helper Functions
# ============================================================================

def get_admin_counts(db: Session) -> dict:
    total_unread = db.query(func.coalesce(func.sum(SupportConversation.unread_admin_count), 0)).filter(
        SupportConversation.is_deleted.is_(False)
    ).scalar() or 0

    return {
        "all": db.query(SupportConversation).filter(SupportConversation.is_deleted.is_(False)).count(),
        "open": db.query(SupportConversation).filter(
            SupportConversation.is_deleted.is_(False),
            SupportConversation.status == "open"
        ).count(),
        "in_progress": db.query(SupportConversation).filter(
            SupportConversation.is_deleted.is_(False),
            SupportConversation.status == "in_progress"
        ).count(),
        "resolved": db.query(SupportConversation).filter(
            SupportConversation.is_deleted.is_(False),
            SupportConversation.status == "resolved"
        ).count(),
        "closed": db.query(SupportConversation).filter(
            SupportConversation.is_deleted.is_(False),
            SupportConversation.status == "closed"
        ).count(),
        "unread_total": int(total_unread),
    }


def format_conversation_dict(conv: SupportConversation) -> dict:
    if conv.user:
        display_name = conv.user.name
        display_email = conv.user.email
        display_phone = conv.user.phone
        is_registered = True
    else:
        display_name = conv.guest_name or "Guest Visitor"
        display_email = conv.guest_email
        display_phone = conv.guest_phone
        is_registered = False

    messages_data = [
        {
            "id": m.id,
            "conversation_id": m.conversation_id,
            "sender_type": m.sender_type,
            "sender_id": m.sender_id,
            "sender_name": m.sender_name,
            "message": m.message,
            "is_read": m.is_read,
            "created_at": m.created_at
        }
        for m in (conv.messages or [])
    ]

    return {
        "id": conv.id,
        "session_id": conv.session_id,
        "user_id": conv.user_id,
        "display_name": display_name,
        "display_email": display_email,
        "display_phone": display_phone,
        "is_registered_user": is_registered,
        "status": conv.status,
        "unread_admin_count": conv.unread_admin_count,
        "unread_user_count": conv.unread_user_count,
        "last_message_at": conv.last_message_at,
        "created_at": conv.created_at,
        "messages": messages_data
    }


def format_list_item(conv: SupportConversation) -> dict:
    if conv.user:
        display_name = conv.user.name
        display_email = conv.user.email
        display_phone = conv.user.phone
        is_registered = True
    else:
        display_name = conv.guest_name or "Guest Visitor"
        display_email = conv.guest_email
        display_phone = conv.guest_phone
        is_registered = False

    last_text = None
    if conv.messages:
        last_text = conv.messages[-1].message

    return {
        "id": conv.id,
        "session_id": conv.session_id,
        "user_id": conv.user_id,
        "display_name": display_name,
        "display_email": display_email,
        "display_phone": display_phone,
        "is_registered_user": is_registered,
        "status": conv.status,
        "unread_admin_count": conv.unread_admin_count,
        "unread_user_count": conv.unread_user_count,
        "last_message_text": last_text,
        "last_message_at": conv.last_message_at,
        "created_at": conv.created_at
    }


# ============================================================================
# Public / Visitor Endpoints
# ============================================================================

@router.post("/support/conversations/init", response_model=APIResponse[SupportConversationResponse])
async def init_conversation(
    payload: SupportConversationInit,
    request: Request,
    db: Session = Depends(get_db)
):
    """
    Initialize or resume a customer support chat conversation.
    - If user is authenticated: auto-binds user account, no contact form needed.
    - If user is guest: requires Name and Phone (Email is optional).
    """
    current_user = get_optional_user(request, db)
    conv: Optional[SupportConversation] = None
    is_new = False

    # Check if a valid session_id was passed
    if payload.session_id:
        conv = db.query(SupportConversation).filter(
            SupportConversation.session_id == payload.session_id,
            SupportConversation.is_deleted.is_(False)
        ).first()

    # If user is signed in, check if they already have an open conversation
    if not conv and current_user:
        conv = db.query(SupportConversation).filter(
            SupportConversation.user_id == current_user.id,
            SupportConversation.is_deleted.is_(False),
            SupportConversation.status != "closed"
        ).order_by(desc(SupportConversation.last_message_at)).first()

    now = datetime.now(timezone.utc)

    if not conv:
        is_new = True
        new_session_id = payload.session_id or uuid.uuid4().hex

        if current_user:
            conv = SupportConversation(
                session_id=new_session_id,
                user_id=current_user.id,
                guest_name=current_user.name,
                guest_email=current_user.email,
                guest_phone=current_user.phone,
                status="open",
                unread_admin_count=1,
                unread_user_count=0,
                last_message_at=now
            )
        else:
            # Guest: require name and phone; email is optional
            if not payload.name or not payload.name.strip():
                raise HTTPException(status_code=400, detail="Name is required.")
            phone_clean = "".join(ch for ch in (payload.phone or "") if ch.isdigit())
            if len(phone_clean) < 10:
                raise HTTPException(status_code=400, detail="A valid phone number is required.")
            email_clean = payload.email.strip().lower() if payload.email and payload.email.strip() else None
            if email_clean and "@" not in email_clean:
                raise HTTPException(status_code=400, detail="Please enter a valid email address.")

            conv = SupportConversation(
                session_id=new_session_id,
                user_id=None,
                guest_name=payload.name.strip(),
                guest_email=email_clean,
                guest_phone=payload.phone.strip(),
                status="open",
                unread_admin_count=1,
                unread_user_count=0,
                last_message_at=now
            )

        db.add(conv)
        db.flush()

        # Add initial welcome / bot message
        welcome_msg = SupportMessage(
            conversation_id=conv.id,
            sender_type="bot",
            sender_id=None,
            sender_name="TradeCall Support",
            message=WELCOME_MESSAGE,
            is_read=True
        )
        db.add(welcome_msg)
        db.commit()
        db.refresh(conv)
    else:
        # If user recently logged in, link user_id if not already set
        if current_user and not conv.user_id:
            conv.user_id = current_user.id
            db.commit()
            db.refresh(conv)

    conv_dict = format_conversation_dict(conv)
    if is_new:
        await manager.broadcast_message(conv.session_id, {
            "type": "new_conversation",
            "session_id": conv.session_id,
            "conversation": format_list_item(conv),
            "data": conv_dict,
            "counts": get_admin_counts(db)
        })

    return APIResponse(
        status="success",
        message="Conversation initialized",
        data=conv_dict
    )


@router.get("/support/conversations/my-tickets", response_model=APIResponse[List[SupportConversationListItem]])
def list_my_tickets(
    session_ids: Optional[str] = Query(None, description="Comma-separated session IDs for guest users"),
    phone: Optional[str] = Query(None, description="Phone number to match tickets"),
    name: Optional[str] = Query(None, description="Name to match tickets"),
    email: Optional[str] = Query(None, description="Email to match tickets"),
    request: Request = None,
    db: Session = Depends(get_db)
):
    """List customer support tickets for the current user or guest matching phone/name/session IDs."""
    current_user = get_optional_user(request, db)
    parsed_sessions = [s.strip() for s in (session_ids or "").split(",") if s.strip()]

    filters = []

    # 1. Logged-in user: match user_id and optionally their phone/email
    if current_user:
        filters.append(SupportConversation.user_id == current_user.id)
        if current_user.phone:
            u_digits = "".join(filter(str.isdigit, current_user.phone))
            u_last10 = u_digits[-10:] if len(u_digits) >= 10 else u_digits
            if u_last10:
                filters.append(SupportConversation.guest_phone.contains(u_last10))
        if current_user.email:
            filters.append(func.lower(SupportConversation.guest_email) == current_user.email.strip().lower())

    # 2. Match by provided phone and/or name
    clean_phone = (phone or "").strip()
    clean_name = (name or "").strip()
    clean_email = (email or "").strip()

    if clean_phone:
        p_digits = "".join(filter(str.isdigit, clean_phone))
        p_last10 = p_digits[-10:] if len(p_digits) >= 10 else p_digits
        if p_last10:
            if clean_name:
                # Prioritize matching phone and name together, or matching phone
                filters.append(
                    or_(
                        and_(
                            SupportConversation.guest_phone.contains(p_last10),
                            func.lower(SupportConversation.guest_name).contains(clean_name.lower())
                        ),
                        SupportConversation.guest_phone.contains(p_last10)
                    )
                )
            else:
                filters.append(SupportConversation.guest_phone.contains(p_last10))
    elif clean_name:
        filters.append(func.lower(SupportConversation.guest_name) == clean_name.lower())

    if clean_email:
        filters.append(func.lower(SupportConversation.guest_email) == clean_email.lower())

    # 3. Match by explicit session IDs
    if parsed_sessions:
        filters.append(SupportConversation.session_id.in_(parsed_sessions))

    if not filters:
        return APIResponse(status="success", data=[])

    query = db.query(SupportConversation).filter(
        SupportConversation.is_deleted.is_(False),
        or_(*filters)
    ).distinct().order_by(desc(SupportConversation.last_message_at))

    conversations = query.limit(50).all()
    items = [format_list_item(c) for c in conversations]

    return APIResponse(status="success", data=items)


@router.get("/support/conversations/{session_id}", response_model=APIResponse[SupportConversationResponse])
async def get_conversation_by_session(session_id: str, db: Session = Depends(get_db)):
    """Fetch conversation and message history by session_id."""
    conv = db.query(SupportConversation).filter(
        SupportConversation.session_id == session_id,
        SupportConversation.is_deleted.is_(False)
    ).first()

    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found.")

    # Reset unread_user_count
    if conv.unread_user_count > 0:
        conv.unread_user_count = 0
        db.commit()
        db.refresh(conv)

    return APIResponse(
        status="success",
        data=format_conversation_dict(conv)
    )


@router.post("/support/conversations/{session_id}/messages", response_model=APIResponse[SupportMessageResponse])
async def send_visitor_message(
    session_id: str,
    payload: SupportMessageCreate,
    request: Request,
    db: Session = Depends(get_db)
):
    """Visitor or user sends a message in the chat."""
    conv = db.query(SupportConversation).filter(
        SupportConversation.session_id == session_id,
        SupportConversation.is_deleted.is_(False)
    ).first()

    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found.")

    if conv.status in ("closed", "resolved"):
        raise HTTPException(
            status_code=400,
            detail=f"This ticket is {conv.status}. Please reopen the ticket to continue chatting."
        )

    clean_text = payload.message.strip()
    if not clean_text:
        raise HTTPException(status_code=400, detail="Message cannot be empty.")

    current_user = get_optional_user(request, db)
    sender_type = "user" if current_user else "guest"
    sender_id = current_user.id if current_user else None
    sender_name = current_user.name if current_user else (conv.guest_name or "Visitor")

    now = datetime.now(timezone.utc)
    new_msg = SupportMessage(
        conversation_id=conv.id,
        sender_type=sender_type,
        sender_id=sender_id,
        sender_name=sender_name,
        message=clean_text,
        is_read=False,
        created_at=now
    )
    db.add(new_msg)

    conv.last_message_at = now
    conv.unread_admin_count += 1
    if conv.status == "open":
        conv.status = "in_progress"

    db.commit()
    db.refresh(new_msg)
    db.refresh(conv)

    msg_data = {
        "id": new_msg.id,
        "conversation_id": new_msg.conversation_id,
        "session_id": conv.session_id,
        "sender_type": new_msg.sender_type,
        "sender_id": new_msg.sender_id,
        "sender_name": new_msg.sender_name,
        "message": new_msg.message,
        "is_read": new_msg.is_read,
        "created_at": new_msg.created_at.isoformat()
    }

    # Broadcast to session & admin sockets
    await manager.broadcast_message(conv.session_id, {
        "type": "new_message",
        "data": msg_data,
        "conversation": format_list_item(conv),
        "counts": get_admin_counts(db)
    })

    return APIResponse(
        status="success",
        message="Message sent",
        data=new_msg
    )


@router.post("/support/conversations/{session_id}/reopen", response_model=APIResponse[SupportConversationResponse])
async def reopen_conversation(session_id: str, db: Session = Depends(get_db)):
    """Customer reopens a closed or resolved ticket."""
    conv = db.query(SupportConversation).filter(
        SupportConversation.session_id == session_id,
        SupportConversation.is_deleted.is_(False)
    ).first()

    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found.")

    now = datetime.now(timezone.utc)
    conv.status = "open"
    conv.last_message_at = now
    conv.unread_admin_count += 1

    reopen_msg = SupportMessage(
        conversation_id=conv.id,
        sender_type="bot",
        sender_id=None,
        sender_name="TradeCall Support",
        message="This ticket was reopened by the customer.",
        is_read=False,
        created_at=now
    )
    db.add(reopen_msg)
    db.commit()
    db.refresh(reopen_msg)
    db.refresh(conv)

    msg_data = {
        "id": reopen_msg.id,
        "conversation_id": reopen_msg.conversation_id,
        "session_id": conv.session_id,
        "sender_type": reopen_msg.sender_type,
        "sender_id": reopen_msg.sender_id,
        "sender_name": reopen_msg.sender_name,
        "message": reopen_msg.message,
        "is_read": reopen_msg.is_read,
        "created_at": reopen_msg.created_at.isoformat()
    }

    conv_item = format_list_item(conv)
    counts = get_admin_counts(db)

    await manager.broadcast_message(conv.session_id, {
        "type": "status_changed",
        "session_id": conv.session_id,
        "conversation_id": conv.id,
        "status": "open",
        "conversation": conv_item,
        "counts": counts
    })
    await manager.broadcast_message(conv.session_id, {
        "type": "new_message",
        "data": msg_data,
        "conversation": conv_item,
        "counts": counts
    })

    return APIResponse(
        status="success",
        message="Ticket reopened",
        data=format_conversation_dict(conv)
    )


@router.get("/support/conversations/{session_id}/poll", response_model=APIResponse[List[SupportMessageResponse]])
def poll_messages(
    session_id: str,
    after_id: int = Query(0, description="Return messages created after this message ID"),
    db: Session = Depends(get_db)
):
    """Fetch missed messages for reconnect after WebSocket drop."""
    conv = db.query(SupportConversation).filter(
        SupportConversation.session_id == session_id,
        SupportConversation.is_deleted.is_(False)
    ).first()

    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found.")

    safe_after_id = max(0, after_id)
    query = db.query(SupportMessage).filter(
        SupportMessage.conversation_id == conv.id,
        SupportMessage.id > safe_after_id
    ).order_by(SupportMessage.id.asc())

    messages = query.all()

    # If any messages were from admin/bot, mark user unread count as 0
    if messages and any(m.sender_type in ("admin", "bot") for m in messages):
        if conv.unread_user_count > 0:
            conv.unread_user_count = 0
            db.commit()

    return APIResponse(
        status="success",
        data=messages
    )


# ============================================================================
# Admin Endpoints
# ============================================================================

@router.get("/admin/support/conversations", response_model=APIResponse[Dict])
def list_admin_conversations(
    status: Optional[str] = Query(None, description="open, in_progress, resolved, all"),
    search: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db)
):
    """Admin dashboard endpoint to list all customer support chat threads."""
    query = db.query(SupportConversation).filter(SupportConversation.is_deleted.is_(False))

    if status and status != "all":
        query = query.filter(SupportConversation.status == status)

    if search:
        s = f"%{search.strip()}%"
        search_clauses = [
            SupportConversation.guest_name.ilike(s),
            SupportConversation.guest_email.ilike(s),
            SupportConversation.guest_phone.ilike(s),
            User.name.ilike(s),
            User.email.ilike(s),
            User.phone.ilike(s),
        ]
        num_clean = search.strip().lstrip('#')
        if num_clean.isdigit():
            search_clauses.append(SupportConversation.id == int(num_clean))

        query = query.outerjoin(User, SupportConversation.user_id == User.id).filter(
            or_(*search_clauses)
        )

    total_count = query.count()
    counts = get_admin_counts(db)

    conversations = query.order_by(desc(SupportConversation.last_message_at)).offset((page - 1) * limit).limit(limit).all()

    items = [format_list_item(c) for c in conversations]

    return APIResponse(
        status="success",
        data={
            "items": items,
            "total": total_count,
            "page": page,
            "limit": limit,
            "counts": counts
        }
    )


@router.get("/admin/support/conversations/{conv_id}", response_model=APIResponse[SupportConversationResponse])
async def get_admin_conversation_detail(
    conv_id: int,
    admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db)
):
    """Admin views conversation detail and marks admin unread messages as read."""
    conv = db.query(SupportConversation).filter(
        SupportConversation.id == conv_id,
        SupportConversation.is_deleted.is_(False)
    ).first()

    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found.")

    # Mark unread messages as read
    if conv.unread_admin_count > 0:
        conv.unread_admin_count = 0
        db.query(SupportMessage).filter(
            SupportMessage.conversation_id == conv.id,
            SupportMessage.sender_type.in_(["user", "guest"]),
            SupportMessage.is_read.is_(False)
        ).update({"is_read": True}, synchronize_session=False)
        db.commit()
        db.refresh(conv)

        await manager.broadcast_to_admins({
            "type": "conversation_read",
            "conversation_id": conv.id,
            "session_id": conv.session_id,
            "conversation": format_list_item(conv),
            "counts": get_admin_counts(db)
        })

    return APIResponse(
        status="success",
        data=format_conversation_dict(conv)
    )


@router.post("/admin/support/conversations/{conv_id}/messages", response_model=APIResponse[SupportMessageResponse])
async def admin_reply(
    conv_id: int,
    payload: SupportMessageCreate,
    admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db)
):
    """Admin replies to the user."""
    conv = db.query(SupportConversation).filter(
        SupportConversation.id == conv_id,
        SupportConversation.is_deleted.is_(False)
    ).first()

    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found.")

    if conv.status in ("closed", "resolved"):
        raise HTTPException(
            status_code=400,
            detail=f"This ticket is {conv.status}. Please change status to 'open' or 'in_progress' to send a reply."
        )

    clean_text = payload.message.strip()
    if not clean_text:
        raise HTTPException(status_code=400, detail="Message cannot be empty.")

    now = datetime.now(timezone.utc)
    new_msg = SupportMessage(
        conversation_id=conv.id,
        sender_type="admin",
        sender_id=admin.id,
        sender_name="Customer Support",
        message=clean_text,
        is_read=False,
        created_at=now
    )
    db.add(new_msg)

    conv.last_message_at = now
    conv.unread_user_count += 1
    conv.unread_admin_count = 0
    if conv.status == "open":
        conv.status = "in_progress"

    db.commit()
    db.refresh(new_msg)
    db.refresh(conv)

    msg_data = {
        "id": new_msg.id,
        "conversation_id": new_msg.conversation_id,
        "session_id": conv.session_id,
        "sender_type": new_msg.sender_type,
        "sender_id": new_msg.sender_id,
        "sender_name": new_msg.sender_name,
        "message": new_msg.message,
        "is_read": new_msg.is_read,
        "created_at": new_msg.created_at.isoformat()
    }

    # Broadcast to visitor and other admin tabs
    await manager.broadcast_message(conv.session_id, {
        "type": "new_message",
        "data": msg_data,
        "conversation": format_list_item(conv),
        "counts": get_admin_counts(db)
    })

    return APIResponse(
        status="success",
        message="Reply sent",
        data=new_msg
    )


@router.patch("/admin/support/conversations/{conv_id}/status", response_model=MessageResponse)
async def update_conversation_status(
    conv_id: int,
    payload: SupportStatusUpdate,
    admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db)
):
    """Update conversation status (open, in_progress, resolved, closed)."""
    conv = db.query(SupportConversation).filter(
        SupportConversation.id == conv_id,
        SupportConversation.is_deleted.is_(False)
    ).first()

    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found.")

    conv.status = payload.status
    db.commit()
    db.refresh(conv)

    await manager.broadcast_message(conv.session_id, {
        "type": "status_changed",
        "session_id": conv.session_id,
        "conversation_id": conv.id,
        "status": conv.status,
        "conversation": format_list_item(conv),
        "counts": get_admin_counts(db)
    })

    return MessageResponse(status="success", message=f"Status updated to {payload.status}")


@router.delete("/admin/support/conversations/{conv_id}", response_model=MessageResponse)
async def delete_conversation(
    conv_id: int,
    admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db)
):
    """Soft delete conversation."""
    conv = db.query(SupportConversation).filter(
        SupportConversation.id == conv_id,
        SupportConversation.is_deleted.is_(False)
    ).first()

    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found.")

    session_id = conv.session_id
    conv.is_deleted = True
    conv.deleted_at = datetime.now(timezone.utc)
    db.commit()

    await manager.broadcast_message(session_id, {
        "type": "conversation_deleted",
        "conversation_id": conv_id,
        "session_id": session_id,
        "counts": get_admin_counts(db)
    })

    return MessageResponse(status="success", message="Conversation deleted")


# ============================================================================
# WebSockets Endpoints (Full Bi-directional Live Chat)
# ============================================================================

@router.websocket("/support/ws/{session_id}")
async def visitor_websocket_endpoint(websocket: WebSocket, session_id: str):
    """Real-time bi-directional WebSocket connection for visitors/users."""
    await manager.connect_session(session_id, websocket)
    try:
        while True:
            data = await websocket.receive_text()
            if data == "ping":
                await websocket.send_text(json.dumps({"type": "pong"}))
                continue

            try:
                cmd = json.loads(data)
            except Exception:
                continue

            cmd_type = cmd.get("type")
            if cmd_type == "ping":
                await websocket.send_text(json.dumps({"type": "pong"}))
                continue

            if cmd_type == "subscribe":
                extra_ids = cmd.get("session_ids") or []
                if isinstance(extra_ids, list):
                    for sid in extra_ids[:30]:
                        if isinstance(sid, str) and sid.strip():
                            manager.subscribe_session(sid.strip(), websocket)
                continue

            target_session = cmd.get("session_id") or session_id

            if cmd_type == "typing":
                await manager.broadcast_to_admins({
                    "type": "typing",
                    "session_id": target_session,
                    "sender": "visitor",
                    "is_typing": bool(cmd.get("is_typing", True))
                })
                continue

            if cmd_type == "send_message":
                text = (cmd.get("message") or "").strip()
                if not text:
                    continue
                db = SessionLocal()
                try:
                    conv = db.query(SupportConversation).filter(
                        SupportConversation.session_id == target_session,
                        SupportConversation.is_deleted.is_(False)
                    ).first()
                    if not conv or conv.status in ("closed", "resolved"):
                        continue

                    sender_type = "user" if conv.user_id else "guest"
                    sender_name = (conv.user.name if conv.user else conv.guest_name) or "Visitor"
                    now = datetime.now(timezone.utc)

                    new_msg = SupportMessage(
                        conversation_id=conv.id,
                        sender_type=sender_type,
                        sender_id=conv.user_id,
                        sender_name=sender_name,
                        message=text,
                        is_read=False,
                        created_at=now
                    )
                    db.add(new_msg)
                    conv.last_message_at = now
                    conv.unread_admin_count += 1
                    if conv.status == "open":
                        conv.status = "in_progress"

                    db.commit()
                    db.refresh(new_msg)
                    db.refresh(conv)

                    msg_data = {
                        "id": new_msg.id,
                        "conversation_id": new_msg.conversation_id,
                        "session_id": conv.session_id,
                        "sender_type": new_msg.sender_type,
                        "sender_id": new_msg.sender_id,
                        "sender_name": new_msg.sender_name,
                        "message": new_msg.message,
                        "is_read": new_msg.is_read,
                        "created_at": new_msg.created_at.isoformat(),
                        "temp_id": cmd.get("temp_id")
                    }

                    await manager.broadcast_message(conv.session_id, {
                        "type": "new_message",
                        "data": msg_data,
                        "conversation": format_list_item(conv),
                        "counts": get_admin_counts(db)
                    })
                finally:
                    db.close()

            elif cmd_type == "reopen_ticket":
                db = SessionLocal()
                try:
                    conv = db.query(SupportConversation).filter(
                        SupportConversation.session_id == target_session,
                        SupportConversation.is_deleted.is_(False)
                    ).first()
                    if not conv:
                        continue

                    now = datetime.now(timezone.utc)
                    conv.status = "open"
                    conv.last_message_at = now
                    conv.unread_admin_count += 1

                    reopen_msg = SupportMessage(
                        conversation_id=conv.id,
                        sender_type="bot",
                        sender_id=None,
                        sender_name="TradeCall Support",
                        message="This ticket was reopened by the customer.",
                        is_read=False,
                        created_at=now
                    )
                    db.add(reopen_msg)
                    db.commit()
                    db.refresh(reopen_msg)
                    db.refresh(conv)

                    msg_data = {
                        "id": reopen_msg.id,
                        "conversation_id": reopen_msg.conversation_id,
                        "session_id": conv.session_id,
                        "sender_type": reopen_msg.sender_type,
                        "sender_id": reopen_msg.sender_id,
                        "sender_name": reopen_msg.sender_name,
                        "message": reopen_msg.message,
                        "is_read": reopen_msg.is_read,
                        "created_at": reopen_msg.created_at.isoformat()
                    }
                    conv_item = format_list_item(conv)
                    counts = get_admin_counts(db)

                    await manager.broadcast_message(conv.session_id, {
                        "type": "status_changed",
                        "session_id": conv.session_id,
                        "conversation_id": conv.id,
                        "status": "open",
                        "conversation": conv_item,
                        "counts": counts
                    })
                    await manager.broadcast_message(conv.session_id, {
                        "type": "new_message",
                        "data": msg_data,
                        "conversation": conv_item,
                        "counts": counts
                    })
                finally:
                    db.close()

            elif cmd_type == "mark_read":
                db = SessionLocal()
                try:
                    conv = db.query(SupportConversation).filter(
                        SupportConversation.session_id == target_session,
                        SupportConversation.is_deleted.is_(False)
                    ).first()
                    if conv and conv.unread_user_count > 0:
                        conv.unread_user_count = 0
                        db.commit()
                finally:
                    db.close()

    except WebSocketDisconnect:
        manager.disconnect_session(session_id, websocket)
    except Exception:
        manager.disconnect_session(session_id, websocket)


@router.websocket("/admin/support/ws")
async def admin_websocket_endpoint(websocket: WebSocket):
    """Real-time bi-directional WebSocket connection for Admin Dashboard."""
    await manager.connect_admin(websocket)
    try:
        while True:
            data = await websocket.receive_text()
            if data == "ping":
                await websocket.send_text(json.dumps({"type": "pong"}))
                continue

            try:
                cmd = json.loads(data)
            except Exception:
                continue

            cmd_type = cmd.get("type")
            if cmd_type == "ping":
                await websocket.send_text(json.dumps({"type": "pong"}))
                continue

            if cmd_type == "typing":
                target_session = cmd.get("session_id")
                if target_session:
                    await manager.broadcast_to_session(target_session, {
                        "type": "typing",
                        "session_id": target_session,
                        "sender": "admin",
                        "is_typing": bool(cmd.get("is_typing", True))
                    })
                continue

            if cmd_type == "mark_read":
                conv_id = cmd.get("conversation_id")
                if not conv_id:
                    continue
                db = SessionLocal()
                try:
                    conv = db.query(SupportConversation).filter(
                        SupportConversation.id == int(conv_id),
                        SupportConversation.is_deleted.is_(False)
                    ).first()
                    if conv and conv.unread_admin_count > 0:
                        conv.unread_admin_count = 0
                        db.query(SupportMessage).filter(
                            SupportMessage.conversation_id == conv.id,
                            SupportMessage.sender_type.in_(["user", "guest"]),
                            SupportMessage.is_read.is_(False)
                        ).update({"is_read": True}, synchronize_session=False)
                        db.commit()
                        db.refresh(conv)
                        await manager.broadcast_to_admins({
                            "type": "conversation_read",
                            "conversation_id": conv.id,
                            "session_id": conv.session_id,
                            "conversation": format_list_item(conv),
                            "counts": get_admin_counts(db)
                        })
                finally:
                    db.close()

            elif cmd_type == "send_reply":
                conv_id = cmd.get("conversation_id")
                text = (cmd.get("message") or "").strip()
                if not conv_id or not text:
                    continue
                db = SessionLocal()
                try:
                    conv = db.query(SupportConversation).filter(
                        SupportConversation.id == int(conv_id),
                        SupportConversation.is_deleted.is_(False)
                    ).first()
                    if not conv or conv.status in ("closed", "resolved"):
                        continue

                    now = datetime.now(timezone.utc)
                    new_msg = SupportMessage(
                        conversation_id=conv.id,
                        sender_type="admin",
                        sender_id=cmd.get("admin_id"),
                        sender_name="Customer Support",
                        message=text,
                        is_read=False,
                        created_at=now
                    )
                    db.add(new_msg)
                    conv.last_message_at = now
                    conv.unread_user_count += 1
                    conv.unread_admin_count = 0
                    if conv.status == "open":
                        conv.status = "in_progress"

                    db.commit()
                    db.refresh(new_msg)
                    db.refresh(conv)

                    msg_data = {
                        "id": new_msg.id,
                        "conversation_id": new_msg.conversation_id,
                        "session_id": conv.session_id,
                        "sender_type": new_msg.sender_type,
                        "sender_id": new_msg.sender_id,
                        "sender_name": new_msg.sender_name,
                        "message": new_msg.message,
                        "is_read": new_msg.is_read,
                        "created_at": new_msg.created_at.isoformat(),
                        "temp_id": cmd.get("temp_id")
                    }

                    await manager.broadcast_message(conv.session_id, {
                        "type": "new_message",
                        "data": msg_data,
                        "conversation": format_list_item(conv),
                        "counts": get_admin_counts(db)
                    })
                finally:
                    db.close()

            elif cmd_type == "update_status":
                conv_id = cmd.get("conversation_id")
                new_status = cmd.get("status")
                if not conv_id or new_status not in ("open", "in_progress", "resolved", "closed"):
                    continue
                db = SessionLocal()
                try:
                    conv = db.query(SupportConversation).filter(
                        SupportConversation.id == int(conv_id),
                        SupportConversation.is_deleted.is_(False)
                    ).first()
                    if not conv:
                        continue
                    conv.status = new_status
                    db.commit()
                    db.refresh(conv)

                    await manager.broadcast_message(conv.session_id, {
                        "type": "status_changed",
                        "session_id": conv.session_id,
                        "conversation_id": conv.id,
                        "status": conv.status,
                        "conversation": format_list_item(conv),
                        "counts": get_admin_counts(db)
                    })
                finally:
                    db.close()

    except WebSocketDisconnect:
        manager.disconnect_admin(websocket)
    except Exception:
        manager.disconnect_admin(websocket)
