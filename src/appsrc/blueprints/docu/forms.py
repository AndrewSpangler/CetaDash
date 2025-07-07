from flask_wtf import FlaskForm
from wtforms import StringField, TextAreaField, SubmitField
from wtforms.validators import DataRequired, Length


class DocumentForm(FlaskForm):
    name = StringField('Title', validators=[DataRequired(), Length(min=1, max=100)])
    content = TextAreaField('Content', validators=[])
    description = StringField('Description', validators=[Length(min=0, max=256)])
    details = TextAreaField('Details (MD + HTML)')
    submit = SubmitField('Save Document')