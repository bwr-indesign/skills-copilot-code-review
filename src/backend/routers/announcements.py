"""
Announcement endpoints for the High School Management System API
"""

from fastapi import APIRouter, HTTPException, Query
from typing import Dict, Any, Optional, List
from datetime import date
from bson import ObjectId
from bson.errors import InvalidId

from ..database import announcements_collection, teachers_collection

router = APIRouter(
    prefix="/announcements",
    tags=["announcements"]
)


def _serialize(announcement: dict) -> dict:
    """Convert a MongoDB document to a JSON-serializable dict."""
    doc = dict(announcement)
    doc["id"] = str(doc.pop("_id"))
    return doc


def _require_teacher(teacher_username: Optional[str]):
    """Raise 401 if teacher_username is missing or not found in the database."""
    if not teacher_username:
        raise HTTPException(status_code=401, detail="Authentication required")
    teacher = teachers_collection.find_one({"_id": teacher_username})
    if not teacher:
        raise HTTPException(status_code=401, detail="Invalid credentials")


def _parse_object_id(announcement_id: str) -> ObjectId:
    """Parse an ObjectId string, raising 400 on failure."""
    try:
        return ObjectId(announcement_id)
    except (InvalidId, Exception):
        raise HTTPException(status_code=400, detail="Invalid announcement ID")


@router.get("", response_model=List[Dict[str, Any]])
def get_active_announcements() -> List[Dict[str, Any]]:
    """
    Get all currently active announcements visible to the public.

    An announcement is active when today falls within [start_date, expiration_date).
    - start_date is optional; when absent the announcement is immediately active.
    - expiration_date is required; announcements on or after this date are hidden.
    """
    today = date.today().isoformat()
    active = []
    for ann in announcements_collection.find({"expiration_date": {"$gt": today}}):
        start = ann.get("start_date")
        if start and start > today:
            continue
        active.append(_serialize(ann))
    return active


@router.get("/all", response_model=List[Dict[str, Any]])
def get_all_announcements(
    teacher_username: Optional[str] = Query(None)
) -> List[Dict[str, Any]]:
    """
    Get every announcement regardless of dates — requires teacher authentication.

    Used by the management UI to list, edit, and delete announcements.
    """
    _require_teacher(teacher_username)
    return [_serialize(ann) for ann in announcements_collection.find().sort("expiration_date", 1)]


@router.post("", response_model=Dict[str, Any])
def create_announcement(
    message: str,
    expiration_date: str,
    start_date: Optional[str] = None,
    teacher_username: Optional[str] = Query(None)
) -> Dict[str, Any]:
    """
    Create a new announcement — requires teacher authentication.

    - message: The text to display.
    - expiration_date: Required. Format YYYY-MM-DD. The announcement is hidden on and after this date.
    - start_date: Optional. Format YYYY-MM-DD. When provided, the announcement is hidden before this date.
    """
    _require_teacher(teacher_username)

    # Validate date formats
    try:
        date.fromisoformat(expiration_date)
        if start_date:
            date.fromisoformat(start_date)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid date format. Use YYYY-MM-DD")

    doc: Dict[str, Any] = {
        "message": message,
        "expiration_date": expiration_date,
        "created_by": teacher_username,
        "created_at": date.today().isoformat(),
    }
    if start_date:
        doc["start_date"] = start_date

    result = announcements_collection.insert_one(doc)
    doc["id"] = str(result.inserted_id)
    doc.pop("_id", None)
    return doc


@router.put("/{announcement_id}", response_model=Dict[str, Any])
def update_announcement(
    announcement_id: str,
    message: str,
    expiration_date: str,
    start_date: Optional[str] = None,
    teacher_username: Optional[str] = Query(None)
) -> Dict[str, Any]:
    """
    Update an existing announcement — requires teacher authentication.

    Providing start_date=None (omitting it) removes any existing start date.
    """
    _require_teacher(teacher_username)
    obj_id = _parse_object_id(announcement_id)

    # Validate date formats
    try:
        date.fromisoformat(expiration_date)
        if start_date:
            date.fromisoformat(start_date)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid date format. Use YYYY-MM-DD")

    update_fields: Dict[str, Any] = {
        "message": message,
        "expiration_date": expiration_date,
    }
    if start_date:
        update_fields["start_date"] = start_date

    # Build the update operation; unset start_date when not supplied
    update_op: Dict[str, Any] = {"$set": update_fields}
    if not start_date:
        update_op["$unset"] = {"start_date": ""}

    result = announcements_collection.update_one({"_id": obj_id}, update_op)
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Announcement not found")

    updated = announcements_collection.find_one({"_id": obj_id})
    return _serialize(updated)


@router.delete("/{announcement_id}")
def delete_announcement(
    announcement_id: str,
    teacher_username: Optional[str] = Query(None)
) -> Dict[str, str]:
    """Delete an announcement — requires teacher authentication."""
    _require_teacher(teacher_username)
    obj_id = _parse_object_id(announcement_id)

    result = announcements_collection.delete_one({"_id": obj_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Announcement not found")

    return {"message": "Announcement deleted"}
