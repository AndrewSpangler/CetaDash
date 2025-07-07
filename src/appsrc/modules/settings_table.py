import json
from ..main import db

def decode_bool(val:str) -> bool:
    if (val := val.lower()) in ("true", "false"):
        return str(int(str(val) == "true"))
    return bool(int(val))   
def decode_int(val:str) -> int: return int(val)
def decode_float(val:str) -> float: return float(val)
def decode_dict(val:str) -> dict: return json.loads(val)
def encode_bool(val:bool) -> str: return str(int(bool(val)))
def encode_dict(val:dict) -> str: return json.dumps(val)
def passthrough(val:object) -> object: return val

ENCODER_MAP = {
    "bool": encode_bool,
    "int": str,
    "float": str,
    "string": passthrough,
    "dict": encode_dict,
}

DECODER_MAP = {
    "bool": decode_bool,
    "int": decode_int,
    "float": decode_float,
    "string": passthrough,
    "dict": decode_dict,
}

class BaseSettingsTable(db.Model):
    __abstract__ = True
    key = db.Column(db.Text, primary_key=True)
    value = db.Column(db.Text)
    data_type = db.Column(db.Text, nullable=False)
    @classmethod
    def get_setting(cls, key:str) -> object:
        """Loads a setting from the table"""
        if not (setting := cls.query.get(key)):
            raise ValueError(f"Key - {key} does not exist in {cls.__tablename__}")
        return DECODER_MAP[setting.data_type](setting.value)
    @classmethod
    def get_settings(cls) -> dict[str:object]:
        """Loads all settings from table as a dict"""
        settings = cls.query.all()
        loaded = {
            s.key: DECODER_MAP[s.data_type](s.value)
            for s in settings
        }
        return loaded
    @classmethod
    def set_setting(
        cls:type,
        key:str,
        val:str|object="",
        data_type:str="string",
        update_type:bool=False
    ) -> object:
        """Updates or creates a setting in the table"""
        if (setting := cls.query.get(key)):
            if data_type and update_type:
                setting.data_type = data_type
            else:
                data_type = setting.data_type
            setting.value = ENCODER_MAP[data_type](val)
        else:
            setting = cls(key=key, value=ENCODER_MAP[data_type](val), data_type=data_type)
            cls.session.add(setting)
        db.session.commit()