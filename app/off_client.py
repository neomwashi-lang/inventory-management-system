"""Client for the OpenFoodFacts API (https://openfoodfacts.github.io/openfoodfacts-server/api/).

Two lookups are supported:
  * by barcode - GET /api/v2/product/{barcode}.json
  * by name    - GET /cgi/search.pl?search_terms=...&json=1

Responses are normalised to the same field names used by our inventory items.
Network problems raise ``ExternalAPIError`` so callers can show a clean message.
"""
import requests

BASE_URL = "https://world.openfoodfacts.org"
# OpenFoodFacts asks every app to send a custom User-Agent.
USER_AGENT = "InventoryAdminPortal/1.0 (student project by Neo Mwashi; leonmwashi@student.moringa.com)"
TIMEOUT_SECONDS = 10
FIELDS = "code,product_name,brands,ingredients_text,categories,quantity,nutriscore_grade,image_front_url"


class ExternalAPIError(Exception):
    """Raised when OpenFoodFacts cannot be reached or returns unusable data."""


def _fetch(url, params=None):
    try:
        return requests.get(url, params=params, headers={"User-Agent": USER_AGENT},
                            timeout=TIMEOUT_SECONDS)
    except requests.Timeout as exc:
        raise ExternalAPIError("OpenFoodFacts request timed out.") from exc
    except requests.RequestException as exc:
        raise ExternalAPIError("Could not connect to OpenFoodFacts.") from exc


def _json(response):
    try:
        return response.json()
    except ValueError as exc:
        raise ExternalAPIError("OpenFoodFacts returned invalid JSON.") from exc


def normalize_product(raw, fallback_barcode=None):
    """Convert an OpenFoodFacts product record into inventory field names."""
    grade = str(raw.get("nutriscore_grade") or "").lower()
    return {
        "barcode": str(raw.get("code") or fallback_barcode or "") or None,
        "product_name": (raw.get("product_name") or "").strip() or "Unnamed product",
        "brands": raw.get("brands") or "",
        "ingredients_text": raw.get("ingredients_text") or "",
        "categories": raw.get("categories") or "",
        "quantity": raw.get("quantity") or "",
        "nutriscore_grade": grade if grade in {"a", "b", "c", "d", "e"} else None,
        "image_url": raw.get("image_front_url") or "",
    }


def get_product_by_barcode(barcode):
    """Return a normalised product dict, or ``None`` if the barcode is unknown."""
    barcode = str(barcode).strip()
    if not barcode.isdigit():
        raise ValueError("Barcode must contain digits only.")

    response = _fetch(f"{BASE_URL}/api/v2/product/{barcode}.json", {"fields": FIELDS})
    if response.status_code == 404:
        return None
    if response.status_code != 200:
        raise ExternalAPIError(f"OpenFoodFacts returned HTTP {response.status_code}.")

    data = _json(response)
    if data.get("status") != 1 or not data.get("product"):
        return None
    return normalize_product(data["product"], fallback_barcode=barcode)


def search_products_by_name(name, limit=5):
    """Return a list of normalised products matching ``name`` (may be empty)."""
    name = (name or "").strip()
    if not name:
        raise ValueError("Product name must not be empty.")

    params = {"search_terms": name, "search_simple": 1, "action": "process",
              "json": 1, "page_size": limit, "fields": FIELDS}
    response = _fetch(f"{BASE_URL}/cgi/search.pl", params)
    if response.status_code != 200:
        raise ExternalAPIError(f"OpenFoodFacts returned HTTP {response.status_code}.")

    products = _json(response).get("products") or []
    return [normalize_product(p) for p in products if p.get("product_name") and p.get("code")]
