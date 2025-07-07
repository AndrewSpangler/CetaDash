import os

DEBUG = False

APPLICATION_NAME = "CetaDash"
APPLICATION_DESCRIPTION = "Welcome to CetaDash"
APPLICATION_DETAILS = "A Flask-based homelab and Docker workflow automation multitool."

TRUSTED_PROXY_IPS = ["172.18.0.*"]

FOOTER_TEXT = "CetaDash Homelab Multitool"
DEFAULT_DOMAIN = ""
ENVIRONMENT = "test"
TIMEZONE = "US/Pacific"
DOWNLOADS_DIR = "downloads"

LOADING_SPLASH = """**Whale Sounds**"""
# Databases
SQLALCHEMY_POOL_SIZE = 24
SQLALCHEMY_MAX_OVERFLOW = 5
SQLALCHEMY_POOL_RECYCLE = 3600
SQLALCHEMY_DATABASE_URI = "sqlite:///" + os.path.join(os.getcwd(), "databases/users.sqlite")
# Speeds up database
SQLALCHEMY_TRACK_MODIFICATIONS=False
# SQLALCHEMY_ENGINE_OPTIONS = {'pool_pre_ping': True}
# Folder to output logs too
LOGS_FOLDER = os.path.join(os.getcwd(), "logs")
# File pattern to log to, will become app.log.1, app.log.2 etc when log grows too large
LOG_FILE = os.path.join(LOGS_FOLDER, "app.log")
os.makedirs(LOGS_FOLDER, exist_ok=True)
# Logging Configuration
LOG_CONFIG = (
    {
        "version": 1,
        "formatters": {
            "default": {
                "format": "[%(asctime)s] %(levelname)s %(name)s %(threadName)s in %(module)s: %(message)s",
            }
        },
        "handlers": {
            "wsgi": {
                "class": "logging.StreamHandler",
                "stream": "ext://flask.logging.wsgi_errors_stream",
                "formatter": "default",
            },
            "file": {
                "class": "logging.handlers.RotatingFileHandler",
                "level": "INFO",
                "formatter": "default",
                "filename": LOG_FILE,
                "maxBytes": 1024 * 1024, # 1 MB max size
                "backupCount": 10,
                "encoding": "utf8",
            }
        },
        "root": {
            "level": "INFO",
            "handlers": ["wsgi", "file"]
        },
    }
)

ADMIN_NAV_LINKS = {
    "Users":"users",
    "Background Tasks":"background_tasks",
}