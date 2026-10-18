"""Flask routes for the inventory admin API.

CRUD routes (RESTful):
    GET    /inventory              list items (optional ?brand= and ?q= filters)
    GET    /inventory/<id>         fetch one item
    POST   /inventory              add an item
    PATCH  /inventory/<id>         update an item
    DELETE /inventory/<id>         remove an item

Helper routes:
    GET    /health                       service check
    GET    /inventory/low-stock          items at or below a stock threshold
    POST   /inventory/<id>/enrich        fill in missing details from OpenFoodFacts
    POST   /inventory/import             fetch a product from OpenFoodFacts and add it
    GET    /external/product/<barcode>   look up a product by barcode (no save)
    GET    /external/search?name=        look up products by name (no save)
"""
from flask import Blueprint, jsonify, request

from . import off_client, storage
from .validators import validate_item

api = Blueprint("api", __name__)

ENRICH_FIELDS = ("brands", "ingredients_text", "categories", "quantity",
                 "nutriscore_grade", "image_url")


def error(message, status, details=None):
    body = {"error": message}
    if details:
        body["details"] = details
    return jsonify(body), status


def json_body():
    """Return the JSON object in the request body, or None if it is missing/invalid."""
    data = request.get_json(silent=True)
    return data if isinstance(data, dict) else None


# ------------------------------------------------------------------ helpers
@api.get("/health")
def health():
    return jsonify({"status": "ok", "items": len(storage.inventory)})

@api.get("/")
def index():
    return jsonify({"service": "Inventory Admin API",
                    "endpoints": ["/inventory", "/inventory/<id>", "/inventory/low-stock",
                                  "/external/product/<barcode>", "/external/search?name=",
                                  "/inventory/import", "/health"]})


@api.get("/inventory/low-stock")
def low_stock():
    raw = request.args.get("threshold", "10")
    if not raw.isdigit():
        return error("threshold must be a whole number >= 0.", 400)
    items = [i for i in storage.get_all() if i["stock"] <= int(raw)]
    return jsonify({"threshold": int(raw), "count": len(items), "items": items})


# --------------------------------------------------------------------- CRUD
@api.get("/inventory")
def list_items():
    brand = request.args.get("brand", "").lower()
    query = request.args.get("q", "").lower()
    items = storage.get_all()
    if brand:
        items = [i for i in items if brand in i["brands"].lower()]
    if query:
        items = [i for i in items if query in i["product_name"].lower()]
    return jsonify({"count": len(items), "items": items})


@api.get("/inventory/<int:item_id>")
def get_item(item_id):
    item = storage.get_by_id(item_id)
    if item is None:
        return error(f"Item {item_id} not found.", 404)
    return jsonify(item)


@api.post("/inventory")
def create_item():
    data = json_body()
    if data is None:
        return error("Request body must be a valid JSON object.", 400)
    clean, errors = validate_item(data)
    if errors:
        return error("Validation failed.", 400, errors)
    if clean.get("barcode") and storage.get_by_barcode(clean["barcode"]):
        return error(f"An item with barcode {clean['barcode']} already exists.", 409)
    return jsonify(storage.add_item(clean)), 201


@api.patch("/inventory/<int:item_id>")
def update_item(item_id):
    if storage.get_by_id(item_id) is None:
        return error(f"Item {item_id} not found.", 404)
    data = json_body()
    if data is None:
        return error("Request body must be a valid JSON object.", 400)
    clean, errors = validate_item(data, partial=True)
    if errors:
        return error("Validation failed.", 400, errors)
    other = storage.get_by_barcode(clean.get("barcode"))
    if other and other["id"] != item_id:
        return error(f"An item with barcode {clean['barcode']} already exists.", 409)
    return jsonify(storage.update_item(item_id, clean))


@api.delete("/inventory/<int:item_id>")
def delete_item(item_id):
    removed = storage.delete_item(item_id)
    if removed is None:
        return error(f"Item {item_id} not found.", 404)
    return jsonify({"message": f"Item {item_id} deleted.", "item": removed})


# ----------------------------------------------------- external API routes
@api.get("/external/product/<barcode>")
def external_product(barcode):
    try:
        product = off_client.get_product_by_barcode(barcode)
    except ValueError as exc:
        return error(str(exc), 400)
    if product is None:
        return error(f"No product found for barcode {barcode}.", 404)
    return jsonify({"product": product})


@api.get("/external/search")
def external_search():
    name = request.args.get("name", "")
    try:
        results = off_client.search_products_by_name(name)
    except ValueError as exc:
        return error(str(exc), 400)
    return jsonify({"count": len(results), "results": results})


@api.post("/inventory/import")
def import_product():
    """Look a product up on OpenFoodFacts (barcode or name) and add it to the array."""
    data = json_body()
    if data is None:
        return error("Request body must be a valid JSON object.", 400)
    barcode, name = data.get("barcode"), data.get("name")
    if not barcode and not name:
        return error("Provide 'barcode' or 'name'.", 400)

    # Optional store-specific values: price and stock.
    extras, errors = validate_item({k: data[k] for k in ("price", "stock") if k in data},
                                   partial=True)
    if errors and (data.keys() & {"price", "stock"}):
        return error("Validation failed.", 400, errors)

    try:
        if barcode:
            product = off_client.get_product_by_barcode(barcode)
        else:
            results = off_client.search_products_by_name(name, limit=1)
            product = results[0] if results else None
    except ValueError as exc:
        return error(str(exc), 400)
    if product is None:
        return error("No matching product found on OpenFoodFacts.", 404)

    if product.get("barcode") and storage.get_by_barcode(product["barcode"]):
        return error(f"An item with barcode {product['barcode']} already exists.", 409)

    item = storage.add_item({**product, **extras, "source": "openfoodfacts", "enriched": True})
    return jsonify(item), 201


@api.post("/inventory/<int:item_id>/enrich")
def enrich_item(item_id):
    """Fill in missing details of a stored item using its barcode."""
    item = storage.get_by_id(item_id)
    if item is None:
        return error(f"Item {item_id} not found.", 404)
    if not item.get("barcode"):
        return error("Item has no barcode to look up.", 400)

    overwrite = request.args.get("overwrite", "false").lower() == "true"
    product = off_client.get_product_by_barcode(item["barcode"])
    if product is None:
        return error(f"No product found for barcode {item['barcode']}.", 404)

    changes = {f: product[f] for f in ENRICH_FIELDS
               if product.get(f) and (overwrite or not item.get(f))}
    changes["enriched"] = True
    return jsonify(storage.update_item(item_id, changes))
