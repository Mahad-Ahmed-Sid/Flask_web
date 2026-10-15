"""Flask extensions.

Extensions are instantiated here — but *not* bound to an app.  ``create_app``
calls ``init_app`` on each of them, which is what makes the application
factory pattern (and isolated unit tests) possible.
"""

from flask_migrate import Migrate
from flask_sqlalchemy import SQLAlchemy
from flask_wtf.csrf import CSRFProtect

db = SQLAlchemy()
migrate = Migrate()
csrf = CSRFProtect()
