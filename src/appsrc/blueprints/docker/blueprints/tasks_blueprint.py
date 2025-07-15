import os
import datetime
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
    request
)
from flask_login import current_user
from ..models import (
    app,
    db,
    WorkflowTask,
    WorkflowTaskAssociation,
    WorkflowTaskEditLog,
    Workflow,
    ACTION_ENUM,
    STATUS_ENUM
)
from ..forms import EditWorkflowTaskForm

blueprint = Blueprint(
    'tasks',
    __name__,
    static_folder=os.path.join(os.path.dirname(os.path.dirname(__file__)),"static"),
    template_folder=os.path.join(os.path.dirname(os.path.dirname(__file__)), "templates"),
)

@blueprint.route('/')
@app.permission_required(app.models.core.PERMISSION_ENUM.ADMIN)
def index():
    tasks = WorkflowTask.query.all()
    new_button = make_table_button(
        "New Workflow Task",
        url_args=[["docker.tasks.create"], {}],
        classes=["bi", "bi-plus"],
        btn_type="success"
    )
    page = make_table_page(
        "tasks",
        title = "Workflow Tasks",
        columns = [
            "[ID] Name",
            "Created",
            "Creator",
            "Updated",
            "Editor" 
        ],
        rows = [
            (
                app.wtf.span(
                    f"""<a href="{url_for('docker.tasks.view', task_id=task.id)}">[{task.id}] {task.name}</a>"""
                    + app.wtf.br() + app.wtf.span(
                        make_table_icon_button(
                            ((f'docker.tasks.edit',),{'task_id':task.id}),
                            classes=[f"bi-pencil"],
                            tooltip='Edit Task',
                            method="GET"
                        ) + make_table_icon_button(
                            ((f'docker.tasks.delete',),{'task_id':task.id}),
                            classes=[f"bi-trash"],
                            tooltip='Delete Task'
                        ),
                        style="display: inline-block;",
                        classes="float-right"
                    ),
                    classes="d-flex justify-content-between"
                ),
                task.created_at_pretty,
                task.creator.name,
                task.edited_at_pretty,
                task.last_editor.name
            )
            for task in tasks 
        ],
        header_elements=[new_button] if current_user.is_admin else [],
    )
    return page


@blueprint.route('/create', methods=['GET', 'POST'])
@app.permission_required(app.models.core.PERMISSION_ENUM.ADMIN)
def create():
    form = EditWorkflowTaskForm()
    if request.method == "POST" and form.validate_on_submit():
        workflowtask = WorkflowTask(
            name=form.name.data,
            creator_id=current_user.id,
            last_editor_id=current_user.id,
            template=form.template.data,
            environment=form.environment.data,
            description=form.description.data,
            details=form.details.data
        )
        db.session.add(workflowtask)
        db.session.commit()
        flash('Workflow Task created successfully!', 'success')
        return redirect(url_for('docker.tasks.view', task_id=workflowtask.id))
 
    return render_template('task/edit.html', form=form)


@blueprint.route('/task/<task_id>/edit', methods=['GET','POST'])
@app.permission_required(app.models.core.PERMISSION_ENUM.ADMIN)
def edit(task_id):
    workflowtask = WorkflowTask.query.get_or_404(task_id)    
    form = EditWorkflowTaskForm()
    before = {
        "name" : workflowtask.name,
        "last_editor_id" : workflowtask.last_editor_id,
        "edited_at" : workflowtask.edited_at,
        "template" : workflowtask.template,
        "environment" : workflowtask.environment,
        "description" : workflowtask.description,
        "details" : workflowtask.details,
    }

    if request.method == "POST" and form.validate_on_submit():
        after = {
            "name": form.name.data,
            "last_editor_id": current_user.id,
            "edited_at": datetime.datetime.utcnow(),
            "template": form.template.data,
            "environment": form.environment.data,
            "description": form.description.data,
            "details": form.details.data,
        }
        for k, v in after.items():
            setattr(workflowtask, k, v)
        changes = app.models.core.make_changelog(before, after)
        workflowtask.log_edit(
            current_user.id,
            ACTION_ENUM.MODIFY,
            message = changes
        )
        db.session.commit()
        flash('Workflow Task updated successfully!', 'success')
        return redirect(url_for('docker.tasks.view', task_id=task_id))
    
    before.pop("last_editor_id")
    before.pop("edited_at")

    form.process(data=before)
    return render_template('task/edit.html', workflowtask=workflowtask, form=form)


@blueprint.route('/task/<task_id>/view', methods=['GET','POST'])
@app.permission_required(app.models.core.PERMISSION_ENUM.ADMIN)
def view(task_id):
    task = WorkflowTask.query.get_or_404(task_id)    
    return render_template('task/view.html', task=task)


@blueprint.route('/task/<task_id>/edits/<log_id>', methods=['GET','POST'])
@app.permission_required(app.models.core.PERMISSION_ENUM.ADMIN)
def edits(task_id, log_id):
    task = WorkflowTask.query.get_or_404(task_id) 
    edit_log = WorkflowTaskEditLog.query.get_or_404(log_id)

    if not task.id == edit_log.task.id:
        raise ValueError("Task and edit log do not match")

    return render_template(
        'task/changelog.html',
        edit_log=edit_log,
        back = url_for("docker.tasks.view", task_id=task_id),
        back_text = "Back to Task "+task_id
    )


@blueprint.route('/task/<task_id>/delete', methods=['POST'])
@app.permission_required(app.models.core.PERMISSION_ENUM.ADMIN)
def delete(task_id):
    workflowtask = WorkflowTask.query.get_or_404(task_id)
    
    workflowtask.log_edit(
        current_user.id,
        ACTION_ENUM.DELETE,
        message=f"Task '{workflowtask.name}' deleted"
    )
    WorkflowTaskAssociation.query.filter_by(task_id=workflowtask.id).delete()
    
    from ..models import WorkflowTaskRunLog, WorkflowTaskScheduledRunLog
    WorkflowTaskRunLog.query.filter_by(task_id=workflowtask.id).delete()
    WorkflowTaskScheduledRunLog.query.filter_by(task_id=workflowtask.id).delete()
    
    db.session.delete(workflowtask)
    db.session.commit()
    
    flash('Workflow Task deleted successfully!', 'success')
    return redirect(url_for('docker.tasks.index'))