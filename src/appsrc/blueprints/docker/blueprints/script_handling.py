import os
import queue
import threading
import secrets
import docker
import yaml
import shutil
import subprocess
from jinja2 import Environment, BaseLoader
from ..models import (
    app,
    db,
    script,
    ACTION_ENUM,
    STATUS_ENUM
)
os.makedirs("/cetadash-compose/scripts", exist_ok=True)



def handle_script(user_id, script, result_queue, cleanup=True):
   

