import os
import logging
from datetime import datetime
from flask import Flask
from flask_login import current_user
from flask_sqlalchemy import SQLAlchemy
from werkzeug.datastructures import ImmutableDict
from ...main import db
from ...modules.parsing import pretty_date, localize
from ...models import User, BaseEditable, BaseEditLog, ACTION_ENUM

class Document(BaseEditable):
    __tablename__ = "Document"
    __bind_key__ = "cetadash_db"
    content = db.Column(db.Text)

    @property
    def title(self):
        return self.name

    def log_edit(
        self,
        user_id:int,
        action:int = ACTION_ENUM.MODIFY,
        message:str = ""
    ):
        return super().log_edit(
            DocumentEditLog,
            user_id,
            action=action,
            document_id=self.id,
            message=message
        )
    
    def log_run(self, *args, **kw):
        raise NotImplemented
    
    def log_scheduled_run(self, *args, **kw):
        raise NotImplemented


class DocumentEditLog(BaseEditLog):
    __tablename__ = "DocumentEditLog"
    __bind_key__ = "cetadash_db"
    document_id = db.Column(db.Integer, db.ForeignKey('Document.id'), nullable=False)
    document = db.relationship("Document", foreign_keys=[document_id], backref="edit_logs")


def init_db(app:Flask) -> None:
    """Initialize Docu db"""
    logging.info("Initializing Docu db")
    with app.app_context():
        db.create_all(bind_key=["cetadash_db"])
        db.session.commit()
        app.models.docu = ImmutableDict()
        for obj in (Document, DocumentEditLog):
            setattr(app.models.docu, obj.__name__, obj)

        if not len(Document.query.all()):
            documents = []
            for file in os.scandir("docu"):
                if file.is_file():
                    with open(file.path) as f:
                        content = f.read()
                        documents.append(Document(
                            name = f.name,
                            content = content,
                            creator_id = 1,
                            last_editor_id = 1,
                        ))
            db.session.add_all(documents)
            db.session.commit()