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
    WorkflowTaskRunLog,
    WorkflowTaskScheduledRunLog,
    WorkflowRunLog,
    WorkflowScheduledRunLog,
    WorkflowTriggerRunLog,
    ScheduleTriggerRunLog,
    ACTION_ENUM,
    STATUS_ENUM
)
os.makedirs("/cetadash-compose", exist_ok=True)

def format_environment_string(env_dict: dict) -> str:
    """Convert environment dictionary back to string format"""
    return '\n'.join(f"{key}={value}" for key, value in env_dict.items())


def parse_environment_variables(env_string: str) -> dict:
    """Parse environment variables from a string into a dictionary"""
    if not env_string:
        return {}
    env_vars = {}
    for line in env_string.strip().split('\n'):
        line = line.strip()
        if line and '=' in line and not line.startswith('#'):
            key, value = line.split('=', 1)
            env_vars[key.strip()] = value.strip()
    return env_vars


def build_layered_environment(trigger, workflow, task):
    """Build environment variables with proper layering (trigger/schedule > workflow > task)"""
    layered_env = parse_environment_variables(getattr(task, 'environment', '') or '')
    
    if workflow.environment and workflow.environment.strip():
        workflow_env = parse_environment_variables(workflow.environment)
        layered_env.update(workflow_env)
    
    if trigger.environment and trigger.environment.strip():
        trigger_env = parse_environment_variables(trigger.environment)
        layered_env.update(trigger_env)
    
    return layered_env


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
        trigger_log = trigger.log_run(user_id, message="")
        db.session.add(trigger_log)
        db.session.commit()
        if isinstance(trigger, WorkflowTrigger):
            workflow_log = workflow.log_run(user_id, trigger_log_id=trigger_log.id, message="")
        else:
            workflow_log = workflow.log_scheduled_run(schedule_trigger_log_id=trigger_log.id, message="")
        db.session.add(workflow_log)
        db.session.commit()
        workflow_log_id = workflow_log.id

        if isinstance(trigger, WorkflowTrigger):
            workflow_log = WorkflowRunLog.query.get(workflow_log.id)
            trigger_log = WorkflowTriggerRunLog.query.get(trigger_log.id)
        else:
            workflow_log = WorkflowScheduledRunLog.query.get(workflow_log.id)
            trigger_log = ScheduleTriggerRunLog.query.get(trigger_log.id)
            
        db.session.expunge(workflow_log)
        db.session.expunge(trigger_log)

    def commit_logs(extra:list=[]):
        with app.app_context():
            db.session.merge(workflow_log)
            db.session.merge(trigger_log)
            for l in extra:
                db.session.merge(l)
            db.session.commit()
    
    def write_queue(msg):
        result_queue.put_nowait(msg.replace("\n", "\n\n"))

    def write_workflow_log(msg):
        write_queue(msg)
        with app.app_context():
            db.session.merge(workflow_log)
            workflow_log.message += msg + "\n"
            db.session.commit()

    def write_trigger_log(msg):
        write_queue(msg)
        with app.app_context():
            db.session.merge(trigger_log)
            trigger_log.message += msg + "\n"
            db.session.commit()

    def write_both_logs(msg):
        write_queue(msg)
        with app.app_context():
            db.session.merge(workflow_log)
            db.session.merge(trigger_log)
            msg = msg + "\n"
            workflow_log.message += msg
            trigger_log.message += msg
            db.session.commit()

    if isinstance(trigger, WorkflowTrigger):
        write_trigger_log("\n🖥️📖 Parsing variable map from trigger header translation")
        try:
            headers_map = get_trigger_heading_map(trigger.headers)
        except Exception as e:
            trigger_log.status = STATUS_ENUM.HEADERS
            workflow_log.status = STATUS_ENUM.HEADERS
            write_trigger_log(f"🖥️❌ Error parsing variable map - {e}")
            commit_logs()
            raise e
        write_trigger_log("🖥️📖 Translating headers")
        try:
            trigger_variables = translate_headers(request_headers, headers_map)
        except Exception as e:
            trigger_log.status = STATUS_ENUM.HEADERS
            workflow_log.status = STATUS_ENUM.HEADERS
            write_trigger_log(f"🖥️❌ Error translating headers - {e}")
            commit_logs()
            raise e

    elif isinstance(trigger, ScheduleTrigger):
        write_trigger_log("\n🖥️📖 Parsing variable supply from trigger")
        try:
            trigger_variables = parse_jinja_variables(trigger.headers)
        except Exception as e:
            trigger_log.status = STATUS_ENUM.HEADERS
            workflow_log.status = STATUS_ENUM.HEADERS
            write_trigger_log(f"🖥️❌ Error parsing variable map - {e}")
            commit_logs()
            raise e

    try:
        for task in tasks:
            
            with app.app_context():
                if isinstance(trigger, WorkflowTrigger):
                    task_log = task.log_run(user_id, workflow_log_id=workflow_log_id)
                elif isinstance(trigger, ScheduleTrigger):
                    task_log = task.log_scheduled_run(workflow_log_id=workflow_log_id)
                task_log.message = ""
                db.session.add(task_log)
                db.session.commit()
                if isinstance(trigger, WorkflowTrigger):
                    task_log = WorkflowTaskRunLog.query.get(task_log.id)
                elif isinstance(trigger, ScheduleTrigger):
                    task_log = WorkflowTaskScheduledRunLog.query.get(task_log.id)
                db.session.expunge(task_log)

            write_queue("\n"*2)
            write_workflow_log("="*40)
            write_workflow_log(f"🖥️✅ Handling task {task} - {session_id}")
            
            success = True
            message = ""
            try:
                handle_task(
                    trigger,
                    trigger_variables,
                    workflow,
                    task,
                    session_id,
                    result_queue,
                    task_log,
                    cleanup=cleanup
                )
                task_log.status = STATUS_ENUM.SUCCESS
            except Exception as e:
                task_log.status = STATUS_ENUM.FAILURE
                success = False
                message = e
            finally:
                commit_logs([task_log])
            if not success:
                raise ValueError(f"Task failed - {message}")
            write_workflow_log(f"🖥️✅ Finished task {task} - {session_id}")
            
    except Exception as e:
        trigger_log.status = STATUS_ENUM.TASK
        write_both_logs(f"🖥️❌ Error during workflow task handling - {e}")
        commit_logs()

    if cleanup:
        write_workflow_log("🖥️🧹 Cleaning up compose dir...")
        threading.Thread(
            target=lambda: shutil.rmtree(session_path),
            daemon=True
        ).start()

    workflow_log.status = STATUS_ENUM.SUCCESS
    trigger_log.status = STATUS_ENUM.SUCCESS
    
    write_both_logs("="*40)
    write_trigger_log(f"🖥️✅ Trigger {trigger.name} - session {session_id} completed. Disconnecting...")
    write_workflow_log(f"🖥️✅ Workflow {workflow.name} - session {session_id} completed")
    write_queue("\n"*2)
    write_queue("__COMPLETE__")
    commit_logs()


def up_compose(session, path, result_queue, task_log, cleanup=True):
    def write_log(msg):
        with app.app_context():
            db.session.merge(task_log)
            task_log.message += msg+"\n"
            db.session.commit()
        result_queue.put_nowait(msg)

    def queue_std(pipe, tag):
        for line in iter(pipe.readline, ''):
            msg = tag + line.strip()
            write_log(msg)
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
    write_log(f"🖥️🔗 Fetching containers {container_names}")
    containers = [client.containers.get(c) for c in container_names]
    def queue_container(cont):
        try:
            write_log(f"🖥️⛓️ Attaching to logs for {cont.name}.")
            for log in cont.logs(stream=True, follow=True, tail=1000):
                write_log((f"🐳🧾 [{cont.name}]: " + log.decode('utf-8')).strip())
        except Exception as e:
            write_log(f"🖥️❌ Failed to attach to logs for {cont.name}: {e}")

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
    write_log(f"🖥️✅ Compose run completed.")
    if cleanup:
        write_log(f"🖥️🧹 Cleaning up containers...")
        for c in containers:
            write_log(f"🐳🗑️ Removing container {c.name}")
            c.remove(force=True)
    

def handle_task(
    trigger,
    trigger_variables,
    workflow,
    task,
    session,
    result_queue,
    task_log,
    cleanup=True
):
    def write_log(msg):
        with app.app_context():
            db.session.merge(task_log)
            task_log.message += msg+"\n"
            db.session.commit()
        result_queue.put_nowait(msg)

    template = task.template
    variables_map = trigger_variables.copy()
    variables_map.update({"session_id": session})
    write_log("🖥️🌐 Building layered environment (trigger > workflow > task)")

    layered_env = build_layered_environment(trigger, workflow, task)
    layered_env_string = format_environment_string(layered_env)
    write_log(f"🖥️📊 Environment layers applied: {len(layered_env)} variables total")
    if layered_env:
        write_log(f"🖥️🔧 Environment variables: {', '.join(layered_env.keys())}")

    write_log("🖥️✏️ Rendering Template")
    renderer = TemplateRenderer(template, variables_map)
    rendered_template = renderer.render()  
    env = task.environment

    try:
        write_log("🖥️📖 Loading compose file from task template")
        loaded_compose = yaml.safe_load(rendered_template)
        
    except Exception as e:
        write_log(f"🖥️❌ Error loading template {rendered_template}")
        raise
    compose_location = f"/cetadash-compose/{session}/{task.id}.yml"
    write_log("🖥️💾 Writing compose file...")
    with open(compose_location, "w+") as f:
        yaml.dump(loaded_compose, f, default_flow_style=False, sort_keys=False)
    write_log("🖥️💾 Writing layered env file...")
    env_location = f"/cetadash-compose/{session}/.env"
    with open(env_location, "w+") as f:
        f.write(layered_env_string)
    write_log("🖥️⬆️ Starting containers from compose file...")
    up_compose(
        session,
        compose_location,
        result_queue,
        task_log,
        cleanup=cleanup
    )