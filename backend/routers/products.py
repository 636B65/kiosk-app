import os
import uuid
from typing import List, Optional

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload

import audit
from config import settings
from database import get_db
from models import Product, ProductBarcode, Restock, User
from schemas import (
    ProductCreate,
    ProductOut,
    ProductUpdate,
    RestockIn,
    RestockOut,
)
from security import get_current_user, get_optional_user

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


# Fields whose before/after values are written to the audit log on update.
AUDITED_FIELDS = (
    "name",
    "price",
    "special_price",
    "is_weekly_special",
    "special_starts_on",
    "special_ends_on",
    "cost_price",
    "stock",
    "low_stock_threshold",
    "is_active",
    "category_id",
    "barcodes",
)


def _audit_snapshot(product: Product) -> dict:
    return {field: getattr(product, field) for field in AUDITED_FIELDS}


def visible_to(product: Product, user: User | None) -> ProductOut:
    """Purchase prices are for staff only; public callers get cost_price=None."""
    out = ProductOut.model_validate(product)
    return out if user is not None else out.model_copy(update={"cost_price": None})


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
    user: User | None = Depends(get_optional_user),
):
    query = db.query(Product).options(joinedload(Product.category))
    if category_id:
        query = query.filter(Product.category_id == category_id)
    if search:
        query = query.filter(Product.name.ilike(f"%{search}%"))
    if active_only:
        query = query.filter(Product.is_active)
    return [visible_to(p, user) for p in query.order_by(Product.name).all()]


@router.get("/barcode/{barcode}", response_model=ProductOut)
def get_product_by_barcode(
    barcode: str,
    db: Session = Depends(get_db),
    user: User | None = Depends(get_optional_user),
):
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
    return visible_to(product, user)


@router.get("/{product_id}", response_model=ProductOut)
def get_product(
    product_id: int,
    db: Session = Depends(get_db),
    user: User | None = Depends(get_optional_user),
):
    product = (
        db.query(Product)
        .options(joinedload(Product.category))
        .filter(Product.id == product_id)
        .first()
    )
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    return visible_to(product, user)


@router.post("", response_model=ProductOut, status_code=201)
def create_product(
    data: ProductCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    values = data.model_dump()
    barcodes = values.pop("barcodes")
    product = Product(**values)
    db.add(product)
    db.flush()
    product.barcode_entries.extend(
        ProductBarcode(code=code) for code in barcodes
    )
    audit.record(
        db,
        user.username,
        "product.create",
        "product",
        product.id,
        f"{product.name}; price {product.price}; stock {product.stock}",
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
    user: User = Depends(get_current_user),
):
    product = db.get(Product, product_id)
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    before = _audit_snapshot(product)
    values = data.model_dump(exclude_unset=True)
    barcodes = values.pop("barcodes", None)
    for field, value in values.items():
        setattr(product, field, value)
    if (
        product.special_starts_on
        and product.special_ends_on
        and product.special_ends_on < product.special_starts_on
    ):
        db.rollback()
        raise HTTPException(
            status_code=422,
            detail="special_ends_on must not be before special_starts_on",
        )
    if barcodes is not None:
        product.barcode_entries.clear()
        db.flush()
        product.barcode_entries.extend(
            ProductBarcode(code=code) for code in barcodes
        )
    after = _audit_snapshot(product)
    if barcodes is not None:
        after["barcodes"] = barcodes
    changes = audit.describe_changes(before, after)
    if changes:
        audit.record(
            db, user.username, "product.update", "product", product.id,
            f"{product.name}: {changes}",
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
    user: User = Depends(get_current_user),
):
    product = db.get(Product, product_id)
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    _remove_image_file(product.image_path)
    audit.record(
        db, user.username, "product.delete", "product", product.id,
        f"{product.name}; stock {product.stock}",
    )
    db.delete(product)
    db.commit()


@router.post("/{product_id}/restock", response_model=RestockOut, status_code=201)
def restock_product(
    product_id: int,
    data: RestockIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Record a delivery: add stock and remember the purchase price per unit."""
    product = db.get(Product, product_id)
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    product.stock = (product.stock or 0) + data.quantity
    if data.unit_cost is not None:
        product.cost_price = data.unit_cost
    restock = Restock(
        product_id=product.id,
        product_name=product.name,
        quantity=data.quantity,
        unit_cost=data.unit_cost,
        stock_after=product.stock,
        note=data.note.strip(),
        created_by=user.username,
    )
    db.add(restock)
    cost = f" at {data.unit_cost} each" if data.unit_cost is not None else ""
    audit.record(
        db, user.username, "product.restock", "product", product.id,
        f"{product.name}: +{data.quantity}{cost}; stock now {product.stock}",
    )
    db.commit()
    db.refresh(restock)
    return restock


@router.get("/{product_id}/restocks", response_model=List[RestockOut])
def list_product_restocks(
    product_id: int,
    limit: int = 50,
    db: Session = Depends(get_db),
    _: dict = Depends(get_current_user),
):
    if not db.get(Product, product_id):
        raise HTTPException(status_code=404, detail="Product not found")
    return (
        db.query(Restock)
        .filter(Restock.product_id == product_id)
        .order_by(Restock.created_at.desc(), Restock.id.desc())
        .limit(max(1, min(limit, 500)))
        .all()
    )


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
