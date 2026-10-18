# NEO MWASHI
# Inventory Management System – Admin Portal

A Flask REST API and command-line interface for managing a small retailer's inventory.
Product details are supplemented with live data from the
[OpenFoodFacts API](https://openfoodfacts.github.io/openfoodfacts-server/api/).

| Part | File(s) |
|------|---------|
| REST API (CRUD + helper routes) | `app/routes.py` |
| Simulated storage (an array) | `app/storage.py` |
| Input validation | `app/validators.py` |
| OpenFoodFacts integration | `app/off_client.py` |
| CLI (commands + interactive menu) | `cli.py` |
| Unit tests (pytest + unittest.mock) | `tests/` |
| Design notes / Postman collection | `docs/` |

## Installation and setup

Requires Python 3.9+.

```bash
git clone <your-repo-url>
cd inventory-management-system
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### Run the API (Terminal 1)
```bash
python run.py                   # http://127.0.0.1:5000, Flask debug mode on
```
Use `PORT=5001 python run.py` if port 5000 is taken (macOS AirPlay uses it).

### Run the CLI (Terminal 2)
```bash
python cli.py                   # interactive menu
python cli.py --help            # all commands
```
Point the CLI at another address with `--api-url http://127.0.0.1:5001` or the
`INVENTORY_API_URL` environment variable.

### Run the tests
```bash
python -m pytest -v
```
No network is needed: OpenFoodFacts calls are mocked with `unittest.mock`.

## Data model

Data is stored in an in-memory array (resets when the server restarts) seeded with 6 products.
Fields mirror OpenFoodFacts names plus store fields:

```json
{
  "id": 1, "barcode": "025293002114", "product_name": "Organic Almond Milk",
  "brands": "Silk", "ingredients_text": "Filtered water, almonds, cane sugar, sea salt",
  "categories": "Plant-based beverages", "quantity": "1.89 L", "nutriscore_grade": "c",
  "image_url": "", "price": 3.99, "stock": 24,
  "source": "mock", "enriched": false,
  "created_at": "2025-01-01T12:00:00+00:00", "updated_at": "2025-01-01T12:00:00+00:00"
}
```

## API endpoints

All responses are JSON. Errors look like `{"error": "message", "details": [...]}`.

### CRUD
| Method | Route | Description | Success | Errors |
|--------|-------|-------------|---------|--------|
| GET | `/inventory` | List items. Filters: `?brand=`, `?q=` (name) | 200 | – |
| GET | `/inventory/<id>` | Fetch one item | 200 | 404 |
| POST | `/inventory` | Add item. Body requires `product_name`; optional `price`, `stock`, `barcode`, `brands`, … | 201 | 400, 409 duplicate barcode |
| PATCH | `/inventory/<id>` | Update any of the fields above | 200 | 400, 404, 409 |
| DELETE | `/inventory/<id>` | Remove item | 200 | 404 |

### Helper routes
| Method | Route | Description |
|--------|-------|-------------|
| GET | `/health` | Service check |
| GET | `/inventory/low-stock?threshold=10` | Items with stock at or below the threshold |
| GET | `/external/product/<barcode>` | Look up a product on OpenFoodFacts by barcode (not saved) |
| GET | `/external/search?name=<text>` | Search OpenFoodFacts by name (not saved) |
| POST | `/inventory/import` | Body `{"barcode"` or `"name"`, optional `"price"`, `"stock"}` – fetch from OpenFoodFacts **and add to the inventory** (201, 404 not found, 409 duplicate, 502 API down) |
| POST | `/inventory/<id>/enrich[?overwrite=true]` | Fill missing details of a stored item using its barcode |

Example:
```bash
curl -X POST http://127.0.0.1:5000/inventory -H "Content-Type: application/json" \
     -d '{"product_name": "Green Tea", "price": 5.5, "stock": 12}'
curl -X PATCH http://127.0.0.1:5000/inventory/1 -H "Content-Type: application/json" \
     -d '{"price": 4.25}'
```

## CLI usage

| Task | Command |
|------|---------|
| View all items | `python cli.py list` / `list --brand Silk` / `list --search milk` |
| View one item | `python cli.py view 2` |
| Add item | `python cli.py add "Green Tea" --brand Lipton --barcode 12345678 --price 5.50 --stock 12` |
| Update price/stock | `python cli.py update 1 --price 4.25 --stock 30` |
| Delete item | `python cli.py delete 3` (asks to confirm; `--yes` skips) |
| Find item on OpenFoodFacts | `python cli.py lookup --barcode 3017620422003` or `lookup --name nutella` |
| Find on API and add it | `python cli.py import --barcode 3017620422003 --price 4.49 --stock 20` |
| Low stock | `python cli.py low-stock --threshold 5` |
| Enrich stored item | `python cli.py enrich 2` |
| Interactive menu | `python cli.py` or `python cli.py menu` |

Sample session:
```
$ python cli.py list --search cola
ID  Name       Brand      Barcode        Price  Stock
-------------------------------------------------------
3   Coca-Cola  Coca-Cola  5449000000996  $1.99  5

$ python cli.py update 3 --stock 48
Updated item #3: ...

$ python cli.py add "Tea" --price abc
cli.py add: error: argument --price: 'abc' is not a valid price.
```

### Error handling
* Invalid input (negative price, non-numeric stock, bad IDs) is rejected by the CLI and again by the API.
* API server down → `Error: Cannot connect to the API at ... Is the server running (python run.py)?`
* OpenFoodFacts down/timeout → the API returns 502 and the CLI prints the message; nothing crashes.
* The CLI exits with code `0` on success, `1` on runtime errors, `2` on invalid arguments.

## Testing

`pytest` with `unittest.mock`; 85 tests, ~96% coverage:

| File | Covers |
|------|--------|
| `tests/test_storage.py` | Array storage, ID assignment, validators |
| `tests/test_api.py` | GET / POST / PATCH / DELETE, helper routes, error codes, import/enrich |
| `tests/test_off_client.py` | OpenFoodFacts client with mocked responses, timeouts, bad JSON |
| `tests/test_cli.py` | Every CLI command, argument validation, error handling, interactive menu |

Debugging: the server runs in Flask debug mode (`python run.py`) and
`docs/postman_collection.json` can be imported into Postman to exercise every endpoint.

## Project structure
```
app/            Flask package (factory, routes, storage, validators, OpenFoodFacts client)
cli.py          Command-line interface
run.py          Server entry point
tests/          pytest suite
docs/           Design document + Postman collection
scripts/        git_workflow.sh (branch + pull-request workflow)
```

## Git workflow
Each feature was developed on its own branch and merged through a pull request
(`feature/storage-and-validation`, `feature/openfoodfacts-client`, `feature/flask-crud-api`,
`feature/cli-frontend`, `docs/readme-and-design`), and merged branches were deleted.

## Maintainability
Small single-purpose modules, docstrings on every module/function, one place for validation,
the storage layer isolated behind functions (swap the array for a real database without touching routes),
and the app factory pattern for easy testing.
