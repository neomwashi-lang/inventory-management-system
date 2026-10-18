"""Tests for the CLI.

Most tests route the CLI's HTTP calls into the Flask test client (a real
end-to-end check without a running server). Error handling is tested with
mocked ``requests`` responses.
"""
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
import requests

import cli
from app.off_client import ExternalAPIError


@pytest.fixture
def api(client, monkeypatch):
    """An InventoryClient whose HTTP calls are served by the Flask test client."""
    def fake_request(method, url, timeout=None, params=None, json=None):
        response = client.open(url.replace("http://test", ""), method=method,
                               query_string=params, json=json)
        return SimpleNamespace(status_code=response.status_code,
                               json=lambda: response.get_json(silent=True))
    monkeypatch.setattr(cli.requests, "request", fake_request)
    return cli.InventoryClient("http://test")


def run(api, *argv):
    return cli.main(list(argv), client=api)


# ------------------------------------------------------------ commands
def test_list(api, capsys):
    assert run(api, "list") == 0
    out = capsys.readouterr().out
    assert "Nutella" in out and "6 item(s)." in out


def test_list_with_filter_and_empty(api, capsys):
    run(api, "list", "--brand", "silk")
    assert "1 item(s)." in capsys.readouterr().out
    run(api, "list", "--search", "zzz")
    assert "No items found." in capsys.readouterr().out


def test_view(api, capsys):
    assert run(api, "view", "2") == 0
    out = capsys.readouterr().out
    assert "Ferrero" in out and "Nutri-Score:  E" in out


def test_view_missing_item_prints_error(api, capsys):
    assert run(api, "view", "99") == 1
    assert "Item 99 not found." in capsys.readouterr().err


def test_add(api, capsys):
    assert run(api, "add", "Green Tea", "--brand", "Lipton", "--price", "5.5", "--stock", "9") == 0
    assert "Added item #7" in capsys.readouterr().out
    assert api.get_item(7)["brands"] == "Lipton"


def test_add_invalid_price_and_stock_rejected_by_parser(api, capsys):
    for bad in (["--price", "abc"], ["--price", "-2"], ["--stock", "1.5"], ["--stock", "-1"]):
        with pytest.raises(SystemExit) as exc:
            run(api, "add", "X", *bad)
        assert exc.value.code == 2
    assert api.list_items()["count"] == 6


def test_add_api_validation_error_is_shown(api, capsys):
    assert run(api, "add", "Bad", "--barcode", "12") == 1
    assert "barcode must be 8-14 digits." in capsys.readouterr().err


def test_update_price_and_stock(api, capsys):
    assert run(api, "update", "1", "--price", "9.99", "--stock", "7") == 0
    item = api.get_item(1)
    assert item["price"] == 9.99 and item["stock"] == 7


def test_update_without_changes(api, capsys):
    assert run(api, "update", "1") == 1
    assert "Nothing to update" in capsys.readouterr().err


def test_delete_with_yes_flag(api, capsys):
    assert run(api, "delete", "3", "--yes") == 0
    assert "Item 3 deleted." in capsys.readouterr().out
    assert api.list_items()["count"] == 5


def test_delete_confirmation_cancelled_and_accepted(api, capsys):
    with patch("builtins.input", return_value="n"):
        run(api, "delete", "3")
    assert "Cancelled." in capsys.readouterr().out and api.list_items()["count"] == 6
    with patch("builtins.input", return_value="y"):
        run(api, "delete", "3")
    assert api.list_items()["count"] == 5


def test_low_stock(api, capsys):
    run(api, "low-stock", "--threshold", "5")
    out = capsys.readouterr().out
    assert "Coca-Cola" in out and "Cheerios" not in out


def test_invalid_id_rejected(api):
    for bad in ("abc", "0", "-4"):
        with pytest.raises(SystemExit):
            run(api, "view", bad)


# ------------------------------------------------ external API commands
def test_lookup_barcode(api, sample_product, capsys):
    with patch("app.off_client.get_product_by_barcode", return_value=sample_product):
        assert run(api, "lookup", "--barcode", "8076800195057") == 0
    assert "Spaghetti n.5" in capsys.readouterr().out


def test_lookup_name_and_no_results(api, sample_product, capsys):
    with patch("app.off_client.search_products_by_name", return_value=[sample_product]):
        run(api, "lookup", "--name", "spaghetti")
    assert "1." in capsys.readouterr().out
    with patch("app.off_client.search_products_by_name", return_value=[]):
        run(api, "lookup", "--name", "zzz")
    assert "No products found." in capsys.readouterr().out


def test_lookup_requires_barcode_or_name(api):
    with pytest.raises(SystemExit):
        run(api, "lookup")
    with pytest.raises(SystemExit):
        run(api, "lookup", "--barcode", "1", "--name", "x")


def test_lookup_not_found_and_api_failure(api, capsys):
    with patch("app.off_client.get_product_by_barcode", return_value=None):
        assert run(api, "lookup", "--barcode", "12345678") == 1
    assert "No product found" in capsys.readouterr().err
    with patch("app.off_client.get_product_by_barcode", side_effect=ExternalAPIError("OFF is down")):
        assert run(api, "lookup", "--barcode", "12345678") == 1
    assert "OFF is down" in capsys.readouterr().err


def test_import_adds_external_product(api, sample_product, capsys):
    with patch("app.off_client.get_product_by_barcode", return_value=sample_product):
        assert run(api, "import", "--barcode", "8076800195057", "--price", "2", "--stock", "40") == 0
    item = api.get_item(7)
    assert item["product_name"] == "Spaghetti n.5" and item["stock"] == 40
    assert "Imported from OpenFoodFacts" in capsys.readouterr().out


def test_import_duplicate_reports_conflict(api, sample_product, capsys):
    sample_product["barcode"] = "3017620422003"
    with patch("app.off_client.get_product_by_barcode", return_value=sample_product):
        assert run(api, "import", "--barcode", "3017620422003") == 1
    assert "already exists" in capsys.readouterr().err


def test_enrich(api, sample_product, capsys):
    api.add_item({"product_name": "Pasta", "barcode": "8076800195057"})
    with patch("app.off_client.get_product_by_barcode", return_value=sample_product):
        assert run(api, "enrich", "7") == 0
    assert api.get_item(7)["brands"] == "Barilla"


# ------------------------------------------------------- error handling
def test_connection_error_message(capsys):
    with patch("cli.requests.request", side_effect=requests.ConnectionError()):
        assert cli.main(["list"]) == 1
    assert "Cannot connect to the API" in capsys.readouterr().err


def test_timeout_message(capsys):
    with patch("cli.requests.request", side_effect=requests.Timeout()):
        assert cli.main(["list"]) == 1
    assert "timed out" in capsys.readouterr().err


def test_non_json_server_error(capsys):
    response = MagicMock(status_code=500)
    response.json.side_effect = ValueError()
    with patch("cli.requests.request", return_value=response):
        assert cli.main(["list"]) == 1
    assert "HTTP 500" in capsys.readouterr().err


def test_client_builds_expected_requests():
    response = MagicMock(status_code=200)
    response.json.return_value = {}
    with patch("cli.requests.request", return_value=response) as mock:
        client = cli.InventoryClient("http://host:1234/")
        client.update_item(4, {"stock": 2})
        client.delete_item(4)
    assert mock.call_args_list[0].args == ("PATCH", "http://host:1234/inventory/4")
    assert mock.call_args_list[0].kwargs["json"] == {"stock": 2}
    assert mock.call_args_list[1].args == ("DELETE", "http://host:1234/inventory/4")


# --------------------------------------------------- interactive menu
def test_menu_list_and_exit(api, capsys):
    with patch("builtins.input", side_effect=["1", "", "0"]):
        assert cli.main(["menu"], client=api) == 0
    out = capsys.readouterr().out
    assert "Inventory Admin Portal" in out and "Nutella" in out and "Goodbye!" in out


def test_menu_add_item_with_retry_on_invalid_price(api, capsys):
    inputs = ["3", "Menu Item", "", "", "abc", "2.5", "4", "0"]
    with patch("builtins.input", side_effect=inputs):
        cli.main([], client=api)
    assert "Invalid input" in capsys.readouterr().out
    item = api.get_item(7)
    assert item["price"] == 2.5 and item["stock"] == 4


def test_menu_update_delete_and_bad_choice(api, capsys):
    inputs = ["x", "4", "1", "1.25", "", "5", "2", "y", "0"]
    with patch("builtins.input", side_effect=inputs):
        cli.main([], client=api)
    assert "Invalid choice" in capsys.readouterr().out
    assert api.get_item(1)["price"] == 1.25
    assert api.list_items()["count"] == 5


def test_menu_find_by_name_and_add_result(api, sample_product, capsys):
    inputs = ["7", "spaghetti", "1", "2.0", "15", "0"]
    with patch("app.off_client.search_products_by_name", return_value=[sample_product]), \
         patch("app.off_client.get_product_by_barcode", return_value=sample_product), \
         patch("builtins.input", side_effect=inputs):
        cli.main([], client=api)
    assert "Added to inventory as item #7" in capsys.readouterr().out
    assert api.get_item(7)["stock"] == 15


def test_menu_shows_errors_and_continues(api, capsys):
    with patch("builtins.input", side_effect=["2", "99", "0"]):
        assert cli.main([], client=api) == 0
    assert "Item 99 not found." in capsys.readouterr().err


def test_menu_handles_eof(api):
    with patch("builtins.input", side_effect=EOFError):
        assert cli.main([], client=api) == 0
