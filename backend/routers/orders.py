from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session, joinedload

from database import get_db
from models import Customer, Order, OrderItem, Product
from schemas import OrderCreate, OrderItemOut, OrderOut
from security import get_current_user

router = APIRouter(prefix="/api/orders", tags=["orders"])

VALID_STATUSES = ("pending", "paid", "cancelled")


def get_or_create_customer(db: Session, username: str) -> Customer:
    name = (username or "").strip().lower()
    if not name:
        raise HTTPException(status_code=400, detail="A username is required")
    customer = db.query(Customer).filter(Customer.username == name).first()
    if not customer:
        customer = Customer(username=name)
        db.add(customer)
        db.flush()
    return customer


@router.get("", response_model=List[OrderOut])
def list_orders(
    status_: Optional[str] = None,
    db: Session = Depends(get_db),
    _: dict = Depends(get_current_user),
):
    query = db.query(Order)
    if status_:
        query = query.filter(Order.status == status_)
    return query.order_by(Order.created_at.desc()).all()


@router.get("/{order_id}/items", response_model=List[OrderItemOut])
def get_order_items(
    order_id: int,
    db: Session = Depends(get_db),
    _: dict = Depends(get_current_user),
):
    order = db.get(Order, order_id)
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    return order.items


@router.post("", response_model=OrderOut, status_code=201)
def create_order(data: OrderCreate, db: Session = Depends(get_db)):
    if not data.items:
        raise HTTPException(status_code=400, detail="Order must contain items")

    customer = get_or_create_customer(db, data.customer_username)

    order = Order(status="pending", notes=data.notes, customer_id=customer.id)
    subtotal = 0.0
    for item in data.items:
        product = db.get(Product, item.product_id)
        if not product or not product.is_active:
            raise HTTPException(
                status_code=400, detail=f"Product {item.product_id} not available"
            )
        if product.stock < item.quantity:
            raise HTTPException(
                status_code=400,
                detail=f"Insufficient stock for '{product.name}' ({product.stock} left)",
            )
        product.stock -= item.quantity
        line_total = product.price * item.quantity
        subtotal += line_total
        order.items.append(
            OrderItem(
                product_id=product.id,
                product_name=product.name,
                quantity=item.quantity,
                unit_price=product.price,
            )
        )

    order.subtotal = round(subtotal, 2)
    order.total = round(subtotal, 2)

    db.add(order)
    db.commit()
    db.refresh(order)
    return order


@router.patch("/{order_id}/status", response_model=OrderOut)
def update_order_status(
    order_id: int,
    new_status: str,
    db: Session = Depends(get_db),
    _: dict = Depends(get_current_user),
):
    if new_status not in VALID_STATUSES:
        raise HTTPException(status_code=400, detail="Invalid status")
    order = db.get(Order, order_id)
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")

    if order.status == "pending" and new_status == "cancelled":
        for item in order.items:
            product = item.product
            if product:
                product.stock += item.quantity

    order.status = new_status
    if new_status != "pending":
        order.completed_at = datetime.utcnow()
    db.commit()
    db.refresh(order)
    return order