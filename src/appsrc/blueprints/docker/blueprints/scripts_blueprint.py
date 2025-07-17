import os
import datetime
from ....modules.parsing import make_table_page
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
    WorkflowScript,
    WorkflowScriptEditLog,
    WorkflowScriptRunLog,
    WorkflowScriptScheduledRunLog,
    ACTION_ENUM,
    STATUS_ENUM
)
from ..forms import EditScriptForm

blueprint = Blueprint(
    'scripts',
    __name__,
    static_folder=os.path.join(os.path.dirname(os.path.dirname(__file__)),"static"),
    template_folder=os.path.join(os.path.dirname(os.path.dirname(__file__)), "templates"),
)

@blueprint.route('/')
@app.permission_required(app.models.core.PERMISSION_ENUM.ADMIN)
def index():
    scripts = WorkflowScript.query.all()
    new_button = app.wtf.cd.table_button(
        "New Containerized Script",
        url_args=["docker.scripts.create",{}],
        classes="bi bi-plus",
        btn_type="success"
    )
    page = make_table_page(
        "scripts",
        title = "Workflow Script",
        columns = [
            "[ID] Name",
            "Actions",
            # "Created",
            # "Creator",
            "Updated",
            # "Editor" 
        ],
        rows = [
            (
                app.wtf.a(
                    f"[{script.id}] {script.name}",
                    href=url_for('docker.scripts.view', script_id=script.id),                    
                ),
                app.wtf.cd.table_button_row( 
                    app.wtf.cd.table_icon_button(
                        ('docker.scripts.edit',{'script_id':script.id}),
                        classes="bi-pencil",
                        tooltip='Edit Script',
                        method="GET"
                    ) + app.wtf.cd.table_icon_button(
                        ('docker.scripts.delete',{'script_id':script.id}),
                        classes="bi-trash",
                        tooltip='Delete Script'
                    )
                ),
                # script.created_at_pretty,
                # script.creator.name,
                script.edited_at_pretty,
                # script.last_editor.name
            )
            for script in scripts 
        ],
        header_elements=[new_button] if current_user.is_admin else [],
    )
    return page


@blueprint.route('/create', methods=['GET', 'POST'])
@app.permission_required(app.models.core.PERMISSION_ENUM.ADMIN)
def create():
    form = EditScriptForm()
    if request.method == "POST" and form.validate_on_submit():
        script = WorkflowScript(
            name=form.name.data,
            creator_id=current_user.id,
            last_editor_id=current_user.id,
            script=form.script.data,
            environment=form.environment.data,
            description=form.description.data,
            details=form.details.data,
            network_enabled=form.network_enabled.data,
            dependencies=form.dependencies.data
        )
        db.session.add(script)
        db.session.commit()
        flash('Script created successfully!', 'success')
        return redirect(url_for('docker.scripts.view', script_id=script.id))
 
    return render_template('script/edit.html', form=form)


@blueprint.route('/script/<script_id>/edit', methods=['GET','POST'])
@app.permission_required(app.models.core.PERMISSION_ENUM.ADMIN)
def edit(script_id):
    script = WorkflowScript.query.get_or_404(script_id)    
    form = EditScriptForm()
    before = {
        "name" : script.name,
        "last_editor_id" : script.last_editor_id,
        "edited_at" : script.edited_at,
        "script" : script.script,
        "environment" : script.environment,
        "description" : script.description,
        "details" : script.details,
        "network_enabled" : script.network_enabled,
        "dependencies" : script.dependencies
    }

    if request.method == "POST" and form.validate_on_submit():
        after = {
            "name": form.name.data,
            "last_editor_id": current_user.id,
            "edited_at": datetime.datetime.utcnow(),
            "script": form.script.data,
            "environment": form.environment.data,
            "description": form.description.data,
            "details": form.details.data,
            "network_enabled": form.network_enabled.data,
            "dependencies": form.dependencies.data,
        }
        for k, v in after.items():
            setattr(script, k, v)
        changes = app.models.core.make_changelog(before, after)
        script.log_edit(
            current_user.id,
            ACTION_ENUM.MODIFY,
            message = changes
        )
        db.session.commit()
        flash('Script updated successfully!', 'success')
        return redirect(url_for('docker.scripts.view', script_id=script_id))
    
    before.pop("last_editor_id")
    before.pop("edited_at")

    form.process(data=before)
    return render_template('script/edit.html', script=script, form=form)


@blueprint.route('/script/<script_id>/view', methods=['GET','POST'])
@app.permission_required(app.models.core.PERMISSION_ENUM.ADMIN)
def view(script_id):
    script = WorkflowScript.query.get_or_404(script_id)    
    return render_template('script/view.html', script=script)


@blueprint.route('/script/<script_id>/edits/<log_id>', methods=['GET','POST'])
@app.permission_required(app.models.core.PERMISSION_ENUM.ADMIN)
def edits(script_id, log_id):
    script = WorkflowScript.query.get_or_404(script_id) 
    edit_log = WorkflowScriptEditLog.query.get_or_404(log_id)

    if not script.id == edit_log.script.id:
        raise ValueError("Script and edit log do not match")

    return render_template(
        'script/changelog.html',
        edit_log=edit_log,
        back = url_for("docker.scripts.view", script_id=script_id),
        back_text = "Back to Script "+script_id
    )


@blueprint.route('/script/<script_id>/delete', methods=['POST'])
@app.permission_required(app.models.core.PERMISSION_ENUM.ADMIN)
def delete(script_id):
    script = WorkflowScript.query.get_or_404(script_id)
    
    script.log_edit(
        current_user.id,
        ACTION_ENUM.DELETE,
        message=f"Script '{script.name}' deleted"
    )

    # Delete related run logs
    WorkflowScriptRunLog.query.filter_by(script_id=script.id).delete()
    WorkflowScriptScheduledRunLog.query.filter_by(script_id=script.id).delete()
    
    db.session.delete(script)
    db.session.commit()
    
    flash('Script deleted successfully!', 'success')
    return redirect(url_for('docker.scripts.index'))