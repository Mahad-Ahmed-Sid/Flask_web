# Inventory Management System

A multi-user **Flask + SQLAlchemy** inventory app: each account gets a private
stock list — products with prices and descriptions, quantities with a
timestamped adjustment history, categories, dashboards, reports and filtered
CSV exports.

It started as a "follow-along" CRUD tutorial, was rebuilt into a
production-shaped single-user project (application factory, blueprints,
migrations, tests, CI), and was then extended into this multi-user system with
accounts, ownership and stock tracking.

---

![Python](https://img.shields.io/badge/Python-3.10%2B-3776AB?logo=python&logoColor=white)
![Flask](https://img.shields.io/badge/Flask-3.1-000000?logo=flask&logoColor=white)
![SQLAlchemy](https://img.shields.io/badge/SQLAlchemy-2.0-D71F00?logo=sqlalchemy&logoColor=white)
![Tests](https://img.shields.io/badge/tests-174%20passed-brightgreen)
![License](https://img.shields.io/badge/license-MIT-green)

---

## Features

**Accounts and privacy**

- Register / sign in / sign out (Werkzeug password hashing, Flask-Login)
- Fail-closed login guard: every route requires a signed-in user unless it is
  explicitly public, so forgetting a decorator cannot leak data
- Every product, category, stock adjustment and export is scoped to its owner —
  a stranger touching someone else's id gets **404, never 403**
- Profile page + change-password form; logout is POST-only
- Hardened session cookies (`HttpOnly`, `SameSite=Lax`, 12 h lifetime;
  `Secure` in production), CSRF on every form
- The **first registered account adopts the demo admin's migrated products**
  (and their categories), so an existing install keeps its data

**Inventory**

- Full CRUD with server-side validation, inline errors and Post/Redirect/Get
- **Search** (name + description, SQL wildcards matched literally), **sort**
  through an allow-listed column map, **pagination** — all composable
- Filter by **category** and by **stock status** (`in` / `low` / `out`), and
  combine filters with search, sort and page
- CSV export of the current list that honours the active filters

**Stock management**

- Per-product quantity and a configurable low-stock threshold
- Increase / decrease with a reason (restock, sale, damaged, correction, other)
  and an optional note — every change is recorded with a timestamp
- Editing a product's quantity records a `correction` adjustment
- Negative stock is impossible: validated server-side against the current row
- Low-stock badge in the sidebar and on every page it applies to

**Dashboard**

- Totals at a glance: products, inventory value, units on hand, low/out counts
- Recently added products, "Restock soon" table linking to each stock page
- Pure-CSS bar chart of units per category (no charting dependency)

**Reports**

- Inventory valuation, low-stock report and recent stock changes
- `GET /reports/export.csv` — UTF-8 BOM CSV (opens straight in Excel) with an
  `X-Export-Count` header, filtered by `q`, `category`, `stock` and `sort`
- Everything on the page and in the file belongs to the signed-in account

**Quality**

- **174 `pytest` tests** against an isolated in-memory database
- `ruff check` **and** `ruff format` clean; GitHub Actions CI on every push
- Alembic migrations that are **reversible** — the upgrade that added accounts
  preserved the three pre-existing products with their original ids, names,
  prices and dates (verified by upgrading, downgrading and upgrading again)
- Styled 404 / 500 / expired-CSRF pages, responsive sidebar layout, empty
  states and confirmation dialogs throughout

## Tech stack

| Layer      | Choice                                          |
|------------|-------------------------------------------------|
| Framework  | Flask 3.1                                       |
| Database   | SQLAlchemy 2.0 via Flask-SQLAlchemy, SQLite      |
| Migrations | Flask-Migrate (Alembic)                         |
| Auth       | Flask-Login + Werkzeug password hashing         |
| Forms      | Flask-WTF + WTForms (validation + CSRF)         |
| Front end  | Bootstrap 5.3 (CDN) + small custom CSS/JS       |
| Tooling    | pytest, ruff, GitHub Actions                    |

## Quick start

Requires **Python 3.10+** (developed on 3.14).

```bash
# 1. Clone and enter the project
git clone https://github.com/Mahad-Ahmed-Sid/Flask_web.git
cd Flask_web

# 2. Create and activate a virtual environment
python -m venv env

# Windows
env\Scripts\activate
# macOS / Linux
source env/bin/activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Create the database schema (and seed the demo admin)
flask --app app db upgrade

# 5. Run it
flask --app app run --port 9000
# ...or the classic way
python app.py
```

Open <http://127.0.0.1:9000/>.

**Getting data in**

- On a fresh clone, just **register the first account** — it becomes the owner
  of everything the migration seeded.
- On the developer database (which already holds the three original products),
  the very first account you register adopts those products and their
  categories automatically.
- To sign in as the seeded admin instead:

  ```bash
  flask --app app set-password admin@inventory.local   # prompts for a password
  ```

> The local database lives in `instance/products.db` and is git-ignored, so a
> fresh clone always starts clean from the migrations.

## Configuration

Copy `.env.example` to `.env` and adjust it — `.env` is ignored by git.

| Variable             | Default                  | Purpose                                        |
|----------------------|--------------------------|------------------------------------------------|
| `SECRET_KEY`         | dev fallback             | Session/CSRF signing — **set this in production** |
| `FLASK_CONFIG`       | `development`            | `development`, `testing` or `production`       |
| `DATABASE_URL`       | local SQLite file        | Any SQLAlchemy URI, e.g. PostgreSQL             |
| `FLASK_RUN_HOST`     | `127.0.0.1`              | Host used by `flask run` / `python app.py`     |
| `FLASK_RUN_PORT`     | `9000`                   | Port used by `flask run` / `python app.py`     |
| `ADMIN_EMAIL`        | `admin@inventory.local`  | Email of the seeded demo admin                 |
| `ADMIN_DISPLAY_NAME` | `Inventory Admin`        | Display name of the seeded admin               |
| `ADMIN_DEV_PASSWORD` | `ChangeMe-Admin1!`       | Initial password for `flask seed-admin` — **change it** |
| `SESSION_COOKIE_SECURE` | `1`                   | Set to `0` only if you deliberately run production over plain HTTP |

## Routes

| Method           | Path                           | Purpose                              |
|------------------|--------------------------------|--------------------------------------|
| `GET`            | `/auth/register`               | Create an account (adopts demo data) |
| `GET`            | `/auth/login`                  | Sign in                              |
| `POST`           | `/auth/logout`                 | Sign out (POST-only)                 |
| `GET`, `POST`    | `/auth/profile`                | Profile / display name               |
| `GET`, `POST`    | `/auth/profile/password`       | Change password                      |
| `GET`            | `/dashboard/`                  | Totals, restock list, CSS chart      |
| `GET`, `POST`    | `/`                            | Products: list, search, sort, filter, create |
| `GET`, `POST`    | `/edit/<id>`                   | Edit a product (quantity = correction) |
| `POST`           | `/delete/<id>`                 | Delete a product (confirmation)      |
| `GET`, `POST`    | `/stock/<id>`                  | Adjust stock + audit history         |
| `GET`, `POST`    | `/categories/`                 | Manage categories                    |
| `POST`           | `/categories/<id>/delete`      | Delete a category (keeps products)   |
| `GET`            | `/reports/`                    | Valuation, low-stock, recent changes |
| `GET`            | `/reports/export.csv`          | Filtered CSV export                  |
| `GET`            | anything else                  | Styled 404 / 405 page                |

## Project structure

```
Flask2026/
├── app.py                  # thin entry point → create_app()
├── config.py               # development / testing / production config
├── requirements.txt
├── pyproject.toml          # ruff + pytest settings
├── .env.example
├── .github/workflows/ci.yml
│
├── product/                # application package
│   ├── __init__.py         # create_app(), login guard, filters, CLI, errors
│   ├── extensions.py       # db, migrate, csrf, login_manager (unbound)
│   ├── models.py           # User, Product, Category, StockAdjustment
│   ├── forms.py            # registration, login, profile, product, stock, …
│   ├── queries.py          # ownership-scoped lookups, filters, aggregates
│   ├── auth.py             # accounts, password change, legacy adoption
│   ├── seed.py             # demo admin seeding helpers
│   ├── dashboard.py        # at-a-glance stats
│   ├── categories.py       # category CRUD
│   ├── reports.py          # reports + CSV export
│   └── routes.py           # product CRUD, search/sort/pagination, stock
│
├── templates/
│   ├── base.html           # responsive sidebar shell, flash, logout form
│   ├── index.html          # filters + product table
│   ├── edit.html           # edit form
│   ├── stock.html          # stock adjustment form + audit history
│   ├── dashboard.html      # stat cards, bar chart, restock list
│   ├── categories.html     # category manager
│   ├── reports.html        # valuation + low-stock + recent changes
│   ├── auth/               # login, register, profile, change password
│   ├── _macros.html        # sort headers, pagination, badges, field errors
│   └── errors/             # 404, 500, expired-form
│
├── static/                 # style.css, main.js, favicon.svg
├── migrations/             # Alembic revisions (incl. the accounts upgrade)
├── docs/                   # screenshots (being retaken for the new UI)
└── tests/                  # 174 tests: routes, auth, stock, categories,
                            # reports, dashboard, security, models
```

## Development

```bash
pytest                      # run the test suite
ruff check .                # lint
ruff format .               # format

# After changing a model:
flask --app app db migrate -m "Describe the change"
flask --app app db upgrade

# Maintenance
flask --app app set-password someone@example.com   # reset a password
flask --app app seed-admin                        # ensure the demo admin exists
```

## Design notes

Things worth knowing if you are reading the code:

- **One place reads products.** Every query goes through
  `queries.build_product_query` / `get_owned_or_404`, so the owner constraint
  cannot be forgotten in a view.
- **404, not 403.** A stranger probing `/edit/7` must not learn that id 7
  exists, so cross-owner lookups answer *not found*.
- **The login guard fails closed.** It checks the blueprint allow-list rather
  than a list of protected routes; new blueprints are private by default.
- **`delete` is a `POST` with a CSRF token.** A plain `/delete/1` link would be
  followed by link-prefetchers, scrapers and malicious sites alike.
- **Sorting goes through an allow-list.** `?sort=` is looked up in a dict of
  real columns, so `price; DROP TABLE` can never reach SQL; search terms are
  escaped before being wrapped in `LIKE %…%`.
- **Post/Redirect/Get** on create, edit and adjustments stops a refresh from
  re-submitting the form; invalid submissions re-render with inline errors.
- **Stock can never go negative** — the adjustment re-reads the row inside the
  same transaction before applying the delta.
- **Flask-Login's user cache is reset per request** (`g.pop("_login_user")` in
  the first `before_request`). Flask-Login 0.6.3 caches the user on `flask.g`,
  which survives an app context that is reused across requests (test clients,
  scripts) — without the reset, one account's session could be served to the
  next request.
- **Extensions are created unbound** (`db = SQLAlchemy()`) and initialised in
  `create_app`, which is what lets tests spin up isolated apps with an
  in-memory database.

## Migrations and existing data

The project's history includes a real data-preserving upgrade
(`6ed874c53b58_add_users_categories_and_stock_tracking`):

- adds `user`, `category` and `stock_adjustment` tables and a `product.owner_id`
  foreign key — without ever dropping or recreating `product`;
- seeds the demo admin and the `Beverages` / `Snacks` categories, then assigns
  the existing rows to them;
- is reversible: `flask db downgrade fa4522522c2a` restores the original
  five-column table byte-for-byte (verified), and upgrading again re-applies it.

Product ids, names, prices, descriptions and creation dates survive both trips.

## Roadmap

- [ ] JSON API (`/api/products`) with pagination metadata
- [ ] Image uploads instead of the description-only view
- [ ] Dockerfile + deploy workflow
- [ ] Retake the screenshots in `docs/` for the new interface

## License

MIT — see [LICENSE](LICENSE).
