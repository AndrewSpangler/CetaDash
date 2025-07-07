import os
import psutil
from flask import (
    Blueprint,
    render_template,
    jsonify
)
from collections import defaultdict
from ...main import app
from ...modules.host_info import get_host_info


blueprint = Blueprint(
    'host',
    __name__,
    static_folder=os.path.join(os.path.dirname(__file__),"static"),
    template_folder=os.path.join(os.path.dirname(__file__), "templates"),
)

def _get_route_tree():
    tree = {}

    for rule in app.url_map.iter_rules():
        if rule.endpoint == 'static':
            continue

        endpoint = rule.endpoint or 'unknown'
        path = rule.rule
        is_dynamic = '<' in path

        parts = endpoint.split('.')
        if len(parts) > 1:
            *blueprint_parts, _ = parts
            blueprint_path = '.'.join(blueprint_parts)
        else:
            blueprint_path = '__global__'

        current = tree
        for part in blueprint_path.split('.'):
            current = current.setdefault(part, {})

        current.setdefault('__routes__', []).append({
            'path': path,
            'endpoint': endpoint,
            'is_dynamic': is_dynamic
        })

    def sort_tree(node):
        result = {}
        for key in sorted(k for k in node if k != '__routes__'):
            result[key] = sort_tree(node[key])
        if '__routes__' in node:
            result['__routes__'] = sorted(node['__routes__'], key=lambda r: r['path'])
        return result

    return sort_tree(tree)


@blueprint.route("/stats", methods=["GET", "POST"])
@app.permission_required(app.models.core.PERMISSION_ENUM.ADMIN)
def stats():
    info = get_host_info()
    return render_template("stats.html", info=info)


@blueprint.route('/__route_tree__')
@app.permission_required(app.models.core.PERMISSION_ENUM.ADMIN)
def route_tree():
    tree = _get_route_tree()
    return jsonify(tree)


@blueprint.route('/route_tree')
@app.permission_required(app.models.core.PERMISSION_ENUM.ADMIN)
def show_routes():
    tree = _get_route_tree()
    return render_template('tree.html', tree=tree)