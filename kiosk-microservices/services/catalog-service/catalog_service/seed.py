from sqlalchemy.orm import Session

from catalog_service.models import Category, Product


def seed(db: Session) -> None:
    if db.query(Category).count() > 0:
        return
    categories = [
        Category(name="Electronics", description="Gadgets and accessories", sort_order=1),
        Category(name="Snacks", description="Quick bites and treats", sort_order=2),
        Category(name="Beverages", description="Drinks and refreshments", sort_order=3),
        Category(name="Clothing", description="Apparel and accessories", sort_order=4),
    ]
    db.add_all(categories)
    db.flush()
    db.add_all([
        Product(name="USB-C Cable", description="2m fast charging cable", price=9.99, cost_price=5.99, stock=50, category_id=categories[0].id),
        Product(name="Wireless Mouse", description="Compact wireless mouse", price=24.99, cost_price=14.99, stock=25, category_id=categories[0].id),
        Product(name="Bluetooth Earbuds", description="True wireless earbuds with case", price=49.99, cost_price=29.99, stock=12, category_id=categories[0].id),
        Product(name="Potato Chips", description="Classic salted chips", price=2.99, cost_price=1.79, stock=100, category_id=categories[1].id),
        Product(name="Chocolate Bar", description="Milk chocolate 100g", price=3.49, cost_price=2.09, stock=80, category_id=categories[1].id),
        Product(name="Trail Mix", description="Nuts and dried fruit", price=5.99, cost_price=3.59, stock=40, category_id=categories[1].id),
        Product(name="Bottled Water", description="500ml still water", price=1.49, cost_price=0.89, stock=200, category_id=categories[2].id),
        Product(name="Cola", description="Carbonated cola 330ml", price=1.99, cost_price=1.19, stock=150, category_id=categories[2].id),
        Product(name="Orange Juice", description="Fresh squeezed 1L", price=4.99, cost_price=2.99, stock=60, category_id=categories[2].id),
        Product(name="Cotton T-Shirt", description="100% cotton, multiple sizes", price=14.99, cost_price=8.99, stock=20, category_id=categories[3].id),
        Product(name="Baseball Cap", description="Adjustable cotton cap", price=12.99, cost_price=7.79, stock=15, category_id=categories[3].id),
    ])
    db.commit()
