"""Tests for the array-based mock database and validators."""
from app import storage
from app.validators import validate_item


def test_seed_data_has_unique_ids():
    ids = [i["id"] for i in storage.get_all()]
    assert len(ids) == 6 and len(set(ids)) == 6


def test_add_item_assigns_next_id_and_defaults():
    item = storage.add_item({"product_name": "Tea"})
    assert item["id"] == 7 and item["stock"] == 0 and item["price"] == 0.0
    assert storage.get_by_id(7)["product_name"] == "Tea"


def test_ids_are_not_reused_after_delete():
    storage.delete_item(6)
    assert storage.add_item({"product_name": "New"})["id"] == 7


def test_update_and_delete_missing_return_none():
    assert storage.update_item(99, {"stock": 1}) is None
    assert storage.delete_item(99) is None


def test_get_returns_copy_not_reference():
    storage.get_by_id(1)["stock"] = 999
    assert storage.get_by_id(1)["stock"] == 24


def test_validator_accepts_valid_payload():
    clean, errors = validate_item({"product_name": " Tea ", "price": 2, "stock": 3})
    assert errors == [] and clean == {"product_name": "Tea", "price": 2.0, "stock": 3}


def test_validator_rejects_bad_values():
    _, errors = validate_item({"product_name": "", "price": -1, "stock": 1.5,
                               "barcode": "abc", "nutriscore_grade": "z", "brands": 5, "x": 1})
    assert len(errors) == 7


def test_validator_rejects_booleans_as_numbers():
    _, errors = validate_item({"product_name": "A", "price": True, "stock": True})
    assert len(errors) == 2


def test_partial_validation_requires_some_field():
    assert validate_item({}, partial=True)[1]
    assert validate_item({"stock": 4}, partial=True) == ({"stock": 4}, [])
