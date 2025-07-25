import os
import time
import datetime
from flask import (
    Blueprint,
    render_template,
    redirect,
    url_for,
    flash,
    request
)
from flask_login import current_user
from ...main import app, db
from ...modules.parsing import make_table_page
from .models import db, Document, DocumentEditLog, init_db
from .forms import DocumentForm

blueprint = Blueprint(
    'docu',
    __name__,
    url_prefix="/docu",
    static_folder=os.path.join(os.path.dirname(__file__),"static"),
    template_folder=os.path.join(os.path.dirname(__file__), "templates"),
)
blueprint.init_db = init_db


@blueprint.route('/')
@app.permission_required(app.models.core.PERMISSION_ENUM.USER)
def index():
    search_query = request.args.get('q', '')
    page = request.args.get('page', 1, type=int)
    per_page = 10
    documents = Document.query.paginate(page=page, per_page=per_page)
    
    search_bar = app.wtf.cd.search_bar(
        endpoint = url_for('docu.index'),
        search_query=search_query,
        placeholder="Search by title / content."
    )
    
    new_button = app.wtf.cd.table_button(
        "New Document",
        url_args=["docu.create",{}],
        classes="bi bi-plus",
        btn_type="success",
    )   

    return make_table_page(
        "docu",
        title="Documentation",
        columns=[
            "[ID] Document",
            "Created By",
            # "Created At",
            # "Last Edited By",
            "Updated At",
        ],
        rows=[
            (
                app.wtf.a(
                    f"[{d.id}]{d.title}",
                    href=url_for('docu.view', document_id=d.id)
                )
                + (
                    app.wtf.cd.table_icon_button(
                        url_args=("docu.edit",{"document_id":d.id}),
                        classes="bi-pencil",
                        btn_type="transparent",
                        tooltip="Edit document",
                        float="right"
                    ) if current_user.is_admin
                    else ""
                ),
                d.creator.name,
                # d.created_at_pretty,
                # d.last_editor.name,
                d.edited_at_pretty,
            )
            for d in documents  
        ],
        header_elements=[new_button] if current_user.is_admin else [],
        body_elements=[search_bar]
    )


@blueprint.route('/create', methods=['GET', 'POST'])
@app.permission_required(app.models.core.PERMISSION_ENUM.ADMIN)
def create():
    form = DocumentForm()
    if request.method == 'POST' and form.validate_on_submit():
        document = Document(
            name=form.name.data,
            content=form.content.data,
            creator_id=current_user.id,
            last_editor_id=current_user.id,
            description=form.description.data,
            details=form.details.data
        )
        db.session.add(document)
        db.session.commit()
        flash('Document created successfully!', 'success')
        return redirect(url_for('docu.view', document_id=document.id))
    return render_template('docu/new.html', form=form)


@blueprint.route('/edit/<int:document_id>', methods=['GET', 'POST'])
@app.permission_required(app.models.core.PERMISSION_ENUM.ADMIN)
def edit(document_id):
    document = Document.query.get_or_404(document_id)
    form = DocumentForm()
    if request.method == 'POST' and form.validate_on_submit():
        before = {
            "name" : document.name,
            "content" : document.content,
            "edited_at" : document.edited_at,
            "last_editor_id" : document.last_editor_id,
            "description" : document.description,
            "details" : document.details
        }
        after = {
            "name" : form.name.data,
            "content" : form.content.data,
            "edited_at" : datetime.datetime.utcnow(),
            "last_editor_id" : current_user.id,
            "description" : form.description.data,
            "details" : form.details.data
        }
        for k, v in after.items():
            setattr(document, k, v)
        changes = app.models.core.make_changelog(before, after)
        document.log_edit(
            current_user.id,
            app.models.core.ACTION_ENUM.MODIFY,
            message=changes
        )
        db.session.commit()
        flash('Document edit successfully!', 'success')
        return redirect(url_for('docu.view', document_id=document_id))

    form.process(data={
        'name': document.name,
        'content': document.content,
        'details': document.details,
        'description': document.description,
    })
    return render_template('docu/edit.html', form=form, document=document, form_object=form.content)


@blueprint.route('/view/<int:document_id>')
@app.permission_required(app.models.core.PERMISSION_ENUM.USER)
def view(document_id):
    document = Document.query.get_or_404(document_id)
    return render_template('docu/view.html', document=document)


@blueprint.route('/edits/<int:document_id>/<int:log_id>', methods=['GET','POST'])
@app.permission_required(app.models.core.PERMISSION_ENUM.ADMIN)
def edits(document_id, log_id):
    document = Document.query.get_or_404(document_id) 
    edit_log = DocumentEditLog.query.get_or_404(log_id)

    if not document.id == edit_log.document_id:
        raise ValueError("Document and edit log do not match")

    return render_template(
        'docu/changelog.html',
        edit_log=edit_log,
        back = url_for("docu.view", document_id=document.id),
        back_text = "Back to Document "+document.name
    )