from fastapi import APIRouter, HTTPException
from starlette.requests import Request as StarletteRequest

import schemas
from core.limiter import limiter
from services.email_service import send_contact_message

router = APIRouter()


@router.post("")
@limiter.limit("5/minute")
async def contact_us(
    request: StarletteRequest,
    body: schemas.ContactRequest,
):
    first_name = body.first_name.strip()
    last_name = body.last_name.strip()
    description = body.description.strip()
    phone = body.phone.strip() if body.phone else None

    if not first_name or not last_name:
        raise HTTPException(status_code=400, detail="First name and last name are required")

    if len(description) < 10:
        raise HTTPException(status_code=400, detail="Description is too short")

    sent = await send_contact_message(
        first_name=first_name,
        last_name=last_name,
        email=str(body.email),
        phone=phone,
        description=description,
    )

    if not sent:
        raise HTTPException(status_code=500, detail="Could not send contact message")

    return {"status": "sent"}