import pytest

from app import create_app, storage

# A product as returned by app.off_client (already normalised).
SAMPLE_PRODUCT = {
    "barcode": "8076800195057", "product_name": "Spaghetti n.5", "brands": "Barilla",
    "ingredients_text": "Durum wheat semolina, water", "categories": "Pasta",
    "quantity": "500 g", "nutriscore_grade": "a", "image_url": "https://example.com/p.jpg",
}


@pytest.fixture(autouse=True)
def fresh_db():
    """Every test starts with the 6 seeded items (IDs 1-6)."""
    storage.reset_db(seed=True)
    yield
    storage.reset_db(seed=True)


@pytest.fixture
def app():
    return create_app({"TESTING": True})


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def sample_product():
    return dict(SAMPLE_PRODUCT)
