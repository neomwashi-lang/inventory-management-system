"""Tests for the OpenFoodFacts client. requests.get is mocked; no network is used."""
from unittest.mock import MagicMock, patch

import pytest
import requests

from app import off_client
from app.off_client import ExternalAPIError

RAW = {"code": "3017620422003", "product_name": "Nutella", "brands": "Ferrero",
       "ingredients_text": "Sugar, palm oil", "categories": "Spreads", "quantity": "400 g",
       "nutriscore_grade": "E", "image_front_url": "https://img/n.jpg"}


def fake_response(status=200, payload=None, json_error=False):
    response = MagicMock(status_code=status)
    if json_error:
        response.json.side_effect = ValueError("bad json")
    else:
        response.json.return_value = payload
    return response


def test_barcode_lookup_success_and_request_details():
    with patch("app.off_client.requests.get",
               return_value=fake_response(payload={"status": 1, "product": RAW})) as mock_get:
        product = off_client.get_product_by_barcode(" 3017620422003 ")
    url = mock_get.call_args.args[0]
    assert url == "https://world.openfoodfacts.org/api/v2/product/3017620422003.json"
    assert "User-Agent" in mock_get.call_args.kwargs["headers"]
    assert mock_get.call_args.kwargs["timeout"] == off_client.TIMEOUT_SECONDS
    assert product["product_name"] == "Nutella" and product["nutriscore_grade"] == "e"
    assert product["image_url"] == "https://img/n.jpg"


def test_barcode_not_found_status_zero():
    with patch("app.off_client.requests.get",
               return_value=fake_response(payload={"status": 0, "status_verbose": "not found"})):
        assert off_client.get_product_by_barcode("12345678") is None


def test_barcode_http_404_returns_none():
    with patch("app.off_client.requests.get", return_value=fake_response(404, {})):
        assert off_client.get_product_by_barcode("12345678") is None


def test_barcode_must_be_digits():
    with pytest.raises(ValueError):
        off_client.get_product_by_barcode("abc123")


@pytest.mark.parametrize("error, text", [
    (requests.Timeout(), "timed out"),
    (requests.ConnectionError(), "connect"),
])
def test_network_errors_become_external_api_error(error, text):
    with patch("app.off_client.requests.get", side_effect=error):
        with pytest.raises(ExternalAPIError, match=text):
            off_client.get_product_by_barcode("12345678")


def test_server_error_status():
    with patch("app.off_client.requests.get", return_value=fake_response(500, {})):
        with pytest.raises(ExternalAPIError, match="500"):
            off_client.get_product_by_barcode("12345678")


def test_invalid_json_response():
    with patch("app.off_client.requests.get", return_value=fake_response(json_error=True)):
        with pytest.raises(ExternalAPIError, match="invalid JSON"):
            off_client.get_product_by_barcode("12345678")


def test_name_search_returns_normalised_results():
    payload = {"products": [RAW, {"code": "1", "product_name": ""}, {"product_name": "No code"}]}
    with patch("app.off_client.requests.get", return_value=fake_response(payload=payload)) as mock_get:
        results = off_client.search_products_by_name("nutella", limit=3)
    params = mock_get.call_args.kwargs["params"]
    assert params["search_terms"] == "nutella" and params["page_size"] == 3
    assert len(results) == 1 and results[0]["brands"] == "Ferrero"


def test_name_search_empty_results_and_blank_name():
    with patch("app.off_client.requests.get", return_value=fake_response(payload={"products": []})):
        assert off_client.search_products_by_name("zzzz") == []
    with pytest.raises(ValueError):
        off_client.search_products_by_name("  ")


def test_name_search_http_error():
    with patch("app.off_client.requests.get", return_value=fake_response(503, {})):
        with pytest.raises(ExternalAPIError):
            off_client.search_products_by_name("milk")


def test_normalize_handles_missing_fields():
    product = off_client.normalize_product({"nutriscore_grade": "unknown"}, fallback_barcode="12345678")
    assert product["product_name"] == "Unnamed product" and product["barcode"] == "12345678"
    assert product["nutriscore_grade"] is None and product["brands"] == ""
