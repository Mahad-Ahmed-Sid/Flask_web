"""Development entry point.

    python app.py
    FLASK_APP=app.py flask run

The application itself is assembled by :func:`product.create_app`.
"""

import os

from product import create_app

app = create_app()

if __name__ == "__main__":
    app.run(
        host=os.environ.get("FLASK_RUN_HOST", "127.0.0.1"),
        port=int(os.environ.get("FLASK_RUN_PORT", 9000)),
        debug=app.config.get("DEBUG", False),
    )
