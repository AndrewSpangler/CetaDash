import os
import docker
import datetime
import threading
import queue
from flask import (
    Blueprint,
    Response,
    render_template,
    redirect,
    url_for,
    flash,
    stream_with_context
)
from flask_login import current_user
from ..models import (
    app,
    db,
    WorkflowTask,
    WorkflowTaskAssociation,
    Workflow,
    ACTION_ENUM,
    STATUS_ENUM
)
from ....modules.parsing import (
    make_table_button,
    make_table_icon_button,
    make_table_page
)



blueprint = Blueprint(
    'containers',
    __name__,
    static_folder=os.path.join(os.path.dirname(os.path.dirname(__file__)),"static"),
    template_folder=os.path.join(os.path.dirname(os.path.dirname(__file__)), "templates"),
)


def remove_container(container) -> str:
    container.remove(force=True)
    return "Container started succesfully."


def restart_container(container) -> str:
    container.restart()
    return "Container restarted succesfully."


def kill_container(container) -> str:
    container.kill()
    return "Container killed succesfully."


def stop_container(container) -> str:
    container.stop()
    return "Container stopped succesfully."

    
def start_container(container) -> str:
    container.start()
    return "Container started succesfully."


ACTION_MAP = {
    "start_container"   : start_container,
    "stop_container"    : stop_container,
    "kill_container"    : kill_container,
    "restart_container" : restart_container,
    "remove_container"  : remove_container,
}


def action_worker(action, container_id, result_queue) -> None:
    try:
        result_queue.put("🖥️🔗 Connecting to Docker engine")
        client = docker.from_env()
        result_queue.put(f"🖥️🔗 Fetching container {container_id}")
        container = client.containers.get(container_id)
    except docker.errors.DockerException as e:
        result_queue.put(f"🖥️❌ Failed to get container: {str(e)}")
        return

    try:
        result_queue.put(f"🖥️✅ Performing action '{action}' on container '{container.name}'")

        try:
            status = True
            message = ACTION_MAP[action](container)
        except Exception as e:
            status = False
            message = e

        if status:
            result_queue.put(f"🖥️✅ Action '{action}' completed successfully: {message}")
        else:
            result_queue.put(f"🖥️❌ Action '{action}' failed: {message}")
    except docker.errors.DockerException as e:
        result_queue.put(f"🖥️❌ Docker error during '{action}': {str(e)}")
        return

    if status and action in ["start_container", "restart_container"]:
        result_queue.put(f"🖥️🔗 Attaching to logs for container '{container.name}'")
        try:
            for log in container.logs(stream=True, follow=True, tail=1000):
                result_queue.put(f"🐳🧾 {log.decode('utf-8')}")
        except Exception as e:
            result_queue.put(f"🖥️❌ Failed to attach to logs: {str(e)}")

    result_queue.put("🖥️✅ TASK COMPLETE, DISCONNECTING\n")


@blueprint.route('/')
@app.permission_required(app.models.core.PERMISSION_ENUM.ADMIN)
def index():
    client = docker.APIClient()
    containers = client.containers(all=True)
    container_actions = {
        "start_container":("Start", "play"),
        "stop_container":("Stop", "stop"),
        "kill_container":("Kill", "ban"),
        "restart_container":("Restart", "arrow-clockwise"),
        "remove_container":("Remove", "trash"),        
    }
    page = make_table_page(
        "dockercontainers",
        title = "Docker Containers",
        columns = [
            "Name",
            "Image",
            "State",
            "Created",
        ],
        rows = [
            (
                f"<b><a href='{url_for('docker.containers.view', container_id=container['Id'])}'>"+container["Names"][0].strip("/")+"</a></b>"
                + "<br>" + make_table_icon_button(
                    ((f'',),{}),
                    btn_type="transparent",
                    classes=["bi-list-columns-reverse"],
                    on_click=f"openIframeModal('Logs for {container['Names'][0].strip('/')}: {container['Image']}', '{url_for('docker.containers.logsframe', container_id=container['Id'])}')",
                    do_action=False,
                    tooltip='View Logs'
                ) + "".join(
                    make_table_icon_button(
                        ((f'',),{}),
                        btn_type="transparent",
                        classes=[f"bi-{icon}"],
                        on_click=(
                            f"if (confirm('Are you sure you want to run \\'{text}\\' on container {container['Names'][0]}?')) "
                            f"openIframeModal('Task {' '.join(action.split('_')).capitalize()} | {container['Names'][0]}: {container['Image']}', "
                            f"'{url_for('docker.containers.actionframe', container_id=container['Id'],action=action)}')"
                        ),
                        do_action=False,
                        tooltip=text
                    )
                    for action, (text, icon) 
                    in container_actions.items()
                ),
                container["Image"],
                container["State"],
                app.wtf.pretty_date(datetime.datetime.fromtimestamp(container["Created"])),
            )
            for container in containers  
        ],
        custom_script = """
            var statusIndex = -1;
            for (var i = 0; i < headerCells.length; i++) {
                var columnName = headerCells[i].innerText.trim().toLowerCase();
                if (columnName === "state") {
                    statusIndex = i;
                    break;
                }
            }
            ['LOW', 'MEDIUM', 'HIGH', 'CRITICAL']
            if (statusIndex !== -1) {
                var status = data[statusIndex]?.toLowerCase();
                var color = '';
                if (status === 'created') {
                    color = colorMap[errorLevels[1]];
                } else if (status === 'running') {
                    color = colorMap[errorLevels[0]];
                } else if (status === 'restarting') {
                    color = colorMap[errorLevels[2]];
                } else if (status === 'started') {
                    color = colorMap[errorLevels[1]];
                } else if (status === 'exited') {
                    color = colorMap[errorLevels[3]];
                }
                if (color) {
                    $(row).css('background-color', color);
                }
            }
        """
    )
    return page



@blueprint.route('/container/<container_id>/view', methods=['GET', 'POST'])
@app.permission_required(app.models.core.PERMISSION_ENUM.ADMIN)
def view(container_id):
    client = docker.from_env()
    obj = client.containers.get(container_id)
    container = obj.attrs
    return render_template("container/view.html", container=obj, container_data=obj.attrs)


@blueprint.route('/container/<container_id>/action/<action>', methods=['GET', 'POST'])
@app.permission_required(app.models.core.PERMISSION_ENUM.ADMIN)
def action(container_id, action):
    if action not in ACTION_MAP:
        return Response(f"✅❌ Failed: Unknown container action: {action}", mimetype='text/event-stream')

    result_queue = queue.Queue()
    thread = threading.Thread(target=action_worker, args=(action, container_id, result_queue), daemon=True)
    thread.start()

    @stream_with_context
    def generate():
        yield "data: 🖥️▶️ Starting task...\n\n"

        while True:
            try:
                line = result_queue.get(timeout=0.05)
                yield "data: "+line+"\n\n"
            except queue.Empty:
                if not thread.is_alive():
                    break

    return Response(generate(), mimetype='text/event-stream')


@blueprint.route('/container/<container_id>/action_frame/<action>', methods=['GET', 'POST'])
@app.permission_required(app.models.core.PERMISSION_ENUM.ADMIN)
def actionframe(container_id, action):
    return render_template("pages/stream_frame.html", stream_url=url_for("docker.containers.action", action=action, container_id=container_id))


@blueprint.route('/container/<container_id>/logs', methods=['GET', 'POST'])
@app.permission_required(app.models.core.PERMISSION_ENUM.ADMIN)
def logs(container_id):
    def log_streamer(container_id, log_queue, tail=100):
        try:
            client = docker.from_env()
            container = client.containers.get(container_id)
            for log in container.logs(stream=True, follow=True, tail=tail):
                log_queue.put(log.decode("utf-8"))
        except Exception as e:
            log_queue.put(f"data: 🖥️❌ Error: {str(e)}")

    log_queue = queue.Queue()
    thread = threading.Thread(target=log_streamer, args=(container_id, log_queue), daemon=True)
    thread.start()
    @stream_with_context
    def generate():
        while True:
            try:
                line = log_queue.get(timeout=1)
                if line:
                    yield f'data: {line}\n\n'
            except queue.Empty:
                if not thread.is_alive():
                    break
    return Response(generate(), mimetype='text/event-stream')


@blueprint.route('/container/<container_id>/logs_frame', methods=['GET', 'POST'])
@app.permission_required(app.models.core.PERMISSION_ENUM.ADMIN)
def logsframe(container_id):
    return render_template("pages/stream_frame.html", stream_url=url_for("docker.containers.logs", container_id=container_id))