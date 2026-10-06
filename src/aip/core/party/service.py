import uuid
from datetime import date

from pydantic import BaseModel, EmailStr, Field
from sqlalchemy.ext.asyncio import AsyncSession

from aip.core.errors import NotFound
from aip.core.party.models import Party


class PartyCreate(BaseModel):
    kind: str = Field(pattern="^(person|company)$")
    first_name: str | None = None
    last_name: str
    birth_date: date | None = None
    national_id: str | None = None
    email: EmailStr | None = None
    phone: str | None = None
    street: str | None = None
    city: str | None = None
    postal_code: str | None = None
    country: str = Field(pattern="^(SK|AT)$")
    language: str = Field(pattern="^(sk|de)$")


async def create_party(session: AsyncSession, data: PartyCreate) -> Party:
    party = Party(**data.model_dump())
    session.add(party)
    await session.flush()
    return party


async def get_party(session: AsyncSession, party_id: uuid.UUID) -> Party:
    party = await session.get(Party, party_id)
    if party is None:
        raise NotFound(f"Party {party_id} not found")
    return party
