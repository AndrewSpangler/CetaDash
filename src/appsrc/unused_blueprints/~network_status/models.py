import datetime
import logging
from werkzeug.datastructures import ImmutableDict
from ...main import db
from ...modules.parsing import localize, pretty_date
from ...modules.settings_table import BaseSettingsTable

class Range(db.Model):
    """Object to track a range of ips for the network scanner"""
    __tablename__ = "Range"
    __bind_key__ = "network_db"
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    address = db.Column(db.Text)
    name = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.datetime.utcnow)
    @property
    def created_at_local(self):
        return localize(self.created_at)
    @property
    def created_at_pretty(self):
        return pretty_date(self.created_at_local)

class NetSetting(BaseSettingsTable):
    __tablename__ = "NetSetting"
    __bind_key__ = "network_db"
    def __init__(self): pass

DEFAULT_SETTINGS = {
    "SCAN_INTERVAL": (15, "int"),
    "ENABLE_SCAN": (True, "bool")
}

def init_db(app):
    """Initialize network database"""
    logging.info("Initializing Network db")
    with app.app_context():
        db.create_all(bind_key=["network_db"])
        db.session.commit()

        # Init default settings if needed
        if not len(NetSetting.query.all()):
            settings = [
                dict(
                    key=k,
                    value=v[0],
                    data_type=v[1]
                )
                for k,v in DEFAULT_SETTINGS.items()
            ]
            db.session.bulk_insert_mappings(NetSetting, settings)
            db.session.commit()

        app.models.network = ImmutableDict()
        for obj in (Range, NetSetting):
            setattr(app.models.network, obj.__name__, obj)

        app.task_manager.create_task(
            name = "NET_SCAN",
            task = app.network_scanner.scanner.scan,
            interval = NetSetting.get_setting("SCAN_INTERVAL"),
            enabled = NetSetting.get_setting("ENABLE_SCAN")
        )