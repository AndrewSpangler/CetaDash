import os
import datetime
import queue
import threading
from functools import wraps
from ....modules.parsing import make_table_page
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
    new_button = app.wtf.cd.table_button(
        "New Scheduled Trigger",
        url_args=["docker.scheduler.create",{}],
        classes="bi bi-plus",
        btn_type="success"
    )
    page = make_table_page(
        "schedule_triggers",
        title = "Scheduled Triggers",
        columns = [
            "[ID] Name",
            # "Status",
            "Actions",
            # "Created",
            # "Creator",
            "Config",
            "Updated",
            # "Editor",
        ],
        rows = [ 
            (
                app.wtf.a(
                    f"[{trigger.id}] {trigger.name}",
                    href=url_for('docker.scheduler.view', trigger_id=trigger.id)
                ),
                # app.wtf.bs.badge(
                #     ["Disabled","Enabled"][trigger.enabled],
                #     classes="badge-pill "+["bg-danger", "bg-success"][trigger.enabled]
                # ),
                app.wtf.cd.table_button_row(
                    app.wtf.cd.table_icon_button(
                        ('docker.scheduler.toggle_trigger',{'trigger_id':trigger.id}),
                        classes=["bi-toggle-off text-danger", "bi-toggle-on text-success"][trigger.enabled],
                        tooltip=f'Toggle Schedule {"Off" if trigger.enabled else "On"} \
                            [Currently {"Enabled" if trigger.enabled else "Disabled"}]',
                        method="POST"
                    ) + app.wtf.cd.table_icon_button(
                        ('docker.scheduler.edit',{'trigger_id':trigger.id}),
                        classes="bi-pencil",
                        tooltip='Edit Trigger',
                        method="GET"
                    ) + app.wtf.cd.table_icon_button(
                        ('docker.scheduler.delete',{'trigger_id':trigger.id}),
                        classes="bi-trash",
                        tooltip='Delete Trigger',
                    )
                ),
                # trigger.created_at_pretty,
                # trigger.creator.name,
                trigger.schedule_string,
                trigger.edited_at_pretty,
                
                # trigger.last_editor.name,
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

        if trigger.enabled:
            try:
                app.docker_scheduler.add_schedule_trigger(trigger)
                flash("Scheduled Trigger created and added to scheduler successfully!", "success")
            except Exception as e:
                flash(f"Scheduled Trigger created but failed to add to scheduler: {str(e)}", "warning")
        else:
            flash("Scheduled Trigger created successfully (disabled)!", "success")

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
    """Get detailed scheduler status"""
    try:
        result = app.docker_scheduler.get_reload_status()
        
        # Add trigger details
        triggers = ScheduleTrigger.query.all()
        trigger_details = []
        
        for trigger in triggers:
            job_info = app.docker_scheduler.get_job_info(trigger.id)
            trigger_details.append({
                'id': trigger.id,
                'name': trigger.name,
                'enabled': trigger.enabled,
                'job_type': trigger.job_type,
                'workflow_name': trigger.workflow.name,
                'scheduled': job_info is not None,
                'next_run': job_info.get('next_run_time') if job_info else None,
                'schedule_string': trigger.schedule_string
            })
        
        result['trigger_details'] = trigger_details
        return jsonify(result)

    except Exception as e:
        return jsonify({
            'error': str(e),
            'scheduler_running': False
        }), 500


@blueprint.route('/scheduler/<trigger_id>/edit', methods=['GET', 'POST'])
@app.permission_required(app.models.core.PERMISSION_ENUM.ADMIN)
def edit(trigger_id):
    trigger = ScheduleTrigger.query.get_or_404(trigger_id)
    form = ScheduleTriggerForm()
    form.workflow.query_factory = lambda: Workflow.query.order_by(Workflow.name).all()

    before = {
        "name": trigger.name,
        "description": trigger.description,
        "details": trigger.details,
        "workflow_id": trigger.workflow_id,
        "last_editor_id": trigger.last_editor_id,
        "edited_at": trigger.edited_at,
        "headers": trigger.headers,
        "environment": trigger.environment,
        "job_type": trigger.job_type,
        "day_of_week": trigger.day_of_week,
        "hour": trigger.hour,
        "minute": trigger.minute,
        "hours": trigger.hours,
        "minutes": trigger.minutes,
        "seconds": trigger.seconds,
        "enabled": trigger.enabled,
    }

    if request.method == 'POST' and form.validate_on_submit():
        workflow = form.workflow.data
        after = {
            "name": form.name.data,
            "description": form.description.data,
            "details": form.details.data,
            "workflow_id": workflow.id,
            "last_editor_id": current_user.id,
            "edited_at": datetime.datetime.utcnow(),
            "headers": form.headers.data,
            "environment": form.environment.data,
            "job_type": form.job_type.data,
            "day_of_week": form.day_of_week.data,
            "hour": form.hour.data,
            "minute": form.minute.data,
            "hours": form.hours.data,
            "minutes": form.minutes.data,
            "seconds": form.seconds.data,
            "enabled": form.enabled.data,
        }

        # FIX: Store the old enabled state before updating
        was_enabled = trigger.enabled

        for k, v in after.items():
            setattr(trigger, k, v)
        
        changes = app.models.core.make_changelog(before, after)
        trigger.log_edit(
            current_user.id,
            ACTION_ENUM.MODIFY,
            message=changes
        )
        db.session.commit()

        # FIX: Update the scheduler with the new trigger configuration
        try:
            app.docker_scheduler.update_trigger(trigger)
            flash('Scheduled Trigger updated successfully!', 'success')
        except Exception as e:
            flash(f'Scheduled Trigger updated in database but failed to update scheduler: {str(e)}', 'warning')

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
        edit_log=edit_log,
        back = url_for("docker.scheduler.view", trigger_id=trigger_id),
        back_text = "Back to Scheduler "+trigger_id
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
def delete(trigger_id: int) -> str:
    trigger = ScheduleTrigger.query.get_or_404(trigger_id)
    
    # FIX: Remove from scheduler before deleting from database
    try:
        app.docker_scheduler.remove_trigger(trigger.id)
    except Exception as e:
        flash(f'Warning: Failed to remove trigger from scheduler: {str(e)}', 'warning')
    
    db.session.delete(trigger)
    db.session.commit()
    
    flash('Trigger deleted successfully!', 'success')
    return redirect(url_for('docker.scheduler.index'))


@blueprint.route('/scheduler/<trigger_id>/update', methods=['POST'])
@app.permission_required(app.models.core.PERMISSION_ENUM.ADMIN)
def update_scheduler_trigger(trigger_id):
    """Manually update a specific trigger in the scheduler"""
    trigger = ScheduleTrigger.query.get_or_404(trigger_id)
    try:
        app.docker_scheduler.update_trigger(trigger)
        return jsonify({
            'success': True,
            'message': f'Trigger {trigger.name} updated in scheduler successfully'
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'Failed to update trigger in scheduler: {str(e)}'
        }), 500


@blueprint.route('/scheduler/<trigger_id>/toggle', methods=['POST'])
@app.permission_required(app.models.core.PERMISSION_ENUM.ADMIN)
def toggle_trigger(trigger_id):
    """Enable or disable a trigger"""
    trigger = ScheduleTrigger.query.get_or_404(trigger_id)
    
    # Toggle the enabled state
    trigger.enabled = not trigger.enabled
    trigger.last_editor_id = current_user.id
    trigger.edited_at = datetime.datetime.utcnow()
    
    # Log the change
    action = ACTION_ENUM.MODIFY
    message = f"Trigger {'enabled' if trigger.enabled else 'disabled'} by {current_user.name}"
    trigger.log_edit(current_user.id, action, message=message)
    
    db.session.commit()
    
    # Update the scheduler
    try:
        app.docker_scheduler.update_trigger(trigger)
        status = 'enabled' if trigger.enabled else 'disabled'
        flash(f'Trigger {status} successfully!', 'success')
    except Exception as e:
        flash(f'Trigger updated in database but failed to update scheduler: {str(e)}', 'warning')
    
    return redirect(url_for('docker.scheduler.index'))
