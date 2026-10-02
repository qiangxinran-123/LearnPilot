from __future__ import annotations

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile

from backend.app.core.errors import ApiError
from backend.app.schemas.course import (
    Course,
    CourseCreate,
    CourseDeleteResponse,
    CourseListResponse,
    CourseUpdate,
    Material,
    MaterialCreate,
    MaterialListResponse,
)
from backend.app.services.course_service import (
    CourseService,
    ResourceNotFoundError,
    get_course_service,
    serialize_course,
    serialize_material,
)
from backend.app.storage import StorageError, UploadRejected

router = APIRouter(prefix="/api/courses", tags=["courses"])


def course_not_found() -> HTTPException:
    return HTTPException(status_code=404, detail="Course not found")


@router.get("", response_model=CourseListResponse)
def list_courses(service: CourseService = Depends(get_course_service)) -> dict[str, object]:
    courses = service.list_courses()
    return {"count": len(courses), "courses": [serialize_course(course, count) for course, count in courses]}


@router.post("", response_model=Course, status_code=201)
def create_course(payload: CourseCreate, service: CourseService = Depends(get_course_service)) -> dict[str, object]:
    return serialize_course(service.create_course(payload))


@router.get("/{course_id}", response_model=Course)
def get_course_detail(course_id: int, service: CourseService = Depends(get_course_service)) -> dict[str, object]:
    try:
        return serialize_course(service.get_course(course_id))
    except ResourceNotFoundError as error:
        raise course_not_found() from error


@router.patch("/{course_id}", response_model=Course)
def update_course(
    course_id: int, payload: CourseUpdate, service: CourseService = Depends(get_course_service)
) -> dict[str, object]:
    try:
        return serialize_course(service.update_course(course_id, payload))
    except ResourceNotFoundError as error:
        raise course_not_found() from error


@router.delete("/{course_id}", response_model=CourseDeleteResponse)
def delete_course(course_id: int, service: CourseService = Depends(get_course_service)) -> dict[str, object]:
    try:
        service.delete_course(course_id)
    except ResourceNotFoundError as error:
        raise course_not_found() from error
    except StorageError as error:
        raise ApiError(500, "STORAGE_FAILURE", str(error)) from error
    return {"id": course_id, "deleted": True}


@router.get("/{course_id}/materials", response_model=MaterialListResponse, response_model_exclude_none=True)
def list_course_materials(course_id: int, service: CourseService = Depends(get_course_service)) -> dict[str, object]:
    try:
        materials = service.list_materials(course_id)
    except ResourceNotFoundError as error:
        raise course_not_found() from error
    return {
        "course_id": course_id,
        "count": len(materials),
        "materials": [serialize_material(material) for material in materials],
    }


@router.post("/{course_id}/materials", response_model=Material, response_model_exclude_none=True, status_code=201)
def create_course_material(
    course_id: int, material: MaterialCreate, service: CourseService = Depends(get_course_service)
) -> dict[str, object]:
    try:
        return serialize_material(service.create_material(course_id, material))
    except ResourceNotFoundError as error:
        raise course_not_found() from error


@router.post(
    "/{course_id}/materials/upload", response_model=Material, response_model_exclude_none=True, status_code=201
)
def upload_course_material(
    course_id: int,
    file: UploadFile | None = File(default=None),
    service: CourseService = Depends(get_course_service),
) -> dict[str, object]:
    if file is None or not file.filename:
        raise ApiError(400, "INVALID_FILENAME", "Uploaded file must have a filename.")
    try:
        material = service.create_uploaded_material(
            course_id,
            file.filename,
            file.content_type,
            file.file,
        )
        return serialize_material(material)
    except ResourceNotFoundError as error:
        raise course_not_found() from error
    except UploadRejected as error:
        status_code = 413 if error.code == "UPLOAD_TOO_LARGE" else 400
        raise ApiError(status_code, error.code, error.message) from error
    except StorageError as error:
        raise ApiError(500, "STORAGE_FAILURE", "Unable to store uploaded file.") from error
