import os
import datetime
import queue
import threading
from functools import wraps
from ....modules.parsing import (
    make_table_button,
    make_table_icon_button,
    make_table_page
)
from flask import (
    Blueprint,
    render_template,
    redirect,
    url_for,
    flash,
    request,
    Response,
    stream_with_context,
    jsonify
)
from flask_login import current_user
from ..models import (
    app,
    db,
    Workflow,
    WorkflowTaskAssociation,
    ScheduleTrigger,
    ScheduleTriggerEditLog,
    ScheduleTriggerRunLog,
    ACTION_ENUM,
    STATUS_ENUM
)
from ..forms import ScheduleTriggerForm
from .trigger_handling import handle_trigger
from .scheduler import WorkflowScheduler


blueprint = Blueprint(
    'scheduler',
    __name__,
    static_folder=os.path.join(os.path.dirname(os.path.dirname(__file__)),"static"),
    template_folder=os.path.join(os.path.dirname(os.path.dirname(__file__)), "templates"),
)


@blueprint.route('/')
@app.permission_required(app.models.core.PERMISSION_ENUM.ADMIN)
def index():
    triggers = ScheduleTrigger.query.all()
    new_button = make_table_button(
        "New Scheduled Trigger",
        url_args=[["docker.scheduler.create"], {}],
        classes=["bi", "bi-plus"],
        btn_type="success"
    )
    page = make_table_page(
        "schedule_triggers",
        title = "Scheduled Triggers",
        columns = [
            "[ID] Name",
            "Created",
            "Creator",
            "Updated",
            "Editor",
        ],
        rows = [
            (
                app.wtf.span(
                    f"""<a href="{url_for('docker.scheduler.view', trigger_id=trigger.id)}">[{trigger.id}] {trigger.name}</a>"""
                    + app.wtf.span(
                        make_table_icon_button(
                            ((f'docker.scheduler.edit',),{'trigger_id':trigger.id}),
                            classes=[f"bi-pencil"],
                            tooltip='Edit Trigger',
                            float="right",
                            method="GET"
                        ) + make_table_icon_button(
                            ((f'docker.scheduler.delete',),{'trigger_id':trigger.id}),
                            classes=[f"bi-trash"],
                            tooltip='Delete Trigger',
                            float="right"
                        ),
                        style="display: inline-block;",
                        classes="float-right"
                    ),
                    classes="d-flex justify-content-between"
                ),
                trigger.created_at_pretty,
                trigger.creator.name,
                trigger.edited_at_pretty,
                trigger.last_editor.name,
            )
            for trigger in triggers 
        ],
        header_elements=[new_button] if current_user.is_admin else [],
    )
    return page


@blueprint.route('/create', methods=['GET', 'POST'])
@app.permission_required(app.models.core.PERMISSION_ENUM.ADMIN)
def create():
    form = ScheduleTriggerForm()
    form.workflow.query_factory = lambda: Workflow.query.order_by(Workflow.name).all()

    form.headers.data = """username: system
groups: admins"""

    if form.validate_on_submit():
        workflow = form.workflow.data

        if not workflow:
            flash("You must select a workflow.", "danger")
            return render_template("scheduler/new.html", form=form, object_type="Workflow Task")

        cron_fields = dict(
            day_of_week=form.day_of_week.data,
            hour=form.hour.data,
            minute=form.minute.data
        ) if form.job_type.data == "cron" else dict(
            day_of_week=None,
            hour=None,
            minute=None
        )

        interval_fields = dict(
            seconds=form.seconds.data,
            minutes=form.minutes.data,
            hours=form.hours.data
        ) if form.job_type.data == "interval" else dict(
            seconds=None,
            minutes=None,
            hours=None
        )

        trigger = ScheduleTrigger(
            name=form.name.data,
            description=form.description.data,
            details=form.details.data,
            headers=form.headers.data,
            environment=form.environment.data,
            job_type=form.job_type.data,
            workflow_id=workflow.id,
            creator_id=current_user.id,
            last_editor_id=current_user.id,
            enabled=form.enabled.data,
            **cron_fields,
            **interval_fields
        )

        db.session.add(trigger)
        db.session.commit()

        tlog = trigger.log_edit(current_user.id, ACTION_ENUM.CREATE)
        db.session.commit()

        flash("Scheduled Trigger created successfully!", "success")
        return redirect(url_for("docker.scheduler.view", trigger_id=trigger.id))

    return render_template("scheduler/new.html", object_type="Workflow Task", form=form)


@blueprint.route('/reload', methods=['GET'])
@app.permission_required(app.models.core.PERMISSION_ENUM.ADMIN)
def reload_scheduler():
    result = app.docker_scheduler.reload()
    return jsonify(result)


@blueprint.route('/status', methods=['GET'])
@app.permission_required(app.models.core.PERMISSION_ENUM.ADMIN)
def stat_scheduler():
    result = app.docker_scheduler.get_reload_status()
    return jsonify(result)


@blueprint.route('/scheduler/<trigger_id>/edit', methods=['GET', 'POST'])
@app.permission_required(app.models.core.PERMISSION_ENUM.ADMIN)
def edit(trigger_id):
    trigger = ScheduleTrigger.query.get_or_404(trigger_id)
    form = ScheduleTriggerForm()
    form.workflow.query_factory = lambda: Workflow.query.order_by(Workflow.name).all()

    before = {
        "name" : trigger.name,
        "description" : trigger.description,
        "details" : trigger.details,
        "workflow_id" : trigger.workflow_id,
        "last_editor_id" : trigger.last_editor_id,
        "edited_at" : trigger.edited_at,
        "headers" : trigger.headers,
        "environment" : trigger.environment,
        "job_type" : trigger.job_type,
        "day_of_week" : trigger.day_of_week,
        "hour" : trigger.hour,
        "minute" : trigger.minute,
        "hours" : trigger.hours,
        "minutes" : trigger.minutes,
        "seconds" : trigger.seconds,
        "enabled" : trigger.enabled,
    }

    if request.method == 'POST' and form.validate_on_submit():
        workflow = form.workflow.data
        after = {
            "name" : form.name.data,
            "description" : form.description.data,
            "details" : form.details.data,
            "workflow_id" : form.workflow.data.id,
            "last_editor_id" : current_user.id,
            "edited_at" : datetime.datetime.utcnow(),
            "headers" : form.headers.data,
            "environment" : form.environment.data,
            "job_type" : form.job_type.data,
            "day_of_week" : form.day_of_week.data,
            "hour" : form.hour.data,
            "minute" : form.minute.data,
            "hours" : form.hours.data,
            "minutes" : form.minutes.data,
            "seconds" : form.seconds.data,
            "enabled" : form.enabled.data,
        }

        for k, v in after.items():
            setattr(trigger, k, v)
        changes = app.models.core.make_changelog(before, after)
        trigger.log_edit(
            current_user.id,
            ACTION_ENUM.MODIFY,
            message = changes
        )
        db.session.commit()
        flash('Scheduled Trigger updated successfully!', 'success')
        return redirect(url_for('docker.scheduler.view', trigger_id=trigger_id))

    before.pop("last_editor_id")
    before.pop("edited_at")

    form.process(data=before)
    return render_template('scheduler/edit.html', trigger=trigger, form=form)


@blueprint.route('/scheduler/<trigger_id>/view', methods=['GET','POST'])
@app.permission_required(app.models.core.PERMISSION_ENUM.ADMIN)
def view(trigger_id:int) -> str:
    trigger = ScheduleTrigger.query.get_or_404(trigger_id)    
    return render_template('scheduler/view.html', trigger=trigger)


@blueprint.route('/scheduler/<trigger_id>/edits/<log_id>', methods=['GET','POST'])
@app.permission_required(app.models.core.PERMISSION_ENUM.ADMIN)
def edits(trigger_id, log_id):
    trigger = ScheduleTrigger.query.get_or_404(trigger_id) 
    edit_log = ScheduleTriggerEditLog.query.get_or_404(log_id)

    if not trigger.id == edit_log.schedule_trigger.id:
        raise ValueError("Scheduled trigger and edit log do not match")

    return render_template(
        'scheduler/changelog.html',
        edit_log=edit_log
    )


@blueprint.route('/scheduler/<trigger_id>/logs/<log_id>', methods=['GET','POST'])
@app.permission_required(app.models.core.PERMISSION_ENUM.ADMIN)
def logs(trigger_id, log_id):
    trigger = ScheduleTrigger.query.get_or_404(trigger_id) 
    run_log = ScheduleTriggerRunLog.query.get_or_404(log_id)
    if not trigger.id == run_log.schedule_trigger.id:
        raise ValueError("Trigger and edit log do not match")
    return render_template('pages/log_stack_page.html', log=run_log)


@blueprint.route('/scheduler/<trigger_id>/delete', methods=['POST'])
@app.permission_required(app.models.core.PERMISSION_ENUM.ADMIN)
def delete(trigger_id:int) -> str:
    trigger = ScheduleTrigger.query.get_or_404(trigger_id)
    db.session.delete(trigger)
    db.session.commit()
    flash('Trigger deleted successfully!', 'success')
    return redirect(url_for('docker.scheduler.index'))









# @blueprint.route('/trigger/<trigger_id>/actionframe', methods=['GET', 'POST'])
# @app.permission_required(app.models.core.PERMISSION_ENUM.ADMIN)
# def actionframe(trigger_id):
#     return render_template("pages/stream_frame.html", stream_url=url_for("docker.triggers.activate", trigger_id=trigger_id))