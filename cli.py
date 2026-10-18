#!/usr/bin/env python3
"""Command-line interface for the inventory admin API.

Run ``python cli.py --help`` for the commands, or run ``python cli.py`` with no
arguments to open the interactive menu. The Flask server (``python run.py``)
must be running. Set --api-url or INVENTORY_API_URL to use a different address.
"""
import argparse
import os
import sys

import requests

DEFAULT_API_URL = os.environ.get("INVENTORY_API_URL", "http://127.0.0.1:5000")


class APIError(Exception):
    """A readable error from the API, the network, or user input."""

    def __init__(self, message, status_code=None):
        super().__init__(message)
        self.status_code = status_code


# ---------------------------------------------------------------- API client
class InventoryClient:
    """Thin wrapper around the Flask API. Every method returns parsed JSON."""

    def __init__(self, base_url=DEFAULT_API_URL, timeout=20):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def _call(self, method, path, **kwargs):
        url = f"{self.base_url}{path}"
        try:
            response = requests.request(method, url, timeout=self.timeout, **kwargs)
        except requests.Timeout:
            raise APIError(f"The request to {url} timed out.")
        except requests.ConnectionError:
            raise APIError(f"Cannot connect to the API at {self.base_url}. "
                           "Is the server running (python run.py)?")
        except requests.RequestException as exc:
            raise APIError(f"Request failed: {exc}")

        try:
            payload = response.json() or {}
        except ValueError:
            payload = {}
        if response.status_code >= 400:
            message = payload.get("error") or f"Server returned HTTP {response.status_code}."
            if payload.get("details"):
                message += " " + " ".join(payload["details"])
            raise APIError(message, response.status_code)
        return payload

    def list_items(self, brand=None, q=None):
        params = {k: v for k, v in {"brand": brand, "q": q}.items() if v}
        return self._call("GET", "/inventory", params=params)

    def get_item(self, item_id):
        return self._call("GET", f"/inventory/{item_id}")

    def add_item(self, data):
        return self._call("POST", "/inventory", json=data)

    def update_item(self, item_id, data):
        return self._call("PATCH", f"/inventory/{item_id}", json=data)

    def delete_item(self, item_id):
        return self._call("DELETE", f"/inventory/{item_id}")

    def low_stock(self, threshold=10):
        return self._call("GET", "/inventory/low-stock", params={"threshold": threshold})

    def lookup_barcode(self, barcode):
        return self._call("GET", f"/external/product/{barcode}")

    def lookup_name(self, name):
        return self._call("GET", "/external/search", params={"name": name})

    def import_product(self, data):
        return self._call("POST", "/inventory/import", json=data)

    def enrich(self, item_id, overwrite=False):
        return self._call("POST", f"/inventory/{item_id}/enrich",
                          params={"overwrite": str(overwrite).lower()})


# ----------------------------------------------------- input validators
def price_type(value):
    try:
        number = float(value)
    except ValueError:
        raise argparse.ArgumentTypeError(f"'{value}' is not a valid price.")
    if number < 0:
        raise argparse.ArgumentTypeError("price cannot be negative.")
    return number


def stock_type(value):
    try:
        number = int(value)
    except ValueError:
        raise argparse.ArgumentTypeError(f"'{value}' is not a whole number.")
    if number < 0:
        raise argparse.ArgumentTypeError("stock cannot be negative.")
    return number


def id_type(value):
    try:
        number = int(value)
    except ValueError:
        raise argparse.ArgumentTypeError(f"'{value}' is not a valid item ID.")
    if number < 1:
        raise argparse.ArgumentTypeError("item ID must be 1 or greater.")
    return number


# -------------------------------------------------------------- formatting
def _clip(text, width):
    text = str(text or "")
    return text if len(text) <= width else text[:width - 1] + "…"


def print_table(items):
    if not items:
        print("No items found.")
        return
    headers = ["ID", "Name", "Brand", "Barcode", "Price", "Stock"]
    rows = [[str(i["id"]), _clip(i["product_name"], 28), _clip(i["brands"], 16),
             i.get("barcode") or "-", f"${i['price']:.2f}", str(i["stock"])] for i in items]
    widths = [max(len(h), *(len(r[c]) for r in rows)) for c, h in enumerate(headers)]
    line = "  ".join(h.ljust(w) for h, w in zip(headers, widths))
    print(line)
    print("-" * len(line))
    for row in rows:
        print("  ".join(cell.ljust(w) for cell, w in zip(row, widths)))


def print_item(item):
    print(f"ID:           {item['id']}")
    print(f"Name:         {item['product_name']}")
    print(f"Brand:        {item['brands'] or '-'}")
    print(f"Barcode:      {item.get('barcode') or '-'}")
    print(f"Price:        ${item['price']:.2f}")
    print(f"Stock:        {item['stock']}")
    print(f"Quantity:     {item['quantity'] or '-'}")
    print(f"Categories:   {item['categories'] or '-'}")
    print(f"Ingredients:  {item['ingredients_text'] or '-'}")
    print(f"Nutri-Score:  {(item.get('nutriscore_grade') or '-').upper()}")
    print(f"Source:       {item['source']} (enriched: {'yes' if item['enriched'] else 'no'})")


def print_external(product):
    print(f"  {product['product_name']}  [{product['barcode']}]")
    print(f"  Brand: {product['brands'] or '-'} | Quantity: {product['quantity'] or '-'} | "
          f"Nutri-Score: {(product.get('nutriscore_grade') or '-').upper()}")


# ---------------------------------------------------------------- commands
def cmd_list(client, args):
    data = client.list_items(brand=args.brand, q=args.search)
    print_table(data["items"])
    print(f"\n{data['count']} item(s).")


def cmd_view(client, args):
    print_item(client.get_item(args.id))


def cmd_add(client, args):
    payload = {"product_name": args.name, "price": args.price, "stock": args.stock}
    for field, value in (("brands", args.brand), ("barcode", args.barcode),
                         ("ingredients_text", args.ingredients),
                         ("categories", args.categories), ("quantity", args.quantity)):
        if value:
            payload[field] = value
    item = client.add_item(payload)
    print(f"Added item #{item['id']}:")
    print_item(item)


def cmd_update(client, args):
    payload = {}
    for field, value in (("price", args.price), ("stock", args.stock),
                         ("product_name", args.name), ("brands", args.brand)):
        if value is not None:
            payload[field] = value
    if not payload:
        raise APIError("Nothing to update. Use --price, --stock, --name or --brand.")
    item = client.update_item(args.id, payload)
    print(f"Updated item #{item['id']}:")
    print_item(item)


def cmd_delete(client, args):
    item = client.get_item(args.id)  # fail early (404) if it does not exist
    if not args.yes:
        answer = input(f"Delete '{item['product_name']}' (ID {args.id})? [y/N]: ")
        if answer.strip().lower() not in ("y", "yes"):
            print("Cancelled.")
            return
    print(client.delete_item(args.id)["message"])


def cmd_lookup(client, args):
    """Find a product on OpenFoodFacts without saving it."""
    if args.barcode:
        print_external(client.lookup_barcode(args.barcode)["product"])
    else:
        data = client.lookup_name(args.name)
        if not data["results"]:
            print("No products found.")
        for number, product in enumerate(data["results"], start=1):
            print(f"{number}.", end="")
            print_external(product)


def cmd_import(client, args):
    """Find a product on OpenFoodFacts and add it to the inventory."""
    payload = {"price": args.price, "stock": args.stock}
    payload.update({"barcode": args.barcode} if args.barcode else {"name": args.name})
    item = client.import_product(payload)
    print(f"Imported from OpenFoodFacts as item #{item['id']}:")
    print_item(item)


def cmd_low_stock(client, args):
    data = client.low_stock(args.threshold)
    print(f"Items with stock <= {data['threshold']}:")
    print_table(data["items"])


def cmd_enrich(client, args):
    item = client.enrich(args.id, overwrite=args.overwrite)
    print(f"Item #{item['id']} enriched with OpenFoodFacts data:")
    print_item(item)


# ----------------------------------------------------------- interactive menu
MENU = """
=== Inventory Admin Portal ===
 1. List inventory          6. Find product on OpenFoodFacts (barcode)
 2. View item               7. Find product on OpenFoodFacts (name) and add it
 3. Add item                8. Show low-stock items
 4. Update price / stock    9. Enrich item from OpenFoodFacts
 5. Delete item             0. Exit"""


def ask(prompt, cast=str, required=True, default=None):
    """Prompt until the input is valid. Blank returns ``default`` (or None if optional)."""
    suffix = f" [{default}]" if default is not None else "" if required else " (optional)"
    while True:
        raw = input(f"{prompt}{suffix}: ").strip()
        if not raw:
            if default is not None:
                return default
            if not required:
                return None
            print("  A value is required.")
            continue
        try:
            return cast(raw)
        except (ValueError, argparse.ArgumentTypeError) as exc:
            print(f"  Invalid input: {exc}")


def menu_list(client):
    cmd_list(client, argparse.Namespace(brand=None, search=ask("Search by name", required=False)))


def menu_view(client):
    cmd_view(client, argparse.Namespace(id=ask("Item ID", id_type)))


def menu_add(client):
    cmd_add(client, argparse.Namespace(
        name=ask("Product name"), brand=ask("Brand", required=False),
        barcode=ask("Barcode", required=False), ingredients=None, categories=None,
        quantity=None, price=ask("Price", price_type, default=0.0),
        stock=ask("Stock", stock_type, default=0)))


def menu_update(client):
    item_id = ask("Item ID", id_type)
    cmd_update(client, argparse.Namespace(
        id=item_id, name=None, brand=None,
        price=ask("New price", price_type, required=False),
        stock=ask("New stock", stock_type, required=False)))


def menu_delete(client):
    cmd_delete(client, argparse.Namespace(id=ask("Item ID", id_type), yes=False))


def menu_lookup_barcode(client):
    cmd_lookup(client, argparse.Namespace(barcode=ask("Barcode"), name=None))


def menu_lookup_name(client):
    results = client.lookup_name(ask("Product name"))["results"]
    if not results:
        print("No products found.")
        return
    for number, product in enumerate(results, start=1):
        print(f"{number}.", end="")
        print_external(product)
    choice = ask(f"Add which result? 1-{len(results)}", int, required=False)
    if choice is None:
        return
    if not 1 <= choice <= len(results):
        raise APIError("That number is not in the list.")
    item = client.import_product({"barcode": results[choice - 1]["barcode"],
                                  "price": ask("Price", price_type, default=0.0),
                                  "stock": ask("Stock", stock_type, default=0)})
    print(f"Added to inventory as item #{item['id']}.")


def menu_low_stock(client):
    cmd_low_stock(client, argparse.Namespace(threshold=ask("Threshold", stock_type, default=10)))


def menu_enrich(client):
    cmd_enrich(client, argparse.Namespace(id=ask("Item ID", id_type), overwrite=False))


MENU_ACTIONS = {"1": menu_list, "2": menu_view, "3": menu_add, "4": menu_update,
                "5": menu_delete, "6": menu_lookup_barcode, "7": menu_lookup_name,
                "8": menu_low_stock, "9": menu_enrich}


def cmd_menu(client, args=None):
    while True:
        print(MENU)
        try:
            choice = input("Choose an option: ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return 0
        if choice == "0":
            print("Goodbye!")
            return 0
        action = MENU_ACTIONS.get(choice)
        if action is None:
            print("Invalid choice. Enter a number from 0 to 9.")
            continue
        try:
            action(client)
        except (APIError, ValueError) as exc:
            print(f"Error: {exc}", file=sys.stderr)
        except (EOFError, KeyboardInterrupt):
            print()
            return 0


# ----------------------------------------------------------- argument parser
def build_parser():
    parser = argparse.ArgumentParser(prog="cli.py", description="Inventory admin CLI.")
    parser.add_argument("--api-url", default=DEFAULT_API_URL,
                        help=f"API base URL (default: {DEFAULT_API_URL})")
    sub = parser.add_subparsers(dest="command")

    p = sub.add_parser("list", help="List inventory items")
    p.add_argument("--brand")
    p.add_argument("--search", help="filter by product name")
    p.set_defaults(func=cmd_list)

    p = sub.add_parser("view", help="Show one item's details")
    p.add_argument("id", type=id_type)
    p.set_defaults(func=cmd_view)

    p = sub.add_parser("add", help="Add a new item")
    p.add_argument("name")
    p.add_argument("--brand")
    p.add_argument("--barcode")
    p.add_argument("--ingredients")
    p.add_argument("--categories")
    p.add_argument("--quantity")
    p.add_argument("--price", type=price_type, default=0.0)
    p.add_argument("--stock", type=stock_type, default=0)
    p.set_defaults(func=cmd_add)

    p = sub.add_parser("update", help="Update an item's price, stock, name or brand")
    p.add_argument("id", type=id_type)
    p.add_argument("--price", type=price_type)
    p.add_argument("--stock", type=stock_type)
    p.add_argument("--name")
    p.add_argument("--brand")
    p.set_defaults(func=cmd_update)

    p = sub.add_parser("delete", help="Delete an item")
    p.add_argument("id", type=id_type)
    p.add_argument("-y", "--yes", action="store_true", help="skip the confirmation prompt")
    p.set_defaults(func=cmd_delete)

    for name, func, text in (("lookup", cmd_lookup, "Find a product on OpenFoodFacts"),
                             ("import", cmd_import, "Find a product on OpenFoodFacts and add it")):
        p = sub.add_parser(name, help=text)
        group = p.add_mutually_exclusive_group(required=True)
        group.add_argument("--barcode")
        group.add_argument("--name")
        if name == "import":
            p.add_argument("--price", type=price_type, default=0.0)
            p.add_argument("--stock", type=stock_type, default=0)
        p.set_defaults(func=func)

    p = sub.add_parser("low-stock", help="List items running low")
    p.add_argument("--threshold", type=stock_type, default=10)
    p.set_defaults(func=cmd_low_stock)

    p = sub.add_parser("enrich", help="Fill in missing item details from OpenFoodFacts")
    p.add_argument("id", type=id_type)
    p.add_argument("--overwrite", action="store_true", help="replace existing values too")
    p.set_defaults(func=cmd_enrich)

    sub.add_parser("menu", help="Interactive menu (default)").set_defaults(func=cmd_menu)
    return parser


def main(argv=None, client=None):
    args = build_parser().parse_args(argv)
    client = client or InventoryClient(args.api_url)
    func = getattr(args, "func", cmd_menu)
    try:
        return func(client, args) or 0
    except (APIError, ValueError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
