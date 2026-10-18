"""Simulated data storage.

The assignment asks for a mock database held in an array, so all inventory
data lives in the module-level ``inventory`` list. Every item gets a unique
integer ``id``. Items resemble the product data returned by OpenFoodFacts
(product_name, brands, ingredients_text, ...) plus store-specific fields
(price, stock).
"""
from copy import deepcopy
from datetime import datetime, timezone

# Fields every item has, with their default values.
ITEM_DEFAULTS = {
    "barcode": None,
    "product_name": "",
    "brands": "",
    "ingredients_text": "",
    "categories": "",
    "quantity": "",
    "nutriscore_grade": None,
    "image_url": "",
    "price": 0.0,
    "stock": 0,
    "source": "manual",      # "manual", "mock" or "openfoodfacts"
    "enriched": False,       # True once extra details came from OpenFoodFacts
}

# Mock data modelled on OpenFoodFacts product records.
SEED_ITEMS = [
    {"barcode": "025293002114", "product_name": "Organic Almond Milk", "brands": "Silk",
     "ingredients_text": "Filtered water, almonds, cane sugar, sea salt",
     "categories": "Plant-based beverages, Almond milks", "quantity": "1.89 L",
     "nutriscore_grade": "c", "price": 3.99, "stock": 24},
    {"barcode": "3017620422003", "product_name": "Nutella", "brands": "Ferrero",
     "ingredients_text": "Sugar, palm oil, hazelnuts, skim milk powder, cocoa",
     "categories": "Spreads, Hazelnut spreads", "quantity": "400 g",
     "nutriscore_grade": "e", "price": 4.49, "stock": 40},
    {"barcode": "5449000000996", "product_name": "Coca-Cola", "brands": "Coca-Cola",
     "ingredients_text": "Carbonated water, sugar, colour (caramel E150d), phosphoric acid",
     "categories": "Beverages, Sodas", "quantity": "330 ml",
     "nutriscore_grade": "e", "price": 1.99, "stock": 5},
    {"barcode": "7622210449283", "product_name": "Oreo Original", "brands": "Oreo",
     "ingredients_text": "Wheat flour, sugar, palm oil, cocoa powder",
     "categories": "Snacks, Biscuits", "quantity": "154 g",
     "nutriscore_grade": "d", "price": 3.29, "stock": 18},
    {"barcode": "5000157024671", "product_name": "Tomato Ketchup", "brands": "Heinz",
     "ingredients_text": "Tomatoes, spirit vinegar, sugar, salt, spice",
     "categories": "Sauces, Ketchup", "quantity": "460 g",
     "nutriscore_grade": "d", "price": 2.99, "stock": 3},
    {"barcode": "016000275270", "product_name": "Cheerios", "brands": "General Mills",
     "ingredients_text": "Whole grain oats, corn starch, sugar, salt",
     "categories": "Breakfast cereals", "quantity": "306 g",
     "nutriscore_grade": "b", "price": 4.79, "stock": 60},
]

# The "database" array and its ID counter.
inventory = []
_next_id = 1


def _now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def reset_db(seed=True):
    """Empty the array (used at startup and between tests) and optionally re-seed it."""
    global _next_id
    inventory.clear()
    _next_id = 1
    if seed:
        for data in SEED_ITEMS:
            add_item({**data, "source": "mock"})


def get_all():
    return [deepcopy(item) for item in inventory]


def get_by_id(item_id):
    for item in inventory:
        if item["id"] == item_id:
            return deepcopy(item)
    return None


def get_by_barcode(barcode):
    for item in inventory:
        if barcode and item.get("barcode") == barcode:
            return deepcopy(item)
    return None


def add_item(data):
    """Create an item, assign it a new unique ID and append it to the array."""
    global _next_id
    item = {**ITEM_DEFAULTS, **data}
    item["id"] = _next_id
    item["created_at"] = item["updated_at"] = _now()
    _next_id += 1
    inventory.append(item)
    return deepcopy(item)


def update_item(item_id, changes):
    for item in inventory:
        if item["id"] == item_id:
            item.update(changes)
            item["updated_at"] = _now()
            return deepcopy(item)
    return None


def delete_item(item_id):
    for index, item in enumerate(inventory):
        if item["id"] == item_id:
            return inventory.pop(index)
    return None


reset_db()
