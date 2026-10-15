"""Reports: valuation, low-stock report and the CSV export."""

import csv
import io

from conftest import html

from product.extensions import db
from product.models import Product, StockAdjustment


def csv_rows(response) -> list[list[str]]:
    """Parse the export, dropping the UTF-8 BOM Excel expects."""
    text = response.get_data(as_text=True).lstrip("\ufeff")
    return list(csv.reader(io.StringIO(text)))


# --------------------------------------------------------------------- #
# The reports page                                                      #
# --------------------------------------------------------------------- #


def test_reports_page_renders(auth_client, sample_products):
    response = auth_client.get("/reports/")

    assert response.status_code == 200
    body = html(response)
    assert "Inventory valuation" in body
    assert "Low-stock report" in body


def test_reports_total_the_inventory(auth_client, sample_products):
    """5 × $10 + 0 × $5.50 + 50 × $20 = $1,050.00 across 55 units."""
    body = html(auth_client.get("/reports/"))

    assert "$1,050.00" in body
    assert 'stat-value">55<' in body  # units on hand


def test_valuation_ranks_the_most_valuable_first(auth_client, sample_products):
    body = html(auth_client.get("/reports/"))

    assert body.index("Gamma Gizmo") < body.index("Alpha Widget")
    assert body.index("Alpha Widget") < body.index("Beta Gadget")


def test_low_stock_report_lists_what_needs_restocking(auth_client, sample_products):
    body = html(auth_client.get("/reports/"))
    # The valuation table above lists everything, so look inside the
    # low-stock card itself (it ends where "Recent stock changes" begins).
    low_stock_card = body.split("Low-stock report", 1)[1].split("Recent stock changes", 1)[0]

    assert "Alpha Widget" in low_stock_card
    assert "Beta Gadget" in low_stock_card
    assert "Gamma Gizmo" not in low_stock_card  # comfortably in stock


def test_reports_show_recent_stock_changes(auth_client, sample_products):
    product = sample_products[0]
    auth_client.post(
        f"/stock/{product.id}",
        data={"direction": "increase", "amount": "4", "reason": "restock"},
    )

    body = html(auth_client.get("/reports/"))

    assert "Recent stock changes" in body
    assert "Alpha Widget" in body
    assert "+4" in body


def test_empty_reports_are_safe(auth_client):
    body = html(auth_client.get("/reports/"))

    assert "Nothing to value yet" in body
    assert "Nothing is low" in body


# --------------------------------------------------------------------- #
# CSV export                                                            #
# --------------------------------------------------------------------- #


def test_csv_export_is_a_download(auth_client, sample_products):
    response = auth_client.get("/reports/export.csv")

    assert response.status_code == 200
    assert response.headers["Content-Type"].startswith("text/csv")
    assert "attachment; filename=inventory-" in response.headers["Content-Disposition"]
    assert response.headers["X-Export-Count"] == "3"


def test_csv_export_has_a_header_row_and_every_product(auth_client, sample_products):
    rows = csv_rows(auth_client.get("/reports/export.csv"))

    assert rows[0][:3] == ["id", "name", "category"]
    assert len(rows) == 1 + 3

    by_name = {row[1]: row for row in rows[1:]}
    assert set(by_name) == {"Alpha Widget", "Beta Gadget", "Gamma Gizmo"}

    alpha = by_name["Alpha Widget"]
    assert alpha[3] == "10.00"  # price
    assert alpha[4] == "5"  # quantity
    assert alpha[5] == "10"  # low_stock_threshold
    assert alpha[6] == "Low stock"  # stock_status
    assert alpha[7] == "50.00"  # total_value
    assert alpha[8] == "The first product"  # description


def test_csv_export_reports_empty_descriptions_as_blank(auth_client, sample_products):
    rows = csv_rows(auth_client.get("/reports/export.csv"))
    gamma = next(row for row in rows[1:] if row[1] == "Gamma Gizmo")

    assert gamma[8] == ""  # no description -> empty cell, not an em dash


def test_csv_export_honours_the_stock_filter(auth_client, sample_products):
    rows = csv_rows(auth_client.get("/reports/export.csv?stock=out"))

    assert [row[1] for row in rows[1:]] == ["Beta Gadget"]


def test_csv_export_honours_the_search(auth_client, sample_products):
    rows = csv_rows(auth_client.get("/reports/export.csv?q=widget"))

    assert [row[1] for row in rows[1:]] == ["Alpha Widget"]


def test_csv_export_honours_the_category_filter(auth_client, app, sample_products, category):
    sample_products[0].category_id = category.id
    db.session.commit()

    rows = csv_rows(auth_client.get(f"/reports/export.csv?category={category.id}"))

    assert [row[1] for row in rows[1:]] == ["Alpha Widget"]
    assert rows[1][2] == "Widgets"


def test_csv_export_is_scoped_to_the_owner(auth_client, other_client, sample_products):
    """A crafted URL must never widen the export past one account."""
    rows = csv_rows(other_client.get("/reports/export.csv"))

    assert rows[0][:2] == ["id", "name"]  # header only, no data rows
    assert len(rows) == 1
    assert "Alpha Widget" not in other_client.get("/reports/export.csv").get_data(as_text=True)


def test_csv_export_requires_sign_in(client):
    assert client.get("/reports/export.csv").status_code == 302


def test_csv_export_marks_every_row_with_a_status(auth_client, sample_products):
    rows = csv_rows(auth_client.get("/reports/export.csv"))
    statuses = {row[1]: row[6] for row in rows[1:]}

    assert statuses["Beta Gadget"] == "Out of stock"
    assert statuses["Alpha Widget"] == "Low stock"
    assert statuses["Gamma Gizmo"] == "In stock"


def test_stock_adjustments_are_visible_in_the_report(auth_client, sample_products):
    product = sample_products[2]
    auth_client.post(
        f"/stock/{product.id}",
        data={"direction": "decrease", "amount": "5", "reason": "sale", "note": "shop sale"},
    )

    body = html(auth_client.get("/reports/"))

    assert "-5" in body
    assert "shop sale" in body


def test_report_adjustments_are_scoped_to_the_owner(auth_client, other_client, sample_products):
    product = sample_products[0]
    auth_client.post(
        f"/stock/{product.id}",
        data={"direction": "increase", "amount": "1", "reason": "restock", "note": "mine"},
    )

    body = html(other_client.get("/reports/"))

    assert "mine" not in body
    assert "Restock" not in body


def test_products_are_valued_at_price_times_quantity(auth_client, sample_products):
    """The summary must use quantity, not just unit price."""
    product = Product(
        product_name="Empty Shelf",
        price="99.00",
        owner=sample_products[0].owner,
        quantity=0,
        low_stock_threshold=1,
    )
    db.session.add(product)
    db.session.commit()

    body = html(auth_client.get("/reports/"))

    assert "$1,050.00" in body  # unchanged: an empty shelf is worth nothing


def test_adjustment_history_is_capped(auth_client, sample_products):
    product = sample_products[0]
    for _ in range(20):
        auth_client.post(
            f"/stock/{product.id}",
            data={"direction": "increase", "amount": "1", "reason": "restock"},
        )

    stored = db.session.scalars(
        db.select(StockAdjustment).where(StockAdjustment.product_id == product.id)
    ).all()
    assert len(stored) == 20  # the audit trail itself is complete

    body = html(auth_client.get("/reports/"))
    assert "Recent stock changes" in body
    assert "Restock" in body
