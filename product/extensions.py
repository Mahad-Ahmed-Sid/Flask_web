"""Flask extensions.

Extensions are instantiated here — but *not* bound to an app.  ``create_app``
calls ``init_app`` on each of them, which is what makes the application
factory pattern (and isolated unit tests) possible.
"""

from flask_login import LoginManager
from flask_migrate import Migrate
from flask_sqlalchemy import SQLAlchemy
from flask_wtf.csrf import CSRFProtect

db = SQLAlchemy()
migrate = Migrate()
csrf = CSRFProtect()
login_manager = LoginManager()

# Sent to anonymous visitors who try to open a protected page.
login_manager.login_view = "auth.login"
login_manager.login_message = "Please sign in to continue."
login_manager.login_message_category = "warning"
