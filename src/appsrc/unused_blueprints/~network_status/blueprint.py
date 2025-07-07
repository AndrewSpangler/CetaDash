import os
from flask import Flask, Blueprint, url_for, render_template, redirect
import sqlalchemy.exc
from ...main import app, db
from ...modules.network import Scanner
from ...modules.parsing import (
    make_settings_button,
    make_add_button_circle,
    make_table_page
)
from .models import Range, NetSetting, init_db
from .forms import NewRangeForm, ScanFrequencyForm

blueprint = Blueprint(
    'network',
    __name__,
    url_prefix="/network",
    static_folder=os.path.join(os.path.dirname(__file__),"static"),
    template_folder=os.path.join(os.path.dirname(__file__), "templates"),
)
blueprint.init_db = init_db

class NetworkScanner:
    def __init__(self, app:Flask):
        if hasattr(app, "network_scanner"):
            raise AttributeError("Network Scanner already initialized")
        self.app = app
        app.network_scanner = self
        self.remake_scanner()
    
    def remake_scanner(self):
        with app.app_context():
            try:
                ranges = Range.query.all()
            except sqlalchemy.exc.OperationalError:
                ranges = []
        self.scanner = Scanner([r.address for r in ranges])

NetworkScanner(app)

@blueprint.route("/status", methods=["GET"])
@app.permission_required(app.models.core.PERMISSION_ENUM.ADMIN)
def status():
    """Network status page"""
    columns = ["Hostname", "Aliases", "Addresses", "FQDN"]
    rows = [v for k, v in app.network_scanner.scanner.data.items()]
    settings_button = make_settings_button('network.settings')
    return make_table_page(
        "network_scan",
        columns=columns,
        rows=rows,
        title="Network Scan Results",
        header_elements=[settings_button]
    )

def update_scan_background_task(trigger=True):
    if not (task := app.task_manager.tasks.get("NET_SCAN")):
        task = app.task_manager.create_task(
            name = "NET_SCAN",
            task = app.network_scanner.scanner.scan,
            interval = NetSetting.get_setting("SCAN_INTERVAL"),
            enabled = NetSetting.get_setting("ENABLE_SCAN"),
            delay_startup = True
        )
    else:
        task.interval = NetSetting.get_setting("SCAN_INTERVAL")
        task.enabled = NetSetting.get_setting("ENABLE_SCAN")
        task.reschedule()
    if trigger:
        task.trigger()

@blueprint.route("/settings", methods=["GET", "POST"])
@app.permission_required(app.models.core.PERMISSION_ENUM.ADMIN)
def settings():
    """Network settings page"""
    if (frequency_form := ScanFrequencyForm()).validate_on_submit():
        NetSetting.set_setting("SCAN_INTERVAL", frequency_form.update_frequency.data)
        NetSetting.set_setting("ENABLE_SCAN", frequency_form.enable_scan.data)
        update_scan_background_task(trigger=True)
        return redirect(url_for("network.settings"))

    columns = ["ID", "Name", "Address Range", "Created", "Actions"]
    ranges = Range.query.all()
    rows = [(r.id, r.name, r.address, r.created_at_pretty, "") for r in ranges]
    add_button = make_add_button_circle('network.new')

    frequency_form.update_frequency.data = NetSetting.get_setting("SCAN_INTERVAL")
    frequency_form.enable_scan.data = NetSetting.get_setting("ENABLE_SCAN")
    frequency_card = render_template("frequency_card.html", form=frequency_form)

    return make_table_page(
        "network_ranges",
        columns=columns,
        rows=rows,
        title="Network Scanner Settings",
        header_elements=[add_button],
        body_elements=[frequency_card]
    )

@blueprint.route("/new", methods=["GET", "POST"])
@app.permission_required(app.models.core.PERMISSION_ENUM.ADMIN)
def new():
    """Show new range form on GET or make new range in db on POST"""
    if (form := NewRangeForm()).validate_on_submit():
        r = Range(name=form.name.data, address=form.address.data)
        db.session.add(r)
        db.session.commit()
        app.network_scanner.remake_scanner()
        update_scan_background_task(trigger=True)
        return redirect(url_for('network.settings'))
    return render_template("new_range.html", form=form)
