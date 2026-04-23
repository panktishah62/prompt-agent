from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.models.schemas import ResolveLocationRequest, ResolveLocationResponse
from app.services.location_resolver import resolve_location_from_coordinates

router = APIRouter()


@router.post("/api/location/resolve", response_model=ResolveLocationResponse)
async def resolve_location(request: ResolveLocationRequest) -> ResolveLocationResponse:
    try:
        location, formatted_address = await resolve_location_from_coordinates(
            request.latitude,
            request.longitude,
        )
        return ResolveLocationResponse(
            location=location,
            formatted_address=formatted_address,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
