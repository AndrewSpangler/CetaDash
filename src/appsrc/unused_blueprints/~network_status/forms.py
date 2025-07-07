from wtforms import SubmitField, IntegerField, BooleanField, StringField
from wtforms.validators import DataRequired, Length, NumberRange
from flask_wtf import FlaskForm

class NewRangeForm(FlaskForm):
    """
    Form to add a new scanner ip range
    """
    name = StringField("Name", validators=[DataRequired()])
    address = StringField(
        "IP Address",
        validators = [
            DataRequired(),
            Length(min=7, max=15)
        ]
    )
    submit = SubmitField('Add New Range')

class ScanFrequencyForm(FlaskForm):
    enable_scan = BooleanField("Enable Background Scan?", validators=[])
    update_frequency = IntegerField("Scan Frequency (Minutes, Min 5)", validators=[NumberRange(min=5), DataRequired()])
    submit = SubmitField('Update Scan Frequency')
