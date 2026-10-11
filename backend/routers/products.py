import os
import uuid
from typing import List, Optional

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload

from config import settings
from database import get_db
from models import Product, ProductBarcode
from schemas import ProductCreate, ProductOut, ProductUpdate
from security import get_current_user

router = APIRouter(prefix="/api/products", tags=["products"])

ALLOWED_IMAGE_TYPES = {
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/webp": ".webp",
    "image/gif": ".gif",
}
MAX_IMAGE_BYTES = 5 * 1024 * 1024

_MAGIC_BY_SIGNATURE = [
    (b"\x89PNG\r\n\x1a\n", "image/png"),
    (b"\xff\xd8\xff", "image/jpeg"),
    (b"GIF87a", "image/gif"),
    (b"GIF89a", "image/gif"),
]
# WebP: "RIFF" (0-3) + size (4-7) + "WEBP" (8-11)
_WEBP_HEAD = b"RIFF"
_WEBP_MAGIC = b"WEBP"


def _detect_image_type(data: bytes) -> str | None:
    """Return the real content type from file signature bytes."""
    for sig, mime in _MAGIC_BY_SIGNATURE:
        if data.startswith(sig):
            return mime
    if (
        len(data) >= 12
        and data.startswith(_WEBP_HEAD)
        and data[8:12] == _WEBP_MAGIC
    ):
        return "image/webp"
    return None


def images_dir() -> str:
    directory = os.path.join(
        os.path.dirname(os.path.abspath(settings.database_path)) or ".",
        "product_images",
    )
    os.makedirs(directory, exist_ok=True)
    return directory


def _remove_image_file(path: str) -> None:
    if not path:
        return
    file_path = os.path.join(images_dir(), os.path.basename(path))
    if os.path.exists(file_path):
        os.remove(file_path)


@router.get("", response_model=List[ProductOut])
def list_products(
    category_id: Optional[int] = None,
    search: Optional[str] = None,
    active_only: bool = True,
    db: Session = Depends(get_db),
):
    query = db.query(Product).options(joinedload(Product.category))
    if category_id:
        query = query.filter(Product.category_id == category_id)
    if search:
        query = query.filter(Product.name.ilike(f"%{search}%"))
    if active_only:
        query = query.filter(Product.is_active)
    return query.order_by(Product.name).all()


@router.get("/barcode/{barcode}", response_model=ProductOut)
def get_product_by_barcode(barcode: str, db: Session = Depends(get_db)):
    code = barcode.strip().casefold()
    product = (
        db.query(Product)
        .join(ProductBarcode, ProductBarcode.product_id == Product.id)
        .options(joinedload(Product.category))
        .filter(ProductBarcode.code == code, Product.is_active.is_(True))
        .first()
    )
    if not product:
        raise HTTPException(status_code=404, detail="No active product found for barcode")
    return product


@router.get("/{product_id}", response_model=ProductOut)
def get_product(product_id: int, db: Session = Depends(get_db)):
    product = (
        db.query(Product)
        .options(joinedload(Product.category))
        .filter(Product.id == product_id)
        .first()
    )
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    return product


@router.post("", response_model=ProductOut, status_code=201)
def create_product(
    data: ProductCreate,
    db: Session = Depends(get_db),
    _: dict = Depends(get_current_user),
):
    values = data.model_dump()
    barcodes = values.pop("barcodes")
    product = Product(**values)
    db.add(product)
    db.flush()
    product.barcode_entries.extend(
        ProductBarcode(code=code) for code in barcodes
    )
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="A barcode is already assigned to another product",
        ) from exc
    db.refresh(product)
    return product


@router.put("/{product_id}", response_model=ProductOut)
def update_product(
    product_id: int,
    data: ProductUpdate,
    db: Session = Depends(get_db),
    _: dict = Depends(get_current_user),
):
    product = db.get(Product, product_id)
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    values = data.model_dump(exclude_unset=True)
    barcodes = values.pop("barcodes", None)
    for field, value in values.items():
        setattr(product, field, value)
    if barcodes is not None:
        product.barcode_entries.clear()
        db.flush()
        product.barcode_entries.extend(
            ProductBarcode(code=code) for code in barcodes
        )
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="A barcode is already assigned to another product",
        ) from exc
    db.refresh(product)
    return product


@router.delete("/{product_id}", status_code=204)
def delete_product(
    product_id: int,
    db: Session = Depends(get_db),
    _: dict = Depends(get_current_user),
):
    product = db.get(Product, product_id)
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    _remove_image_file(product.image_path)
    db.delete(product)
    db.commit()


@router.post("/{product_id}/image", response_model=ProductOut)
def upload_product_image(
    product_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    _: dict = Depends(get_current_user),
):
    product = db.get(Product, product_id)
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    declared = file.content_type or ""
    ext = ALLOWED_IMAGE_TYPES.get(declared)
    if not ext:
        raise HTTPException(
            status_code=400,
            detail="Only PNG, JPEG, WebP and GIF images are allowed",
        )
    data = file.file.read(MAX_IMAGE_BYTES + 1)
    if not data:
        raise HTTPException(status_code=400, detail="Empty file")
    if len(data) > MAX_IMAGE_BYTES:
        raise HTTPException(status_code=413, detail="Image too large (max 5 MB)")

    actual_type = _detect_image_type(data)
    if actual_type is None or ALLOWED_IMAGE_TYPES.get(actual_type) != ext:
        raise HTTPException(
            status_code=400,
            detail="File content does not match the declared image type",
        )

    _remove_image_file(product.image_path)
    filename = f"{uuid.uuid4().hex}{ext}"
    with open(os.path.join(images_dir(), filename), "wb") as f:
        f.write(data)
    product.image_path = filename
    db.commit()
    db.refresh(product)
    return product


@router.delete("/{product_id}/image", response_model=ProductOut)
def delete_product_image(
    product_id: int,
    db: Session = Depends(get_db),
    _: dict = Depends(get_current_user),
):
    product = db.get(Product, product_id)
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    if product.image_path:
        _remove_image_file(product.image_path)
        product.image_path = ""
        db.commit()
        db.refresh(product)
    return product
