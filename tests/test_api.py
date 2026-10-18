"""Tests for every Flask endpoint. OpenFoodFacts is always mocked."""
from unittest.mock import patch

from app.off_client import ExternalAPIError


# ---------------------------------------------------------------- GET
def test_health(client):
    assert client.get("/health").get_json() == {"status": "ok", "items": 6}

def test_index_lists_endpoints(client):
    assert "/inventory" in client.get("/").get_json()["endpoints"]


def test_get_all_items(client):
    data = client.get("/inventory").get_json()
    assert data["count"] == 6 and data["items"][0]["product_name"] == "Organic Almond Milk"


def test_get_all_with_filters(client):
    assert client.get("/inventory?brand=ferrero").get_json()["count"] == 1
    assert client.get("/inventory?q=cola").get_json()["items"][0]["id"] == 3
    assert client.get("/inventory?q=nothing").get_json()["count"] == 0


def test_get_single_item(client):
    response = client.get("/inventory/2")
    assert response.status_code == 200 and response.get_json()["product_name"] == "Nutella"


def test_get_missing_item_returns_404(client):
    response = client.get("/inventory/999")
    assert response.status_code == 404 and "not found" in response.get_json()["error"]


def test_low_stock(client):
    data = client.get("/inventory/low-stock").get_json()
    assert {i["id"] for i in data["items"]} == {3, 5}
    assert client.get("/inventory/low-stock?threshold=100").get_json()["count"] == 6


def test_low_stock_invalid_threshold(client):
    assert client.get("/inventory/low-stock?threshold=abc").status_code == 400


# --------------------------------------------------------------- POST
def test_create_item(client):
    response = client.post("/inventory", json={"product_name": "Green Tea", "price": 5.5,
                                                "stock": 12, "barcode": "12345678"})
    body = response.get_json()
    assert response.status_code == 201 and body["id"] == 7 and body["price"] == 5.5
    assert client.get("/inventory/7").status_code == 200


def test_create_requires_product_name(client):
    response = client.post("/inventory", json={"price": 1})
    assert response.status_code == 400 and "product_name is required." in response.get_json()["details"]


def test_create_rejects_invalid_values(client):
    response = client.post("/inventory", json={"product_name": "X", "price": -3, "stock": "many"})
    assert response.status_code == 400 and len(response.get_json()["details"]) == 2


def test_create_rejects_non_json_body(client):
    assert client.post("/inventory", data="not json").status_code == 400
    assert client.post("/inventory", json=[1, 2]).status_code == 400


def test_create_duplicate_barcode_conflict(client):
    response = client.post("/inventory", json={"product_name": "Dup", "barcode": "3017620422003"})
    assert response.status_code == 409


# -------------------------------------------------------------- PATCH
def test_patch_updates_only_given_fields(client):
    response = client.patch("/inventory/1", json={"price": 4.25, "stock": 10})
    body = response.get_json()
    assert response.status_code == 200
    assert body["price"] == 4.25 and body["stock"] == 10 and body["product_name"] == "Organic Almond Milk"


def test_patch_missing_item(client):
    assert client.patch("/inventory/999", json={"stock": 1}).status_code == 404


def test_patch_validation_errors(client):
    assert client.patch("/inventory/1", json={"price": "free"}).status_code == 400
    assert client.patch("/inventory/1", json={}).status_code == 400
    assert client.patch("/inventory/1", data="oops").status_code == 400


def test_patch_cannot_change_id(client):
    response = client.patch("/inventory/1", json={"id": 50})
    assert response.status_code == 400 and client.get("/inventory/1").status_code == 200


def test_patch_barcode_conflict(client):
    assert client.patch("/inventory/1", json={"barcode": "3017620422003"}).status_code == 409
    assert client.patch("/inventory/2", json={"barcode": "3017620422003"}).status_code == 200


# ------------------------------------------------------------- DELETE
def test_delete_item(client):
    response = client.delete("/inventory/3")
    assert response.status_code == 200 and response.get_json()["item"]["id"] == 3
    assert client.get("/inventory/3").status_code == 404
    assert client.get("/inventory").get_json()["count"] == 5


def test_delete_missing_item(client):
    assert client.delete("/inventory/999").status_code == 404


def test_unsupported_method_returns_json_405(client):
    response = client.put("/inventory/1", json={})
    assert response.status_code == 405 and "error" in response.get_json()


def test_unknown_route_returns_json_404(client):
    assert client.get("/nope").get_json() == {"error": "Resource not found."}


# ------------------------------------------------- external API routes
def test_external_product_by_barcode(client, sample_product):
    with patch("app.off_client.get_product_by_barcode", return_value=sample_product) as mock:
        response = client.get("/external/product/8076800195057")
    mock.assert_called_once_with("8076800195057")
    assert response.get_json()["product"]["brands"] == "Barilla"


def test_external_product_not_found_and_invalid(client):
    with patch("app.off_client.get_product_by_barcode", return_value=None):
        assert client.get("/external/product/123456789").status_code == 404
    assert client.get("/external/product/abc").status_code == 400  # real validation


def test_external_search(client, sample_product):
    with patch("app.off_client.search_products_by_name", return_value=[sample_product]):
        data = client.get("/external/search?name=spaghetti").get_json()
    assert data["count"] == 1 and data["results"][0]["product_name"] == "Spaghetti n.5"


def test_external_search_requires_name(client):
    assert client.get("/external/search").status_code == 400


def test_external_failure_returns_502(client):
    with patch("app.off_client.get_product_by_barcode", side_effect=ExternalAPIError("down")):
        response = client.get("/external/product/123456789")
    assert response.status_code == 502 and response.get_json()["error"] == "down"


# ---------------------------------------------------- import / enrich
def test_import_by_barcode_adds_to_array(client, sample_product):
    with patch("app.off_client.get_product_by_barcode", return_value=sample_product):
        response = client.post("/inventory/import",
                               json={"barcode": "8076800195057", "price": 2.5, "stock": 30})
    body = response.get_json()
    assert response.status_code == 201 and body["id"] == 7
    assert body["product_name"] == "Spaghetti n.5" and body["source"] == "openfoodfacts"
    assert body["price"] == 2.5 and body["stock"] == 30
    assert client.get("/inventory").get_json()["count"] == 7


def test_import_by_name_uses_first_result(client, sample_product):
    with patch("app.off_client.search_products_by_name", return_value=[sample_product]) as mock:
        response = client.post("/inventory/import", json={"name": "spaghetti"})
    mock.assert_called_once_with("spaghetti", limit=1)
    assert response.status_code == 201 and response.get_json()["price"] == 0.0


def test_import_validation_and_not_found(client):
    assert client.post("/inventory/import", json={}).status_code == 400
    assert client.post("/inventory/import", json={"barcode": "12345678", "price": -1}).status_code == 400
    assert client.post("/inventory/import", data="x").status_code == 400
    with patch("app.off_client.get_product_by_barcode", return_value=None):
        assert client.post("/inventory/import", json={"barcode": "12345678"}).status_code == 404
    with patch("app.off_client.search_products_by_name", return_value=[]):
        assert client.post("/inventory/import", json={"name": "zzz"}).status_code == 404


def test_import_duplicate_barcode(client, sample_product):
    sample_product["barcode"] = "3017620422003"
    with patch("app.off_client.get_product_by_barcode", return_value=sample_product):
        assert client.post("/inventory/import", json={"barcode": "3017620422003"}).status_code == 409


def test_import_external_failure(client):
    with patch("app.off_client.get_product_by_barcode", side_effect=ExternalAPIError("down")):
        assert client.post("/inventory/import", json={"barcode": "12345678"}).status_code == 502


def test_enrich_fills_only_missing_fields(client, sample_product):
    client.post("/inventory", json={"product_name": "My Pasta", "barcode": "8076800195057", "brands": "Mine"})
    with patch("app.off_client.get_product_by_barcode", return_value=sample_product):
        body = client.post("/inventory/7/enrich").get_json()
    assert body["brands"] == "Mine"                      # existing value kept
    assert body["categories"] == "Pasta" and body["enriched"] is True


def test_enrich_overwrite(client, sample_product):
    client.post("/inventory", json={"product_name": "My Pasta", "barcode": "8076800195057", "brands": "Mine"})
    with patch("app.off_client.get_product_by_barcode", return_value=sample_product):
        body = client.post("/inventory/7/enrich?overwrite=true").get_json()
    assert body["brands"] == "Barilla"


def test_enrich_error_cases(client):
    assert client.post("/inventory/999/enrich").status_code == 404
    client.post("/inventory", json={"product_name": "No code"})
    assert client.post("/inventory/7/enrich").status_code == 400
    with patch("app.off_client.get_product_by_barcode", return_value=None):
        assert client.post("/inventory/1/enrich").status_code == 404
