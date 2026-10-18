"""Input validation for inventory payloads."""

TEXT_FIELDS = ("brands", "ingredients_text", "categories", "quantity", "image_url")
ALLOWED_FIELDS = {"product_name", "barcode", "price", "stock", "nutriscore_grade", *TEXT_FIELDS}


def _is_number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def validate_item(data, partial=False):
    """Validate an item payload.

    ``partial=True`` is used for PATCH requests, where fields are optional.
    Returns ``(clean_data, errors)``; the payload is valid when ``errors`` is empty.
    """
    if not isinstance(data, dict):
        return {}, ["Request body must be a JSON object."]

    errors, clean = [], {}

    unknown = set(data) - ALLOWED_FIELDS
    if unknown:
        errors.append(f"Unknown or read-only field(s): {', '.join(sorted(unknown))}.")

    if "product_name" in data:
        name = data["product_name"]
        if isinstance(name, str) and name.strip():
            clean["product_name"] = name.strip()
        else:
            errors.append("product_name must be a non-empty string.")
    elif not partial:
        errors.append("product_name is required.")

    if "barcode" in data:
        barcode = str(data["barcode"]).strip() if data["barcode"] is not None else ""
        if barcode.isdigit() and 8 <= len(barcode) <= 14:
            clean["barcode"] = barcode
        else:
            errors.append("barcode must be 8-14 digits.")

    if "price" in data:
        if _is_number(data["price"]) and data["price"] >= 0:
            clean["price"] = round(float(data["price"]), 2)
        else:
            errors.append("price must be a number greater than or equal to 0.")

    if "stock" in data:
        stock = data["stock"]
        if isinstance(stock, int) and not isinstance(stock, bool) and stock >= 0:
            clean["stock"] = stock
        else:
            errors.append("stock must be a whole number greater than or equal to 0.")

    if "nutriscore_grade" in data:
        grade = data["nutriscore_grade"]
        if isinstance(grade, str) and grade.lower() in {"a", "b", "c", "d", "e"}:
            clean["nutriscore_grade"] = grade.lower()
        else:
            errors.append("nutriscore_grade must be one of a, b, c, d, e.")

    for field in TEXT_FIELDS:
        if field in data:
            if isinstance(data[field], str):
                clean[field] = data[field].strip()
            else:
                errors.append(f"{field} must be a string.")

    if partial and not data and not errors:
        errors.append("Provide at least one field to update.")

    return clean, errors
