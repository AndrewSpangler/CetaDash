import os
import sys
import json
import time
import logging
import logging.config
import ctypes
import asyncio
import platform
import psutil
from functools import wraps
from flask import (
    Flask,
    redirect,
    url_for,
    abort,
    flash,
    request,
    jsonify,
    g,
    render_template,
    render_template_string,
    __version__ as flask_version
)
from flask_login import login_user
from flaskext.markdown import Markdown
from flask_login import LoginManager, login_required, current_user
from pytz import timezone
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import create_engine
from sqlalchemy.exc import OperationalError
from werkzeug.datastructures import ImmutableDict
from .modules.parsing import (
    make_table_page,
    recursive_update
)
from .modules.task_manager import BackgroundTaskManager
from .modules.plugin import load_plugin_config, get_blueprints
from .modules.WTFScript import WTFHtmlFlask

SOURCE_DIR = os.path.dirname(__file__)
BOOTSWATCH_THEMES = ["default"]
# Get list of locally available bootswatch themes
for css in os.scandir(os.path.join(SOURCE_DIR, "static/css/bootswatch")):
    BOOTSWATCH_THEMES.append(
        css.name.lower()
        .replace("bootswatch", "")
        .replace("min.css", "")
        .strip(".")
    )

EDITOR_THEMES = [
    "3024-day","3024-night","abbott","abcdef","ambiance-mobile","ambiance",
    "ayu-dark","ayu-mirage","base16-dark","base16-light","bespin","blackboard",
    "cobalt","colorforth","darcula","dracula","duotone-dark","duotone-light",
    "eclipse","elegant","erlang-dark","gruvbox-dark","hopscotch","icecoder",
    "idea","isotope","juejin","lesser-dark","liquibyte","lucario",
    "material-darker","material-ocean","material-palenight","material","mbo",
    "mdn-like","midnight","monokai","moxer","neat","neo","night","nord",
    "oceanic-next","panda-syntax","paraiso-dark","paraiso-light",
    "pastel-on-dark","railscasts","rubyblue","seti","shadowfox","solarized",
    "ssms","the-matrix","tomorrow-night-bright","tomorrow-night-eighties",
    "ttcn","twilight","vibrant-ink","xq-dark","xq-light","yeti","yonce",
    "zenburn",
]

print(disclaimer := """
Disclaimer: This software is provided "as is" and without warranties of 
any kind, whether express or implied, including, but not limited to, the 
implied warranties of merchantability, fitness for a particular purpose, 
and non-infringement. The use of this software is entirely at your own 
risk, and the owner, developer, or provider of this software shall not be
liable for any direct, indirect, incidental, special, or consequential 
damages arising from the use or inability to use this software or any of 
its functionalities. This software is not intended to be used in any 
life-saving, mission-critical, or other applications where failure of the
software could lead to death, personal injury, or severe physical or 
environmental damage. By using this software, you acknowledge that you 
have read this disclaimer and agree to its terms and conditions.
""".strip())

def get_system_info() -> dict:
    mem = psutil.virtual_memory()
    total_gb = mem.total / (1024 ** 3)
    return {
        "OS": (platform.system(), platform.release(), platform.version()),
        "Memory": f"{int(total_gb)}GB",
        "Python Version": sys.version,
        "Flask Version": flask_version,
        # "Jinja Version": jinja_version
    }

SYSINFO = get_system_info()
print("SYSTEM INFO:\n",  json.dumps(SYSINFO, indent=2))

"""
BACKSTORY ABOUT THIS NEXT BIT OF CODE AND HOW IT AFFECTS THE CONSOLE
For months I was randomly running into an issue where the program would 
hang indefinitely. It would stop responding to any requests but didn't 
otherwise seem to have hung. Turns out the Windows console was getting 
clicked at some point which halted execution. It runs correctly until the 
Windows screen lock activates at which point the webserver would stop 
responding to requests until I logged back in and hit the return key.

I hate NT/Windows sometimes.

Anyways the console will no longer be interactable and using the scroll 
wheel doesn't work but it won't freeze the server if somebody happens to 
accidentally highlight something on the command prompt and then go 
inactive until the screen locks.
"""
if platform.system() == 'Windows':
    if ctypes.windll.kernel32.GetConsoleMode(
        std_in := ctypes.windll.kernel32.GetStdHandle(-10),
        ctypes.byref(mode := ctypes.c_uint())
    ):
        if mode.value & 0x40:
            ctypes.windll.kernel32.SetConsoleMode(std_in, mode.value ^ 0x40)

try:
    ### Prevents premature exits of asyncio loop
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
except AttributeError:
    print("Unable to set asyncio event loop policy")

### Instantiate main app object and load config
app = Flask(__name__)
app.source_dir = SOURCE_DIR
app.config.from_pyfile(os.path.join(os.getcwd(), "config.py"))
print(f"Welcome to {app.config['APPLICATION_NAME']}")
print(f"{app.config['LOADING_SPLASH']}")

### Add WTFScript to jinja templating
wtf = WTFHtmlFlask(app, {
    "url_for" : url_for
})
macros_dir = os.path.join(os.path.dirname(__file__), "modules/WTFScript/macros/html/")
# Load wtf modules
for d in [
    "bootstrap",
    "wtf_fields",
    "simplemde",
    "codemirror",
    "ansi"
]:
    wtf.load_macros_dir(os.path.join(macros_dir, d))
# load custom wtf module for CetaDash
wtf.load_macros_dir(os.path.join(os.path.dirname(__file__), "templates/wtf"))
app.wtf = wtf
app.local_tz = app.wtf.get_tz_from_localization(timezone(app.config["TIMEZONE"]))

### Add markdown rendering in templates
Markdown(app)
Markdown(wtf)

### Load plugins and config
for k in (
    # "SQLALCHEMY_BINDS",
    "NAV_LINKS",
    "ADMIN_NAV_LINKS",
    "DASHBOARD_TABS"
):
    if not k in app.config:
        app.config[k]={}

plugin_config = load_plugin_config(os.path.join(SOURCE_DIR, "blueprints"))

app.recursive_update = recursive_update

recursive_update(app.config, plugin_config)

### Set up logging
logging.basicConfig(level=logging.DEBUG)
logging.config.dictConfig(app.config["LOG_CONFIG"])

### Set up (non-docker) background task scheduler
BackgroundTaskManager(app)

db_host = os.environ["DB_HOST"]
db_port = os.environ["DB_PORT"]
db_user = os.environ["DB_USER"]
db_pass = os.environ["DB_PASSWORD"]
db_name = os.environ["DB_NAME"]

app.config["SQLALCHEMY_BINDS"] = {
    "cetadash_db" : f"mysql+pymysql://{db_user}:{db_pass}@{db_host}:{db_port}/{db_name}"
} 

def with_app():
    """Decorator to provide app context"""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            with app.app_context():
                return func(*args, **kwargs)
        return wrapper
    return decorator

app.with_app = with_app

def wait_for_db(uri, timeout=60, interval=0.5):
    engine = create_engine(uri)
    start_time = time.time()
    
    while True:
        try:
            conn = engine.connect()
            conn.close()
            logging.info("Database is ready.")
            return
        except OperationalError:
            elapsed = time.time() - start_time
            if elapsed > timeout:
                raise TimeoutError(f"Database did not become available in {timeout} seconds.")
            logging.warning(f"Database not ready yet, waiting {interval}s...")
            time.sleep(interval)

wait_for_db(app.config["SQLALCHEMY_BINDS"]["cetadash_db"])

### Set up db engine handler,
# Database engines are initialized in blueprint models
app.db = db = SQLAlchemy(app)
# Namespace for blueprints to register models and objects
app.models = ImmutableDict() 
# Special-case binding to add db models to wtfscript namespace
wtf._bind("models", app.models)
# Init base user / secretkey tables 
# Creates admin and system users
# Needs to be imported after db init
from .models import (
    PERMISSION_ENUM,
    User,
    init_db
)
init_db(app)

### Login
# Define user loader for login
def user_loader(user_id):
    return app.models.core.User.query.get(int(user_id))
app.user_loader = user_loader
# Set up logins
app.login_manager = login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = "login"


### Make databases dir 
os.makedirs("databases", exist_ok=True)

### Make downloads directory
os.makedirs(app.config["DOWNLOADS_DIR"], exist_ok=True)

# Map from group names to permission levels (you can define this however you want)
PERMISSION_MAP = {
    "admins": 10,
    "cetadashusers": 5,
}
DefaultPermission = 0

from flask import abort, request
import logging
import fnmatch

def is_trusted_ip(remote_addr: str, trusted_ips: list) -> bool:
    for ip in trusted_ips:
        if fnmatch.fnmatch(remote_addr, ip):
            return True
    return False

def get_permission_from_groups(groups):
    """Assigns the highest permission level from group memberships"""
    return max([PERMISSION_MAP.get(grp.strip(), 0) for grp in groups], default=DefaultPermission)

def permission_required(required_permission):
    """SSO / Authelia integration"""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            remote_addr = request.remote_addr
            logging.info(remote_addr)
            remote_addr = request.remote_addr
            if not is_trusted_ip(remote_addr, app.config['TRUSTED_PROXY_IPS']):
                logging.warning("Untrusted proxy: %s", remote_addr)
                return abort(403)

            username = request.headers.get("Remote-User", "")
            groups = request.headers.get("Remote-Groups", "")
            group_list = [
                grp.strip()
                for grp in groups.split(",")
                if grp.strip()
            ]
            permission = get_permission_from_groups(group_list)
            if not app.models.core.User.query.filter_by(name=username).first():
                user = app.models.core.User(
                    name=username,
                    permission_integer=permission
                )
                db.session.add(user)
                db.session.commit()
            else:
                user = app.models.core.User.query.filter_by(name=username).first()

                if not permission == user.permission_integer:
                    user.permission_integer = permission
                    db.session.commit()

            if not current_user.is_authenticated:
                login_user(user)
            if permission < required_permission:
                logstring = (
                    f"[403] {username} with permission {permission} "
                    f"tried to access endpoint that requires permission {required_permission}"
                )
                logging.warning(logstring)
                return abort(403)
            # populate global context
            g.user = username
            g.groups = group_list
            g.permission = permission
            return func(*args, **kwargs)
        return wrapper
    return decorator

### Make user filters accessible
app.permission_required = permission_required

def register_blueprint(bp) -> None:
    """
    Custom blueprint registration for clean app architecture
    Inits a blueprint's db if needed then starts blueprint
    """
    
for bp in get_blueprints("src/appsrc/blueprints"): # Load all blueprints from folder
    if hasattr(bp, "init_db"):
        bp.init_db(app)
    app.register_blueprint(bp)

@login_manager.user_loader
def load_user(user_id):
    """Function for the login manager to grab user object from db"""
    return app.user_loader(user_id)

@app.context_processor
def provide_selection() -> dict:
    """
    Context processor which runs before any template is rendered
    Provides access to these objects in all flask templates
    """

    selected_theme = "cosmo"
    if hasattr(current_user, 'selected_theme'):
        selected_theme = current_user.selected_theme or "default"
    
    selected_editor_theme = "isotope"
    if hasattr(current_user, 'selected_theme'):
        selected_editor_theme = current_user.selected_editor_theme or "default"

    return {
        "app": app,
        "show_tz": True, 
        "nav_enabled": True,
        "PERMISSION_MAP": app.models.core.PERMISSION_MAP,
        "PERMISSION_ENUM": app.models.core.PERMISSION_ENUM,
        "themes": BOOTSWATCH_THEMES,
        "editor_themes": EDITOR_THEMES,
        "selected_theme": selected_theme,
        "selected_editor_theme" : selected_editor_theme,
        "models": app.models
    }

@app.route('/apply_theme', methods=['POST'])
def apply_theme():
    print(request.form)
    selected_theme = request.form.get('theme')
    current_user.selected_theme = selected_theme
    db.session.commit()
    return redirect(request.referrer or '/')

@app.route('/apply_editor_theme', methods=['POST'])
def apply_editor_theme():
    selected_editor_theme = request.form.get('editor_theme')
    current_user.selected_editor_theme = selected_editor_theme
    db.session.commit()
    return redirect(request.referrer or '/')

@app.route('/usermeta')
def usermeta():
    """
    DO NOT USE THIS FOR ACCESS CONTROL
    IT SHOULD ONLY BE USED FOR UI COSMETICS 
    """
    if not current_user.is_authenticated:
        logging.warning("Unauthenticated user")
        return abort(403)
    groups = request.headers.get("Remote-Groups", "")
    if len(groups):
        groups = groups.split(",")
    if len(groups) == 1 and groups[0] == "":
        groups = []
    userinfo = {
        "user": request.headers.get("Remote-User", ""),
        "groups": groups
    }
    if userinfo:
        resp = jsonify(userinfo)
        resp.headers.add("Access-Control-Allow-Origin", "*")
        return resp, 200
    else:
        return {}, 500

@app.route('/users')
@app.permission_required(PERMISSION_ENUM.ADMIN)
def users():
    rows = [
        (
            u.name,
            PERMISSION_ENUM._LOOKUP.get(u.permission_integer, u.permission_integer),
        )
        for u in User.query.all()
    ]
    return make_table_page(
        "users",
        title="Users Page",
        columns=["Name", "Role"],
        rows=rows
    )

@app.route('/background_tasks', methods=["GET", "POST"])
@app.permission_required(PERMISSION_ENUM.ADMIN)
def background_tasks():
    url_args = request.args.to_dict()
    toggle = url_args.get("toggle")
    run_now = url_args.get("run_now")
    task_name = url_args.get("task")
    if (toggle or run_now):
        if not task_name in app.task_manager.tasks:
            flash("Task not found", "danger")
            return redirect(url_for("background_tasks"))
        task = app.task_manager.tasks[task_name]

    if toggle:
        task.enabled = not task.enabled
        flash(f"Task {task.name} {'Enabled' if task.enabled else 'Disabled'}", "success")
        return redirect(url_for("background_tasks"))
    elif run_now:
        task.trigger()
        if task.running:
            flash(f"Task {task.name} already running", "danger")
            return redirect(url_for("background_tasks"))
        flash(f"Task {task.name} Triggered successfully", "success")
        return redirect(url_for("background_tasks"))

    rows = [
        (
            k,
            v.interval,
            app.wtf.table_button(
                " "+str(v.enabled),
                ('background_tasks',dict(task=k, toggle=True)),
                btn_type="primary",
                classes="bi bi-toggle-"+("on" if v.enabled else "off"),
            ),
            v.running,
            app.wtf.pretty_date(app.wtf.localize(v.last_run)),
            app.wtf.pretty_date(app.wtf.localize(v.job.next_run_time)),
            app.wtf.table_button(
                " Trigger Task Run",
                ('background_tasks',dict(task=k, run_now=True)),
                btn_type="primary",
                classes="bi bi-play-fill",
            ),
        ) for k,v in app.task_manager.tasks.items()
    ]
    return make_table_page(
        "background_tasks",
        title="Background Tasks",
        columns=["Task", "Frequency (Minutes)", "Enabled", "Running", "Last Run", "Next Run", "Actions"],
        rows=rows,
    )

@app.route("/")
def index():
    """Home page, redirects to dashboard or login in not signed in"""
    return redirect(url_for("dashboard"))

@app.route('/dashboard')
@app.permission_required(PERMISSION_ENUM.USER)
def dashboard():
    return render_template(
        'dashboard.html',
        tabs=app.config["DASHBOARD_TABS"]
    )

@app.route('/about')
def about():
    return render_template('about.html')

@app.errorhandler(404)
def page_not_found(error):
    return render_template('pages/errors/404.html'), 404

@app.errorhandler(500)
def internal_server_error(error):
    return render_template('pages/errors/500.html'), 500

### Start background tasks
app.scheduler.start()