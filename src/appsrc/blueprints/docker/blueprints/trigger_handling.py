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
    WorkflowTask,
    WorkflowTaskAssociation,
    Workflow,
    WorkflowTrigger,
    ScheduleTrigger,
    ACTION_ENUM,
    STATUS_ENUM
)

os.makedirs("/cetadash-compose", exist_ok=True)

class TemplateRenderer:
    def __init__(self, template_str: str, defaults: dict = None):
        self._render = Environment(loader=BaseLoader()).from_string(template_str).render
        self.defaults = defaults or {}

    def render(self, **kw) -> str:
        context = {**self.defaults, **kw}
        return self._render(**context).replace("\t", "  ")


def get_unique_session():
    return secrets.token_urlsafe(32)


def parse_jinja_variables(headers: str) -> dict:
    data = yaml.safe_load(headers)
    return data


def get_trigger_heading_map(headers:str) -> dict:
    data = yaml.safe_load(headers)
    if not "mappings" in data:
        raise ValueError("Trigger values must contain 'mappings' section")
    values = data["mappings"]
    return values


def translate_headers(request_headers:dict, headers_mapping:dict)->dict:
    mapping = {}
    errors = []
    for k, typ in headers_mapping.items():
        req_val = request_headers.get(k, None)
        if req_val is None and not typ.get("nullable"):
            errors.append(f"Missing required header - {k}")
            continue
        mapping.update({typ['value'] : request_headers.get(k, "")})
    if len(errors):
        errors = "\n\t-".join(errors)
        raise ValueError(f"Encountered error(s) while parsing headers - {errors}")
    return mapping


def handle_trigger(user_id, trigger, request_headers, workflow, tasks, result_queue, cleanup=True):
    session_id = get_unique_session()
    session_path = f"/cetadash-compose/{session_id}"
    os.makedirs(session_path)

    with app.app_context():
        trigger_log = trigger.log_run(user_id)
        db.session.add(trigger_log)
        db.session.commit()
        if isinstance(trigger, WorkflowTrigger):
            workflow_log = workflow.log_run(user_id, trigger_log_id=trigger_log.id)
        else:
            workflow_log = workflow.log_scheduled_run(schedule_trigger_log_id=trigger_log.id)
        db.session.add(workflow_log)
        db.session.commit()
        workflow_log_id = workflow_log.id

    def commit_logs(extra:list=[]):
        with app.app_context():
            db.session.merge(workflow_log)
            db.session.merge(trigger_log)
            for l in extra:
                db.session.merge(l)
            db.session.commit()

    if isinstance(trigger, WorkflowTrigger):
        result_queue.put_nowait("🖥️📖 Parsing variable map from trigger header translation")
        try:
            headers_map = get_trigger_heading_map(trigger.headers)
        except Exception as e:
            result_queue.put_nowait(f"🖥️❌ Error parsing variable map - {e}")
            trigger_log.status = STATUS_ENUM.HEADERS
            workflow_log.status = STATUS_ENUM.HEADERS
            commit_logs()
            raise e
        result_queue.put_nowait("🖥️📖 Translating headers")
        try:
            trigger_variables = translate_headers(request_headers, headers_map)
        except Exception as e:
            result_queue.put_nowait(f"🖥️❌ Error translating headers - {e}")
            trigger_log.status = STATUS_ENUM.HEADERS
            workflow_log.status = STATUS_ENUM.HEADERS
            commit_logs()
            raise e

    elif isinstance(trigger, ScheduleTrigger):
        result_queue.put_nowait("🖥️📖 Parsing variable supply from trigger")
        try:
            trigger_variables = parse_jinja_variables(trigger.headers)
        except Exception as e:
            result_queue.put_nowait(f"🖥️❌ Error parsing variable map - {e}")
            trigger_log.status = STATUS_ENUM.HEADERS
            workflow_log.status = STATUS_ENUM.HEADERS
            commit_logs()
            raise e

    try:
        for task in tasks:
            
            with app.app_context():
                if isinstance(trigger, WorkflowTrigger):
                    task_log = task.log_run(user_id, workflow_log_id=workflow_log_id)
                elif isinstance(trigger, ScheduleTrigger):
                    task_log = task.log_scheduled_run(workflow_log_id=workflow_log_id)
                db.session.add(task_log)
                db.session.commit()
            result_queue.put_nowait("\n"*4)
            result_queue.put_nowait("="*40)
            result_queue.put_nowait(f"🖥️✅ Handling task {task} - {session_id}")
            
            success = True
            message = ""
            try:
                handle_task(trigger, trigger_variables, task, session_id, result_queue, cleanup=cleanup)
                task_log.status = STATUS_ENUM.SUCCESS
            except Exception as e:
                task_log.status = STATUS_ENUM.FAILURE
                success = False
                message = e
            finally:
                commit_logs([task_log])
            if not success:
                raise ValueError(f"Task failed - {message}")
            result_queue.put_nowait(f"🖥️✅ Finished task {task} - {session_id}")
            
    except Exception as e:
        trigger_log.status = STATUS_ENUM.TASK
        commit_logs()
        result_queue.put_nowait(f"🖥️❌ Error during workflow task handling - {e}")

    if cleanup:
        result_queue.put_nowait("🖥️🧹 Cleaning up compose dir...")
        threading.Thread(
            target=lambda: shutil.rmtree(session_path),
            daemon=True
        ).start()

    workflow_log.status = STATUS_ENUM.SUCCESS
    trigger_log.status = STATUS_ENUM.SUCCESS
    commit_logs()

    result_queue.put_nowait(f"🖥️✅ Trigger {trigger.name} - session {session_id} completed. Disconnecting...")
    result_queue.put_nowait("="*40)
    result_queue.put_nowait("\n"*4)
    result_queue.put_nowait("__COMPLETE__")


def up_compose(session, path, result_queue, cleanup=True):
    def queue_std(pipe, tag):
        for line in iter(pipe.readline, ''):
            result_queue.put_nowait(tag + line.strip())
        pipe.close()
    # Start container
    process = subprocess.Popen(
        ["docker", "compose", "-f", path, "up", "-d"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1
    )
    stdout_thread = threading.Thread(target=queue_std, args=(process.stdout, f"🐳⚙️ stdout: "))
    stderr_thread = threading.Thread(target=queue_std, args=(process.stderr, f"🐳🛈 stderr: "))
    stdout_thread.start()
    stderr_thread.start()
    process.wait()
    stdout_thread.join()
    stderr_thread.join()
 
    with open(path, 'r') as f:
        conf = yaml.safe_load(f)

    client = docker.from_env()
    container_names = [k for k,v in conf["services"].items()]
    result_queue.put_nowait(f"🖥️🔗 Fetching containers {container_names}")
    containers = [client.containers.get(c) for c in container_names]
    def queue_container(cont):
        try:
            result_queue.put_nowait(f"🖥️⛓️ Attaching to logs for {cont.name}.")
            for log in cont.logs(stream=True, follow=True, tail=1000):
                result_queue.put_nowait(f"🐳🧾 [{cont.name}]: " + log.decode('utf-8'))
        except Exception as e:
            result_queue.put_nowait(f"🖥️❌ Failed to attach to logs for {cont.name}: {e}")

    threads = []
    for c in containers:
        threads.append(threading.Thread(
            target=queue_container,
            args=(c, )
        ))
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    result_queue.put_nowait(f"🖥️✅ Compose run completed.")
    if cleanup:
        result_queue.put_nowait(f"🖥️🧹 Cleaning up containers...")
        for c in containers:
            result_queue.put_nowait(f"🐳🗑️ Removing container {c.name}")
            c.remove(force=True)
    

def handle_task(trigger, trigger_variables, task, session, result_queue, cleanup=True):
    template = task.template
    variables_map = trigger_variables.copy()
    variables_map.update({"session_id": session})

    result_queue.put_nowait("🖥️✏️ Rendering Template")
    renderer = TemplateRenderer(template, variables_map)
    rendered_template = renderer.render()  
    env = task.environment
    try:
        result_queue.put_nowait("🖥️📖 Loading compose file from task template")
        loaded_compose = yaml.safe_load(rendered_template)
    except Exception as e:
        result_queue.put_nowait(f"🖥️❌ Error loading template {loaded_compose}")
        raise
    compose_location = f"/cetadash-compose/{session}/{task.id}.yml"
    result_queue.put_nowait("🖥️💾 Writing compose file...")
    with open(compose_location, "w+") as f:
        yaml.dump(loaded_compose, f, default_flow_style=False, sort_keys=False)
    result_queue.put_nowait("🖥️💾 Writing env file...")
    env_location = f"/cetadash-compose/{session}/.env"
    with open(env_location, "w+") as f:
        f.write(env)
    result_queue.put_nowait("🖥️⬆️ Starting containers from compose file...")
    up_compose(session, compose_location, result_queue, cleanup=cleanup)