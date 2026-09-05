from sqlalchemy.orm import Session

from models import Category, Product, Setting, User
from security import get_password_hash


def seed(db: Session):
    admin = db.query(User).filter(User.username == "admin").first()
    if not admin:
        admin = User(
            username="admin",
            password_hash=get_password_hash("admin123"),
            full_name="Store Administrator",
        )
        db.add(admin)

    for key, value in {
        "store_name": "My Kiosk Store",
        "receipt_footer": "Thank you for your purchase!",
        "currency": "EUR",
    }.items():
        if not db.get(Setting, key):
            db.add(Setting(key=key, value=value))

    if db.query(Category).count() == 0:
        categories = [
            Category(name="Electronics", description="Gadgets and accessories", sort_order=1),
            Category(name="Snacks", description="Quick bites and treats", sort_order=2),
            Category(name="Beverages", description="Drinks and refreshments", sort_order=3),
            Category(name="Clothing", description="Apparel and accessories", sort_order=4),
        ]
        db.add_all(categories)
        db.flush()

        products = [
            Product(name="USB-C Cable", description="2m fast charging cable", price=9.99, stock=50, category_id=categories[0].id),
            Product(name="Wireless Mouse", description="Compact wireless mouse", price=24.99, stock=25, category_id=categories[0].id),
            Product(name="Bluetooth Earbuds", description="True wireless earbuds with case", price=49.99, stock=12, category_id=categories[0].id),
            Product(name="Potato Chips", description="Classic salted chips", price=2.99, stock=100, category_id=categories[1].id),
            Product(name="Chocolate Bar", description="Milk chocolate 100g", price=3.49, stock=80, category_id=categories[1].id),
            Product(name="Trail Mix", description="Nuts and dried fruit", price=5.99, stock=40, category_id=categories[1].id),
            Product(name="Bottled Water", description="500ml still water", price=1.49, stock=200, category_id=categories[2].id),
            Product(name="Cola", description="Carbonated cola 330ml", price=1.99, stock=150, category_id=categories[2].id),
            Product(name="Orange Juice", description="Fresh squeezed 1L", price=4.99, stock=60, category_id=categories[2].id),
            Product(name="Cotton T-Shirt", description="100% cotton, multiple sizes", price=14.99, stock=20, category_id=categories[3].id),
            Product(name="Baseball Cap", description="Adjustable cotton cap", price=12.99, stock=15, category_id=categories[3].id),
        ]
        db.add_all(products)

    db.commit()
