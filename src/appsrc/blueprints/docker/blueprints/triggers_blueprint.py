import os
import datetime
import queue
import threading
from ....modules.parsing import make_table_page
from flask import (
    Blueprint,
    render_template,
    redirect,
    url_for,
    flash,
    request,
    Response,
    stream_with_context
)
from flask_login import current_user
from ..models import (
    app,
    db,
    Workflow,
    WorkflowTrigger,
    WorkflowTaskAssociation,
    WorkflowTriggerEditLog,
    WorkflowTriggerRunLog,
    ACTION_ENUM,
    STATUS_ENUM
)
from ..forms import TriggerForm
from .trigger_handling import handle_trigger

blueprint = Blueprint(
    'triggers',
    __name__,
    static_folder=os.path.join(os.path.dirname(os.path.dirname(__file__)),"static"),
    template_folder=os.path.join(os.path.dirname(os.path.dirname(__file__)), "templates"),
)


@blueprint.route('/')
@app.permission_required(app.models.core.PERMISSION_ENUM.ADMIN)
def index():
    triggers = WorkflowTrigger.query.all()
    new_button = app.wtf.cd.table_button(
        "New Trigger",
        url_args=["docker.triggers.create",{}],
        classes="bi bi-plus",
        btn_type="success"
    )
    page = make_table_page(
        "triggers",
        title = "Workflow Triggers",
        columns = [
            "Name",
            # "Status",
            "Actions",
            "Endpoint",
            "Created",
            # "Creator",
            "Updated",
            # "Editor" 
        ],
        rows = [
            (
                app.wtf.a(
                    f"[{trigger.id}] {trigger.name}",
                    href=url_for('docker.triggers.view', trigger_id=trigger.id),
                    classes="link-primary"
                ),
                # app.wtf.bs.badge(
                #     ["Disabled","Enabled"][trigger.enabled],
                #     classes="badge-pill "+["bg-danger", "bg-success"][trigger.enabled]
                # ),
                app.wtf.cd.table_button_row(
                    app.wtf.cd.table_icon_button(
                        ('docker.triggers.toggle_trigger',{'trigger_id':trigger.id}),
                        classes=["bi-toggle-off text-danger", "bi-toggle-on text-success"][trigger.enabled],
                        tooltip=f'Toggle Trigger {"Off" if trigger.enabled else "On"} \
                            [Currently {"Enabled" if trigger.enabled else "Disabled"}]',
                        method="POST",
                        float=None
                    ) + app.wtf.cd.table_icon_button(
                        ('',{}),
                        classes="bi-play",
                        on_click=f"openIframeModal(`Running Trigger {trigger.name}`, \
                            '{url_for('docker.triggers.actionframe', trigger_id=trigger.id)}')",
                        do_action=False,
                        tooltip='Run Trigger',
                        float=None
                    ) + app.wtf.cd.table_icon_button(
                        ('docker.triggers.edit',{'trigger_id':trigger.id}),
                        classes="bi-pencil",
                        tooltip='Edit Trigger',
                        method="GET",
                        float=None
                    ) + app.wtf.cd.table_icon_button(
                        ('docker.triggers.delete',{'trigger_id':trigger.id}),
                        classes="bi-trash",
                        tooltip='Delete Trigger',
                        float=None
                    )
                ),
                app.wtf.a(
                    trigger.endpoint,
                    href=url_for('docker.triggers.activate', trigger_id=trigger.id),
                    classes="link-secondary"
                ),
                trigger.created_at_pretty,
                # trigger.creator.name,
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
    form = TriggerForm()
    form.workflow.query_factory = lambda: Workflow.query.order_by(Workflow.name).all()

    if form.validate_on_submit():
        workflow = form.workflow.data

        if not workflow:
            flash("You must select a workflow.", "danger")
            return render_template("scheduler/new.html", form=form, object_type="Workflow Task")

        trigger = WorkflowTrigger(
            name=form.name.data,
            endpoint=form.endpoint.data,
            description=form.description.data,
            details=form.details.data,
            creator_id=current_user.id,
            last_editor_id=current_user.id,
            workflow_id=workflow.id,
            headers=form.headers.data,
            environment=form.environment.data,
            enabled=form.enabled.data
        )
        db.session.add(trigger)
        db.session.commit()
        tlog = trigger.log_edit(current_user.id, ACTION_ENUM.CREATE)
        db.session.commit()
        trigger_id = trigger.id
        flash('Workflow Trigger created successfully!', 'success')
        return redirect(url_for('docker.triggers.view', trigger_id=trigger_id))
    return render_template('trigger/new.html', form=form)


@blueprint.route('/trigger/<trigger_id>/edit', methods=['GET','POST'])
@app.permission_required(app.models.core.PERMISSION_ENUM.ADMIN)
def edit(trigger_id):
    trigger = WorkflowTrigger.query.get_or_404(trigger_id)
    form = TriggerForm()
    form.workflow.query_factory = lambda: Workflow.query.order_by(Workflow.name).all()
    
    before = {
        'name': trigger.name,
        'endpoint': trigger.endpoint,
        'workflow_id': trigger.workflow_id,
        "description": trigger.description,
        "details": trigger.details,
        "headers": trigger.headers,
        "environment": trigger.environment,
        "last_editor_id": trigger.last_editor_id,
        "edited_at": trigger.edited_at,
        "enabled" : trigger.enabled
    }
    
    if request.method == "POST" and form.validate_on_submit():
        workflow = form.workflow.data
        after = {
            "name": form.name.data,
            "description": form.description.data,
            "details": form.details.data,
            "endpoint": form.endpoint.data,
            "workflow_id": workflow.id,
            "last_editor_id": current_user.id,
            "edited_at": datetime.datetime.utcnow(),
            "headers": form.headers.data,
            "environment": form.environment.data,
            "enabled": form.enabled.data
        }
        print(after)
        for k, v in after.items():
            setattr(trigger, k, v)
        changes = app.models.core.make_changelog(before, after)
        trigger.log_edit(
            current_user.id,
            ACTION_ENUM.MODIFY,
            message = changes
        )

        db.session.commit()
        flash('Workflow Trigger edited successfully!', 'success')
        return redirect(url_for('docker.triggers.view', trigger_id=trigger_id))
    
    before.pop("edited_at")
    before.pop("last_editor_id")
    form.process(data=before)
    return render_template('trigger/edit.html', trigger=trigger, form=form)


@blueprint.route('/trigger/<trigger_id>/view', methods=['GET','POST'])
@app.permission_required(app.models.core.PERMISSION_ENUM.ADMIN)
def view(trigger_id):
    trigger = WorkflowTrigger.query.get_or_404(trigger_id)    
    return render_template('trigger/view.html', trigger=trigger)


@blueprint.route('/trigger/<trigger_id>/edits/<log_id>', methods=['GET','POST'])
@app.permission_required(app.models.core.PERMISSION_ENUM.ADMIN)
def edits(trigger_id, log_id):
    trigger = WorkflowTrigger.query.get_or_404(trigger_id) 
    edit_log = WorkflowTriggerEditLog.query.get_or_404(log_id)

    if not trigger.id == edit_log.trigger.id:
        raise ValueError("Trigger and edit log do not match")

    return render_template(
        'trigger/changelog.html',
        edit_log=edit_log,
        back = url_for("docker.triggers.view", trigger_id=trigger_id),
        back_text = "Back to Trigger "+trigger_id
    )


@blueprint.route('/trigger/<trigger_id>/logs/<log_id>', methods=['GET','POST'])
@app.permission_required(app.models.core.PERMISSION_ENUM.ADMIN)
def logs(trigger_id, log_id):
    trigger = WorkflowTrigger.query.get_or_404(trigger_id) 
    run_log = WorkflowTriggerRunLog.query.get_or_404(log_id)
    if not trigger.id == run_log.trigger.id:
        raise ValueError("Trigger and edit log do not match")
    return render_template('pages/log_stack_page.html', log=run_log)


@blueprint.route('/trigger/<trigger_id>/delete', methods=['POST'])
@app.permission_required(app.models.core.PERMISSION_ENUM.ADMIN)
def delete(trigger_id):
    trigger = WorkflowTrigger.query.get_or_404(trigger_id)
    db.session.delete(trigger)
    db.session.commit()
    flash('Trigger deleted successfully!', 'success')
    return redirect(url_for('docker.triggers.index'))


@blueprint.route('/trigger/<trigger_id>/activate', methods=['GET','POST'])
@app.permission_required(app.models.core.PERMISSION_ENUM.ADMIN)
def activate(trigger_id):
    request_headers = request.headers
    result_queue = queue.Queue()
    trigger = WorkflowTrigger.query.get_or_404(trigger_id)
    if not trigger.enabled:
        flash("Trigger is not enabled.", 'danger')
        return redirect(url_for("docker.triggers.index"))
    workflow = Workflow.query.get_or_404(trigger.workflow_id)
    tasks = [
        assoc.task for assoc in 
        workflow.task_associations.order_by(
            WorkflowTaskAssociation.priority.asc()
        )
    ]
    
    threading.Thread(
        target=handle_trigger,
        args=(current_user.id, trigger, request_headers, workflow, tasks, result_queue, True),
        daemon=False
    ).start()

    @stream_with_context
    def generate():
        yield f"data: 🖥️▶️ Running trigger {trigger.name} ({trigger.id})\n\n"
        while True:
            try:
                line = result_queue.get(timeout=0.5)
                if line == "__COMPLETE__":
                    result_queue.task_done()
                    yield "data: 🖥️✅ Trigger completed.\n\n"
                    break
                yield "data: " + line + "\n\n"
                result_queue.task_done()
            except queue.Empty:
                continue
            except GeneratorExit:
                break

    return Response(generate(), mimetype='text/event-stream')


@blueprint.route('/trigger/<trigger_id>/actionframe', methods=['GET', 'POST'])
@app.permission_required(app.models.core.PERMISSION_ENUM.ADMIN)
def actionframe(trigger_id):
    return render_template("pages/stream_frame.html", stream_url=url_for("docker.triggers.activate", trigger_id=trigger_id))


@blueprint.route('/trigger/<trigger_id>/toggle', methods=['POST'])
@app.permission_required(app.models.core.PERMISSION_ENUM.ADMIN)
def toggle_trigger(trigger_id):
    """Enable or disable a trigger"""
    trigger = WorkflowTrigger.query.get_or_404(trigger_id)
    
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
    
    return redirect(url_for('docker.triggers.index'))
