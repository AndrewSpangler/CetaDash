import os
import datetime
import logging
from flask_login import UserMixin, current_user
from sqlalchemy import func as sqlfunc
from sqlalchemy.orm import backref
from sqlalchemy.ext.declarative import declared_attr
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.datastructures import ImmutableDict
from ...main import db, app
from ...models import (
    User,
    BaseEditable,
    BaseLog,
    BaseEditLog,
    BaseActionLog,
    SYSTEM_ID,
    ACTION_ENUM,
    STATUS_ENUM
)

DEFAULT_HEADER_MAPPING = """
mappings:
    Remote-User:
        value: username
        nullable: false
    Remote-Groups:
        value: groups
"""


####################
# Tasks
####################
class WorkflowTask(BaseEditable):
    __tablename__ = "WorkflowTask"
    __bind_key__ = "cetadash_db"
    template = db.Column(db.Text, default="")
    environment = db.Column(db.Text, default="")
    use_script = db.Column(db.Boolean, default=False)

    script_id = db.Column(
        db.Integer,
        db.ForeignKey('WorkflowScript.id', ondelete='SET NULL'),
        nullable=True
    )
    script = db.relationship(
        'WorkflowScript',
        backref=db.backref('task', uselist=False)
    )

    def log_edit(
        self,
        user_id:int,
        action:int = ACTION_ENUM.MODIFY,
        **kw
    ):
        return super().log_edit(
            WorkflowTaskEditLog,
            user_id,
            action=action,
            task_id=self.id,
            **kw
        )
    
    def log_run(
        self,
        user_id:int,
        workflow_log_id:int,
        status:int = STATUS_ENUM.RUNNING
    ):
        return super().log_run(
            WorkflowTaskRunLog,
            user_id,
            status=status,
            task_id=self.id,
            workflow_log_id=workflow_log_id
        )
    
    def log_scheduled_run(
        self,
        workflow_log_id:int,
        status:int = STATUS_ENUM.RUNNING
    ):
        return super().log_run(
            WorkflowTaskScheduledRunLog,
            SYSTEM_ID,
            status=status,
            task_id=self.id,
            workflow_log_id=workflow_log_id
        )


class WorkflowTaskEditLog(BaseEditLog):
    __tablename__ = "WorkflowTaskEditLog"
    __bind_key__ = "cetadash_db"
    task_id = db.Column(
        db.Integer,
        db.ForeignKey('WorkflowTask.id', ondelete='CASCADE'),
        nullable=False
    )
    task = db.relationship(
        "WorkflowTask",
        foreign_keys=[task_id],
        backref=backref(
            "edit_logs",
            order_by="WorkflowTaskEditLog.id.desc()",
            cascade="all, delete-orphan"
        )
    )


class WorkflowTaskRunLog(BaseActionLog):
    __tablename__ = "WorkflowTaskRunLog"
    __bind_key__ = "cetadash_db"
    task_id = db.Column(
        db.Integer,
        db.ForeignKey('WorkflowTask.id', ondelete='CASCADE'),
        nullable=False
    )
    task = db.relationship(
        "WorkflowTask",
        foreign_keys=[task_id], 
        backref=backref(
            "run_logs",
            order_by="WorkflowTaskRunLog.id.desc()",
            cascade="all, delete-orphan"
        )
    )
    workflow_log_id = db.Column(
        db.Integer,
        db.ForeignKey('WorkflowRunLog.id', ondelete='CASCADE'),
        nullable=False
    )
    workflow_log = db.relationship(
        "WorkflowRunLog",
        foreign_keys=[workflow_log_id],
        backref=backref(
            "task_logs",
            order_by="WorkflowTaskRunLog.id.desc()",
            cascade="all, delete-orphan"
        )
    )


class WorkflowTaskScheduledRunLog(BaseActionLog):
    __tablename__ = "WorkflowTaskScheduledRunLog"
    __bind_key__ = "cetadash_db"
    task_id = db.Column(
        db.Integer,
        db.ForeignKey('WorkflowTask.id', ondelete='CASCADE'),
        nullable=False
    )
    task = db.relationship(
        "WorkflowTask",
        foreign_keys=[task_id],
        backref=backref(
            "scheduled_run_logs",
            order_by="WorkflowTaskScheduledRunLog.id.desc()",
            cascade="all, delete-orphan"
        )
    )
    workflow_log_id = db.Column(
        db.Integer,
        db.ForeignKey(
            'WorkflowScheduledRunLog.id',
            ondelete='CASCADE'
        ),
        nullable=False
    )
    workflow_log = db.relationship(
        "WorkflowScheduledRunLog",
        foreign_keys=[workflow_log_id],
        backref=backref(
            "scheduled_task_logs",
            order_by="WorkflowTaskScheduledRunLog.id.desc()",
            cascade="all, delete-orphan"
        )
    )


####################
# Workflows
####################
class Workflow(BaseEditable):
    __tablename__ = "Workflow"
    __bind_key__ = "cetadash_db"
    environment = db.Column(db.Text, default="")
    
    @property
    def prioritized_tasks(self):
        return [
            assoc.task for assoc in
            self.task_associations.order_by(WorkflowTaskAssociation.priority).all()
        ]
    
    @property
    def prioritized_task_ids(self):
        return [
            assoc.task_id for assoc in
            self.task_associations.order_by(WorkflowTaskAssociation.priority).all()
        ]

    def add_task(self, task: WorkflowTask, priority: int = None):
        if priority is None:
            max_priority = self.task_associations.with_entities(sqlfunc.max(WorkflowTaskAssociation.priority)).scalar()
            priority = (max_priority or 0) + 1
        assoc = WorkflowTaskAssociation(workflow=self, task=task, priority=priority)
        db.session.add(assoc)
    
    def remove_task(self, task: WorkflowTask):
        assoc = self.task_associations.filter_by(task_id=task.id).first()
        if assoc:
            db.session.delete(assoc)

            # reassign priorities to keep them consecutive
            remaining_assocs = self.task_associations.order_by(WorkflowTaskAssociation.priority).all()
            for index, remaining_assoc in enumerate(remaining_assocs):
                remaining_assoc.priority = index

    def reorder_tasks(self, task_ids_in_order: list[int]):
        for index, task_id in enumerate(task_ids_in_order):
            assoc = self.task_associations.filter_by(task_id=task_id).first()
            if assoc:
                assoc.priority = index
    
    def log_edit(self, user_id: int = None, action: int = ACTION_ENUM.MODIFY, **kw):
        return super().log_edit(WorkflowEditLog, user_id, action=action, workflow_id=self.id, **kw)
    
    def log_run(
        self,
        user_id:int,
        trigger_log_id:int,
        status:int = STATUS_ENUM.RUNNING,
        **kw
    ):
        return super().log_run(
            WorkflowRunLog,
            user_id,
            status=status,
            workflow_id=self.id,
            trigger_log_id=trigger_log_id,
            **kw
        )

    def log_scheduled_run(
        self,
        schedule_trigger_log_id:int,
        status:int = STATUS_ENUM.RUNNING,
        **kw
    ):
        return super().log_run(
            WorkflowScheduledRunLog,
            SYSTEM_ID,
            status=status,
            workflow_id=self.id,
            schedule_trigger_log_id=schedule_trigger_log_id,
            **kw
        )


class WorkflowEditLog(BaseEditLog):
    __tablename__ = "WorkflowEditLog"
    __bind_key__ = "cetadash_db"
    workflow_id = db.Column(
        db.Integer,
        db.ForeignKey('Workflow.id', ondelete='CASCADE'),
        nullable=False
    )
    workflow = db.relationship(
        "Workflow",
        foreign_keys=[workflow_id],
        backref=backref(
            "edit_logs",
            order_by="WorkflowEditLog.id.desc()",
            cascade="all, delete-orphan"
        )
    )


class WorkflowRunLog(BaseActionLog):
    __tablename__ = "WorkflowRunLog"
    __bind_key__ = "cetadash_db"
    workflow_id = db.Column(
        db.Integer,
        db.ForeignKey('Workflow.id', ondelete='CASCADE'),
        nullable=False
    )
    workflow = db.relationship(
        "Workflow",
        foreign_keys=[workflow_id],
        backref=backref(
            "run_logs",
            order_by="WorkflowRunLog.id.desc()",
            cascade="all, delete-orphan"
        )
    )
    trigger_log_id = db.Column(
        db.Integer,
        db.ForeignKey('WorkflowTriggerRunLog.id', ondelete='CASCADE'),
        nullable=False
    )
    trigger_log = db.relationship(
        "WorkflowTriggerRunLog", 
        foreign_keys=[trigger_log_id],
        backref=backref(
            "workflow_run_logs",
            cascade="all, delete-orphan"
        )
    )


class WorkflowScheduledRunLog(BaseActionLog):
    """Logs for scheduled triggers"""
    __tablename__ = "WorkflowScheduledRunLog"
    __bind_key__ = "cetadash_db"
    workflow_id = db.Column(
        db.Integer,
        db.ForeignKey('Workflow.id', ondelete='CASCADE'),
        nullable=False
    )
    workflow = db.relationship(
        "Workflow",
        foreign_keys=[workflow_id],
        backref=backref(
            "schedule_run_logs",
            order_by="WorkflowScheduledRunLog.id.desc()",
            cascade="all, delete-orphan"
        )
    )
    schedule_trigger_log_id = db.Column(
        db.Integer,
        db.ForeignKey('ScheduleTriggerRunLog.id', ondelete='CASCADE'),
        nullable=False
    )
    schedule_trigger_log = db.relationship(
        "ScheduleTriggerRunLog", 
        foreign_keys=[schedule_trigger_log_id],
        backref=backref(
            "workflow_scheduled_logs",
            cascade="all, delete-orphan"
        )
    )


class WorkflowTaskAssociation(db.Model):
    __tablename__ = "WorkflowTaskAssociation"
    __bind_key__ = "cetadash_db"
    id = db.Column(db.Integer, primary_key=True)
    workflow_id = db.Column(
        db.Integer,
        db.ForeignKey("Workflow.id", ondelete='CASCADE'),
        nullable=False
    )
    task_id = db.Column(
        db.Integer,
        db.ForeignKey("WorkflowTask.id", ondelete='CASCADE'),
        nullable=False
    )
    priority = db.Column(db.Integer, nullable=False, default=0)
    workflow = db.relationship(
        "Workflow",
        backref=db.backref(
            "task_associations",
            lazy="dynamic",
            cascade="all,delete-orphan"
        )
    )
    task = db.relationship(
        "WorkflowTask",
        backref="workflow_associations"
    )


####################
# Triggers
####################
class WorkflowTrigger(BaseEditable):
    __tablename__ = "WorkflowTrigger"
    __bind_key__ = "cetadash_db"
    endpoint = db.Column(db.String(200), nullable=False)
    headers = db.Column(db.Text, default=DEFAULT_HEADER_MAPPING)
    environment = db.Column(db.Text, default="")
    workflow_id = db.Column(
        db.Integer,
        db.ForeignKey("Workflow.id", ondelete="SET NULL"),
        nullable=True
    )
    workflow = db.relationship(
        "Workflow", 
        backref=backref(
            "triggers",
            # Don't cascade delete triggers when workflow is deleted
            cascade="save-update, merge, refresh-expire, expunge"
        )
    )
    enabled = db.Column(db.Boolean, default=True)

    def log_edit(self, user_id: int, action: int = ACTION_ENUM.MODIFY, **kw):
        return super().log_edit(
            WorkflowTriggerEditLog,
            user_id,
            action=action,
            trigger_id=self.id,
            **kw
        )
    
    def log_run(self, user_id: int, status: int = STATUS_ENUM.RUNNING, **kw):
        return super().log_run(
            WorkflowTriggerRunLog,
            user_id, status=status,
            trigger_id=self.id,
            **kw
        )


class WorkflowTriggerEditLog(BaseEditLog):
    __tablename__ = "WorkflowTriggerEditLog"
    __bind_key__ = "cetadash_db"
    trigger_id = db.Column(
        db.Integer,
        db.ForeignKey('WorkflowTrigger.id', ondelete='CASCADE'),
        nullable=False
    )
    trigger = db.relationship(
        "WorkflowTrigger",
        foreign_keys=[trigger_id],
        backref=backref(
            "edit_logs",
            order_by="WorkflowTriggerEditLog.id.desc()",
            cascade="all, delete-orphan"
        )
    )


class WorkflowTriggerRunLog(BaseActionLog):
    __tablename__ = "WorkflowTriggerRunLog"
    __bind_key__ = "cetadash_db"
    trigger_id = db.Column(
        db.Integer,
        db.ForeignKey('WorkflowTrigger.id', ondelete='CASCADE'),
        nullable=False
    )
    trigger = db.relationship(
        "WorkflowTrigger",
        foreign_keys=[trigger_id],
        backref=backref(
            "run_logs",
            order_by="WorkflowTriggerRunLog.id.desc()",
            cascade="all, delete-orphan"
        )
    )

    @property
    def workflow_log(self):
        return WorkflowRunLog.query.filter_by(
            trigger_log_id=self.id
        ).first()


####################
# Scheduled Triggers
####################
class ScheduleTrigger(BaseEditable):
    __tablename__ = "ScheduleTrigger"
    __bind_key__ = "cetadash_db"
    headers = db.Column(db.Text, default=DEFAULT_HEADER_MAPPING)
    environment = db.Column(db.Text, default="")
    workflow_id = db.Column(
        db.Integer, 
        db.ForeignKey("Workflow.id", ondelete="SET NULL"), 
        nullable=True
    )
    workflow = db.relationship(
        "Workflow", 
        backref=backref(
            "workflow_schedules",
            # Don't cascade delete schedules when workflow is deleted
            cascade="save-update, merge, refresh-expire, expunge"
        )
    )

    job_type = db.Column(db.String(50), nullable=False)  # "interval", "cron"

    # For cron jobs
    day_of_week = db.Column(db.String(20), nullable=True)
    hour = db.Column(db.Integer, nullable=True)
    minute = db.Column(db.Integer, nullable=True)

    # For interval jobs
    seconds = db.Column(db.Integer, nullable=True)
    minutes = db.Column(db.Integer, nullable=True)
    hours = db.Column(db.Integer, nullable=True)

    enabled = db.Column(db.Boolean, default=True)

    def log_edit(self,
        user_id: int,
        action: int = ACTION_ENUM.MODIFY,
        **kw
    ):
        return super().log_edit(
            ScheduleTriggerEditLog,
            user_id,
            action=action,
            schedule_trigger_id=self.id,
            **kw
        )
    
    def log_run(self,
        status: int = STATUS_ENUM.RUNNING,
        **kw
    ):
        return super().log_run(
            ScheduleTriggerRunLog,
            SYSTEM_ID,
            status=status,
            schedule_trigger_id=self.id,
            **kw
        )
    
    @property
    def schedule_string(self) -> str:
        """Returns a human-readable string representation of the schedule configuration."""
        if self.job_type == "cron":
            parts = []
            
            if self.day_of_week:
                if self.day_of_week == "*":
                    parts.append("every day")
                else:
                    days = self.day_of_week.replace(",", ", ")
                    parts.append(f"on {days}")
            
            if self.hour is not None and self.minute is not None:
                time_str = f"{self.hour:02d}:{self.minute:02d}"
                parts.append(f"at {time_str}")
            elif self.hour is not None:
                parts.append(f"at {self.hour:02d}:00")
            elif self.minute is not None:
                parts.append(f"at minute {self.minute}")
            
            return " ".join(parts) if parts else "cron schedule"
        
        elif self.job_type == "interval":
            parts = []
            
            if self.hours:
                parts.append(f"{self.hours} hour{'s' if self.hours != 1 else ''}")
            if self.minutes:
                parts.append(f"{self.minutes} minute{'s' if self.minutes != 1 else ''}")
            if self.seconds:
                parts.append(f"{self.seconds} second{'s' if self.seconds != 1 else ''}")
            
            if parts:
                return f"every {', '.join(parts)}"
            else:
                return "interval schedule"
        
        return f"{self.job_type} schedule"
    

class ScheduleTriggerEditLog(BaseEditLog):
    __tablename__ = "ScheduleTriggerEditLog"
    __bind_key__ = "cetadash_db"
    schedule_trigger_id = db.Column(
        db.Integer,
        db.ForeignKey('ScheduleTrigger.id', ondelete='CASCADE'),
        nullable=False
    )
    schedule_trigger = db.relationship(
        "ScheduleTrigger",
        foreign_keys=[schedule_trigger_id],
        backref=backref(
            "edit_logs",
            order_by="ScheduleTriggerEditLog.id.desc()",
            cascade="all, delete-orphan"
        )
    )


class ScheduleTriggerRunLog(BaseActionLog):
    __tablename__ = "ScheduleTriggerRunLog"
    __bind_key__ = "cetadash_db"
    schedule_trigger_id = db.Column(
        db.Integer,
        db.ForeignKey('ScheduleTrigger.id', ondelete='CASCADE'),
        nullable=False
    )
    schedule_trigger = db.relationship(
        "ScheduleTrigger",
        foreign_keys=[schedule_trigger_id],
        backref=backref(
            "run_logs",
            order_by="ScheduleTriggerRunLog.id.desc()",
            cascade="all, delete-orphan"
        )
    )

    @property
    def workflow_log(self):
        return WorkflowScheduledRunLog.query.filter_by(schedule_trigger_log_id=self.id).first()


####################
# CONTAINERIZED SCRIPTS
####################
class WorkflowScript(BaseEditable):
    __tablename__ = "WorkflowScript"
    __bind_key__ = "cetadash_db"
    environment = db.Column(db.Text, default="")
    script = db.Column(db.Text, default="")
    dependencies = db.Column(db.Text, default="")
    network_enabled = db.Column(db.Boolean, default=True)
    language = db.Column(db.Text, default="python")
   
    def log_edit(
        self,
        user_id: int,
        action: int = ACTION_ENUM.MODIFY,
        **kw
    ):
        return super().log_edit(
            WorkflowScriptEditLog,
            user_id,
            action=action,
            script_id=self.id,
            **kw
        )

    def log_run(
        self,
        user_id:int,
        task_log_id:int,
        status:int = STATUS_ENUM.RUNNING
    ):
        return super().log_run(
            WorkflowScriptRunLog,
            user_id,
            status=status,
            script_id=self.id,
            task_log_id=task_log_id
        )
    
    def log_scheduled_run(
        self,
        task_log_id:int,
        status:int = STATUS_ENUM.RUNNING
    ):
        return super().log_run(
            WorkflowScriptScheduledRunLog,
            SYSTEM_ID,
            status=status,
            script_id=self.id,
            task_log_id=task_log_id
        )


class WorkflowScriptEditLog(BaseEditLog):
    __tablename__ = "WorkflowScriptEditLog"
    __bind_key__ = "cetadash_db"
    script_id = db.Column(
        db.Integer,
        db.ForeignKey('WorkflowScript.id', ondelete='CASCADE'),
        nullable=False
    )
    script = db.relationship(
        "WorkflowScript",
        foreign_keys=[script_id],
        backref=backref(
            "edit_logs",
            order_by="WorkflowScriptEditLog.id.desc()",
            cascade="all, delete-orphan"
        )
    )


class WorkflowScriptRunLog(BaseActionLog):
    __tablename__ = "WorkflowScriptRunLog"
    __bind_key__ = "cetadash_db"
    script_id = db.Column(
        db.Integer,
        db.ForeignKey('WorkflowScript.id', ondelete='CASCADE'),
        nullable=False
    )
    script = db.relationship(
        "WorkflowScript",
        foreign_keys=[script_id], 
        backref=backref(
            "run_logs",
            order_by="WorkflowScriptRunLog.id.desc()",
            cascade="all, delete-orphan"
        )
    )
    task_log_id = db.Column(
        db.Integer,
        db.ForeignKey('WorkflowTaskRunLog.id', ondelete='CASCADE'),
        unique=True,
        nullable=False
    )
    task_log = db.relationship(
        "WorkflowTaskRunLog",
        foreign_keys=[task_log_id],
        backref=backref(
            "script_run_log",
            uselist=False,
            cascade="all, delete-orphan"
        )
    )


class WorkflowScriptScheduledRunLog(BaseActionLog):
    __tablename__ = "WorkflowScriptScheduledRunLog"
    __bind_key__ = "cetadash_db"

    script_id = db.Column(
        db.Integer,
        db.ForeignKey('WorkflowScript.id', ondelete='CASCADE'),
        nullable=False
    )
    script = db.relationship(
        "WorkflowScript",
        foreign_keys=[script_id],
        backref=backref(
            "scheduled_run_logs",
            order_by="WorkflowScriptScheduledRunLog.id.desc()",
            cascade="all, delete-orphan"
        )
    )

    task_log_id = db.Column(
        db.Integer,
        db.ForeignKey('WorkflowTaskScheduledRunLog.id', ondelete='CASCADE'),
        unique=True,
        nullable=False
    )
    task_log = db.relationship(
        "WorkflowTaskScheduledRunLog",
        foreign_keys=[task_log_id],
        backref=backref(
            "script_scheduled_run_log",
            uselist=False,
            cascade="all, delete-orphan"
        )
    )


test_data = {

    "scripts": [
        {
            "name" : "Hello World Script",
            "description" : "Containerizes a \"Hello World\" Python Script",
            "network_enabled" : False,
            "language" : "python",
            "script" : """# Hello World Example Docker File
import time
if __name__ == "__main__":
    print("Hello World!")
    for i in range(100):
        print(f"Hello World - {i}")
        time.sleep(0.01)
""",
        }
    ],



    "tasks" : [
        {
            "name" : "Hello World 1 (Container)",
            "template" : """
networks:
    traefik_network:
        driver: bridge
        name: traefik_network
        external: true

services:
    hello-{{username}}-{{session_id}}:
        container_name: hello-{{username}}-{{session_id}}
        hostname: hello-{{username}}-{{session_id}}
        image: hello-world
        networks:
            traefik_network: {}
        environment:
            - TZ=$TZ
            """,
            "environment" : """
TZ=America/Los_Angeles
            """,
            "description" : "Step 1 of Example Workflow",
            "details" : """""",
        },

        {
            "name" : "Hello World 2 (Script)",
            "description" : "Step 2 of Example Workflow",
            "details" : """""",
            "script_id" : 0,
        },

    ],


    "workflows" : [
        {
            "name" : "Hello World Workflow",
            "description": "Runs 3 Hello World Tasks in sequence",
            "details": "",
        }
    ],


    "triggers" : [
        {
            "name" : "Hello World Trigger",
            "description" : "Triggers the Hello World workflow",
            "endpoint" : "hello",
            "details" : "",
            "headers" : """
mappings:
    Remote-User:
        value: username
        nullable: false
    Remote-Groups:
        value: groups
""",
        }
    ],


    "schedule_triggers" : [
        {
            "name" : "Hello World Schedule Trigger",
            "description" : "Triggers the Hello World workflow",
            "endpoint" : "hello",
            "details" : "",
            "headers" : """
mappings:
    Remote-User:
        value: username
        nullable: false
    Remote-Groups:
        value: groups
""",
        }
    ],

}

def init_db(app):
    with app.app_context():
        logging.info("Initializing Docker Plugin db")
        db.create_all(bind_key=["cetadash_db"])

        app.models.docker = ImmutableDict()
        for obj in (
            ACTION_ENUM,
            STATUS_ENUM,
            WorkflowScript,
            WorkflowScriptEditLog,
            WorkflowScriptRunLog,
            WorkflowScriptScheduledRunLog,
            WorkflowTask,
            WorkflowTaskEditLog,
            WorkflowTaskRunLog,
            WorkflowTaskScheduledRunLog,
            Workflow,
            WorkflowEditLog,
            WorkflowRunLog,
            WorkflowScheduledRunLog,
            WorkflowTaskAssociation,
            WorkflowTrigger,
            WorkflowTriggerEditLog,
            WorkflowTriggerRunLog,
            ScheduleTrigger,
            ScheduleTriggerEditLog,
            ScheduleTriggerRunLog
        ):
            setattr(app.models.docker, obj.__name__, obj)

        if WorkflowTask.query.first() is None:
            logging.info("Populating initial Docker Plugin data")
            
            # Create scripts
            scripts = []
            for script_data in test_data["scripts"]:
                script = WorkflowScript(
                    name=script_data["name"],
                    description=script_data["description"],
                    language=script_data.get("language", "python"),
                    network_enabled=script_data.get("network_enabled", True),
                    script=script_data["script"],
                    creator_id=1,
                    last_editor_id=1
                )
                db.session.add(script)
                scripts.append(script)
            db.session.commit()

            # Create tasks
            tasks = []
            for task_data in test_data["tasks"]:
                task = WorkflowTask(
                    name=task_data["name"],
                    template=task_data.get("template"),
                    environment=task_data.get("environment"),
                    description=task_data["description"],
                    details=task_data.get("details", ""),
                    creator_id=1,
                    last_editor_id=1
                )

                # Link scripts
                script_index = task_data.get("script_id")
                if script_index is not None and 0 <= script_index < len(scripts):
                    task.use_script = True
                    task.script_id = scripts[script_index].id

                db.session.add(task)
                tasks.append(task)
            db.session.commit()


            wf_data = test_data["workflows"][0]
            workflow = Workflow(
                name=wf_data["name"],
                description=wf_data["description"],
                details=wf_data["details"],
                creator_id=1,
                last_editor_id=1
            )
            db.session.add(workflow)
            db.session.commit()

            for i, task in enumerate(tasks):
                assoc = WorkflowTaskAssociation(
                    workflow_id=workflow.id,
                    task_id=task.id,
                    priority=i,
                )
                db.session.add(assoc)

            db.session.commit()

            trig_data = test_data["triggers"][0]
            trigger = WorkflowTrigger(
                name=trig_data["name"],
                endpoint=trig_data["endpoint"],
                description=trig_data["description"],
                details=trig_data["details"],
                headers=trig_data["headers"],
                workflow_id=workflow.id,
                creator_id=1,
                last_editor_id=1,
            )
            db.session.add(trigger)
            db.session.commit()

    app.docker_scheduler.load_all_triggers()