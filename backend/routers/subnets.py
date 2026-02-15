"""Subnet CRUD endpoints."""

from fastapi import APIRouter, HTTPException

from backend import database as db
from backend.models import SubnetCreate, SubnetUpdate, SubnetResponse

router = APIRouter(prefix="/api/subnets", tags=["subnets"])


def _get_db_path() -> str:
    from backend.main import get_config
    return get_config().app.database_path


@router.get("", response_model=list[SubnetResponse])
def list_subnets():
    return db.list_subnets(_get_db_path())


@router.post("", response_model=SubnetResponse, status_code=201)
def create_subnet(body: SubnetCreate):
    try:
        return db.create_subnet(_get_db_path(), body.cidr, body.label)
    except Exception as e:
        if "UNIQUE" in str(e):
            raise HTTPException(400, "Subnet already exists")
        raise


@router.get("/{subnet_id}", response_model=SubnetResponse)
def get_subnet(subnet_id: int):
    subnet = db.get_subnet(_get_db_path(), subnet_id)
    if not subnet:
        raise HTTPException(404, "Subnet not found")
    return subnet


@router.patch("/{subnet_id}", response_model=SubnetResponse)
def update_subnet(subnet_id: int, body: SubnetUpdate):
    updates = body.model_dump(exclude_none=True)
    result = db.update_subnet(_get_db_path(), subnet_id, **updates)
    if not result:
        raise HTTPException(404, "Subnet not found")
    return result


@router.delete("/{subnet_id}", status_code=204)
def delete_subnet(subnet_id: int):
    if not db.delete_subnet(_get_db_path(), subnet_id):
        raise HTTPException(404, "Subnet not found")
