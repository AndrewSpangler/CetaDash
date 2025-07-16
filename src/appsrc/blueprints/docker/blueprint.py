import os
from flask import Blueprint, redirect, url_for
from flask_login import current_user
from .models import app, db, init_db
from .blueprints import (
    tasks_blueprint,
    workflows_blueprint,
    triggers_blueprint,
    containers_blueprint,
    scheduler_blueprint,
    scripts_blueprint,
    WorkflowScheduler
)

blueprint = Blueprint(
    'docker',
    __name__,
    url_prefix="/docker",
    static_folder=os.path.join(os.path.dirname(__file__),"static"),
    template_folder=os.path.join(os.path.dirname(__file__), "templates"),
)

blueprint.init_db = init_db
blueprint.register_blueprint(containers_blueprint,  url_prefix='/containers')
blueprint.register_blueprint(scripts_blueprint,     url_prefix='/workflow/scripts')
blueprint.register_blueprint(tasks_blueprint,       url_prefix='/workflow/tasks')
blueprint.register_blueprint(workflows_blueprint,   url_prefix='/workflow/workflows')
blueprint.register_blueprint(triggers_blueprint,    url_prefix='/workflow/triggers')
blueprint.register_blueprint(scheduler_blueprint,   url_prefix='/workflow/scheduler')

scheduler = WorkflowScheduler(app)
app.docker_scheduler = scheduler

@blueprint.route('/')
@app.permission_required(app.models.core.PERMISSION_ENUM.ADMIN)
def index():
    return redirect(url_for("docker.containers.index"))