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
    WorkflowEditLog,
    Workflow,
    ACTION_ENUM
)
from ..forms import EditWorkflowForm

blueprint = Blueprint(
    'workflows',
    __name__,
    static_folder=os.path.join(os.path.dirname(os.path.dirname(__file__)),"static"),
    template_folder=os.path.join(os.path.dirname(os.path.dirname(__file__)), "templates"),
)


@blueprint.route('/')
@app.permission_required(app.models.core.PERMISSION_ENUM.ADMIN)
def index():
    workflows = Workflow.query.all()
    new_button = make_table_button(
        "New Workflow",
        url_args=[["docker.workflows.create"], {}],
        classes=["bi", "bi-plus"],
        btn_type="success"
    )
    page = make_table_page(
        "workflows",
        title = "Docker Workflows",
        columns = [
            "[ID] Name",
            "Created",
            "Creator",
            "Edited",
            "Editor",
            "Actions", 
        ],
        rows = [
            (
                f"""<a href="{url_for('docker.workflows.view', workflow_id=workflow.id)}">[{workflow.id}] {workflow.name}</a>""",
                workflow.created_at_pretty,
                workflow.creator.name,
                workflow.edited_at_pretty,
                workflow.last_editor.name,
                make_table_icon_button(
                    ((f'docker.workflows.edit',),{'workflow_id':workflow.id}),
                    classes=[f"bi-pencil"],
                    tooltip='Edit Workflow',
                    method="GET"
                ) + make_table_icon_button(
                    ((f'docker.workflows.delete',),{'workflow_id':workflow.id}),
                    classes=[f"bi-trash"],
                    tooltip='Delete Workflow'
                )
            )
            for workflow in workflows 
        ],
        header_elements=[new_button] if current_user.is_admin else [],
    )
    return page


@blueprint.route('/create', methods=['GET','POST'])
@app.permission_required(app.models.core.PERMISSION_ENUM.ADMIN)
def create():
    form = EditWorkflowForm()
    if request.method == "POST" and form.validate_on_submit():
        workflow = Workflow(
            name=form.name.data,
            creator_id=current_user.id,
            last_editor_id=current_user.id,
            description=form.description.data,
            details=form.details.data,

        )
        db.session.add(workflow)
        db.session.commit()
        incoming_ids = [int(_id) for _id in form.tasks.data]
        for _id in incoming_ids:
            workflow.add_task(WorkflowTask.query.get(_id))
        workflow.reorder_tasks([int(_id) for _id in form.tasks.data])
        workflow.log_edit(current_user.id, ACTION_ENUM.CREATE)
        db.session.commit()
        flash('Docker Workflow created successfully!', 'success')
        return redirect(url_for('docker.workflows.view', workflow_id=workflow.id))
    
    all_tasks = WorkflowTask.query.all()
    task_map = {task.id: task for task in all_tasks}
    task_name_map = {task.id: task.name for task in all_tasks}
    return render_template(
        'workflow/new.html',
        form=form,
        task_map=task_map,
        all_tasks=all_tasks,
        task_name_map=task_name_map,
        available_tasks=all_tasks
    )

@blueprint.route('/workflow/<workflow_id>/edit', methods=['GET','POST'])
@app.permission_required(app.models.core.PERMISSION_ENUM.ADMIN)
def edit(workflow_id):
    workflow = Workflow.query.get_or_404(workflow_id)    
    form = EditWorkflowForm()

    used_task_ids = workflow.prioritized_task_ids

    before = {
        "name" : workflow.name,
        "description" : workflow.description,
        "details" : workflow.details,
        "last_editor_id" : workflow.last_editor_id,
        "edited_at" : workflow.edited_at,
        'tasks':  used_task_ids
    }

    if request.method == "POST" and form.validate_on_submit():
        incoming_ids = [int(_id) for _id in form.tasks.data]
        for _id in incoming_ids:
            if _id in used_task_ids:
                continue
            workflow.add_task(WorkflowTask.query.get(_id))
        for _id in used_task_ids:
            if not _id in incoming_ids:
                workflow.remove_task(WorkflowTask.query.get(_id))
        workflow.reorder_tasks([int(_id) for _id in form.tasks.data])
        after = {
            "name" : form.name.data,
            "last_editor_id" : current_user.id,
            "edited_at" : datetime.datetime.utcnow(),
            "details" : form.details.data,
            "description": form.description.data,
            "tasks" : workflow.prioritized_task_ids
        }
        for k, v in after.items():
            if k == "tasks":
                continue
            setattr(workflow, k, v)
        changes = app.models.core.make_changelog(before, after)
        workflow.log_edit(
            current_user.id,
            ACTION_ENUM.MODIFY,
            message = changes
        )
        db.session.commit()
        flash('Docker Workflow Edited Successfully!', 'success')
        return redirect(url_for('docker.workflows.view', workflow_id=workflow_id))

    before.pop("edited_at")
    before.pop("last_editor_id")
    form.process(data=before)

    all_tasks = WorkflowTask.query.all()
    task_map = {task.id: task for task in all_tasks}
    task_name_map = {task.id: task.name for task in all_tasks}
    available_tasks = [task for task in all_tasks if task.id not in used_task_ids]
    return render_template(
        'workflow/edit.html',
        workflow=workflow,
        form=form,
        task_map=task_map,
        task_name_map=task_name_map,
        available_tasks=available_tasks
    )


@blueprint.route('/workflow/<workflow_id>/view', methods=['GET','POST'])
@app.permission_required(app.models.core.PERMISSION_ENUM.ADMIN)
def view(workflow_id):
    workflow = Workflow.query.get_or_404(workflow_id)    
    return render_template('workflow/view.html', workflow=workflow)


@blueprint.route('/workflow/<workflow_id>/edits/<log_id>', methods=['GET','POST'])
@app.permission_required(app.models.core.PERMISSION_ENUM.ADMIN)
def edits(workflow_id, log_id):
    workflow = Workflow.query.get_or_404(workflow_id) 
    edit_log = WorkflowEditLog.query.get_or_404(log_id)

    if not workflow.id == edit_log.workflow.id:
        raise ValueError("Workflow and edit log do not match")

    return render_template(
        'workflow/changelog.html',
        workflow=workflow,
        edit_log=edit_log
    )


@blueprint.route('/workflow/<workflow_id>/delete', methods=['POST'])
@app.permission_required(app.models.core.PERMISSION_ENUM.ADMIN)
def delete(workflow_id):
    workflow = Workflow.query.get_or_404(workflow_id)
    WorkflowTaskAssociation.query.filter_by(workflow_id=workflow.id).delete()
    db.session.delete(workflow)
    db.session.commit()
    flash('Docker Workflow deleted successfully!', 'success')
    return redirect(url_for('docker.workflows.index'))