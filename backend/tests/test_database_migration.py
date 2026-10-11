import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

import models  # noqa: F401
from database import Base
from migrate_database import copy_database
from models import Category, Product


def test_database_copy_preserves_ids_and_requires_explicit_replace(tmp_path):
    source = create_engine(f"sqlite:///{tmp_path / 'source.db'}")
    target = create_engine(f"sqlite:///{tmp_path / 'target.db'}")
    Base.metadata.create_all(source)

    with Session(source) as db:
        category = Category(id=17, name="Drinks", description="Cold")
        db.add(category)
        db.flush()
        db.add(
            Product(
                id=29,
                name="Water",
                price=1.5,
                stock=10,
                category_id=category.id,
            )
        )
        db.commit()

    assert copy_database(source, target) == 2
    with Session(target) as db:
        product = db.get(Product, 29)
        assert product is not None
        assert product.category_id == 17
        assert product.category.name == "Drinks"

    with pytest.raises(ValueError, match="already contains data"):
        copy_database(source, target)

    assert copy_database(source, target, replace_target=True) == 2
    with Session(target) as db:
        assert db.query(Product).count() == 1
        assert db.query(Category).count() == 1

    source.dispose()
    target.dispose()
