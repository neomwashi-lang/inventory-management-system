# Design Document

## 1. Problem
Employees need to add, view, edit and delete inventory items, and look up product details
on OpenFoodFacts to fill in or supplement what the store has. Data is held in an array
(simulated storage); a CLI is the user interface; Flask endpoints run on each user action.

## 2. Route design

| Route | Input | Output | Changes in data | Triggered by CLI |
|-------|-------|--------|-----------------|------------------|
| `GET /inventory` | optional `brand`, `q` | `{count, items[]}` | none | `list`, menu 1 |
| `GET /inventory/<id>` | id in path | item | none | `view`, menu 2 |
| `POST /inventory` | JSON: `product_name` (req), price, stock, barcode, … | created item (201) | appends item with new ID | `add`, menu 3 |
| `PATCH /inventory/<id>` | id + any editable fields | updated item | modifies item in place, updates `updated_at` | `update`, menu 4 |
| `DELETE /inventory/<id>` | id | message + removed item | removes item | `delete`, menu 5 |
| `GET /inventory/low-stock` | `threshold` | `{threshold, count, items[]}` | none | `low-stock`, menu 8 |
| `GET /external/product/<barcode>` | barcode | `{product}` | none | `lookup --barcode`, menu 6 |
| `GET /external/search` | `name` | `{count, results[]}` | none | `lookup --name`, menu 7 |
| `POST /inventory/import` | `barcode` or `name`, price, stock | created item | appends item built from OpenFoodFacts data | `import`, menu 7 |
| `POST /inventory/<id>/enrich` | id, `overwrite` | updated item | fills blank fields from OpenFoodFacts | `enrich`, menu 9 |
| `GET /health` | – | status | none | – |

Status codes: 200/201 success, 400 invalid input, 404 not found, 409 duplicate barcode,
502 OpenFoodFacts unavailable.

## 3. Mock database
An array of dicts in `app/storage.py`, resembling OpenFoodFacts' `product` object
(`product_name`, `brands`, `ingredients_text`, `categories`, `quantity`, `nutriscore_grade`, …)
plus `id`, `barcode`, `price`, `stock`, `source`, `enriched`, timestamps. IDs are unique and never reused.

## 4. External API
OpenFoodFacts v2: `GET /api/v2/product/{barcode}.json` and `GET /cgi/search.pl?search_terms=…&json=1`.
Responses are normalised in `normalize_product()` so inventory items use the same field names.
Failures (timeout, no connection, HTTP error, invalid JSON) raise `ExternalAPIError` → HTTP 502.

## 5. CLI mock-up
```
=== Inventory Admin Portal ===
 1. List inventory          6. Find product on OpenFoodFacts (barcode)
 2. View item               7. Find product on OpenFoodFacts (name) and add it
 3. Add item                8. Show low-stock items
 4. Update price / stock    9. Enrich item from OpenFoodFacts
 5. Delete item             0. Exit
Choose an option: 7
Product name: nutella
1.  Nutella  [3017620422003]
    Brand: Ferrero | Quantity: 400 g | Nutri-Score: E
Add which result? 1-1 (optional): 1
Price [0.0]: 4.49
Stock [0]: 20
Added to inventory as item #7.
```

## 6. Flow of "find on API and add"
CLI `import`/menu 7 → `POST /inventory/import` → `off_client` → OpenFoodFacts →
normalised product → `storage.add_item()` → item with new ID returned to the CLI.
