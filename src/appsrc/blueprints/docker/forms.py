from flask_wtf import FlaskForm
from wtforms import (
    StringField,
    TextAreaField,
    SelectField,
    SubmitField,
    BooleanField,
    FieldList,
    IntegerField,
    SelectField,
    HiddenField
)
from wtforms.validators import DataRequired, Length, Optional, NumberRange
from wtforms_sqlalchemy.fields import QuerySelectField
from .models import Workflow, ScheduleTrigger


def query_workflows():
    return Workflow.query.all


class EditWorkflowForm(FlaskForm):
    name = StringField('Name', validators=[Length(min=3, max=100)])
    tasks = FieldList(
        StringField("Task ID"),
        min_entries=0,
        label='Task Order',
        render_kw={'readonly': True}
    )
    details = TextAreaField('Details (MD)')
    description = StringField('Description ', validators=[Length(min=0, max=256)])
    submit = SubmitField('Save Workflow')


class EditWorkflowTaskForm(FlaskForm):
    name = StringField('Name', validators=[DataRequired(), Length(min=3, max=100)])
    description = StringField('Description ', validators=[Length(min=0, max=256)])
    details = TextAreaField('Details (MD + HTML)')
    template = TextAreaField('Template (YAML + JINJA)')
    environment = TextAreaField('Environment Variables (ENV)')
    submit = SubmitField('Save Changes')


class TriggerForm(FlaskForm):
    name = StringField('Name', validators=[DataRequired(), Length(min=1, max=100)])
    description = TextAreaField('Description ', validators=[Length(min=0, max=256)])
    endpoint = StringField('Endpoint', validators=[DataRequired(), Length(min=1, max=256)])
    details = TextAreaField('Details (MD + HTML)')
    headers = TextAreaField('Proxy Headers Translation (YAML)')
    environment = TextAreaField("Environment Variables (ENV)", validators=[Optional()])
    workflow_id = SelectField("Workflow", coerce=int)
    submit = SubmitField('Save Workflow Trigger')


class ScheduleTriggerForm(FlaskForm):
    name = StringField("Name", validators=[DataRequired()])
    description = TextAreaField("Description ", validators=[Optional()])
    details = TextAreaField("Details", validators=[Optional()])
    headers = TextAreaField("Jinja Variables (YAML)", validators=[Optional()])
    environment = TextAreaField("Environment Variables (ENV)", validators=[Optional()])
    enabled = BooleanField("Enabled", default=True)
    workflow = QuerySelectField("Workflow", query_factory=query_workflows, get_label="name", allow_blank=False)
    job_type = SelectField(
        "Job Type",
        choices=[("cron", "Cron (e.g. every Wednesday at 2 PM)"), ("interval", "Interval (e.g. every 15 minutes)")],
        validators=[DataRequired()]
    )
    # cron fields
    day_of_week = StringField("Day of Week", validators=[Optional()])  # e.g. 'mon,wed,fri'
    hour = IntegerField("Hour (0-23)", validators=[Optional(), NumberRange(min=0, max=23)])
    minute = IntegerField("Minute (0-59)", validators=[Optional(), NumberRange(min=0, max=59)])
    # interval fields
    seconds = IntegerField("Seconds", validators=[Optional(), NumberRange(min=0)])
    minutes = IntegerField("Minutes", validators=[Optional(), NumberRange(min=0)])
    hours = IntegerField("Hours", validators=[Optional(), NumberRange(min=0)])
    submit = SubmitField('Save Scheduled Trigger')