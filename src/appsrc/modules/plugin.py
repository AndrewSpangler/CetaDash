import os
import json
import types
import errno
from typing import Generator, List, Any
import __main__
from .parsing import recursive_update


# Based on https://github.com/pallets/flask/blob/main/src/flask/config.py
def _from_pyfile(path: os.PathLike[str]) -> dict:
    """Loads all-caps values from a config.py file as a dict"""
    path = os.path.join(path)
    d = types.ModuleType("config")
    d.__file__ = path
    try:
        with open(path, mode="rb") as config_file:
            exec(compile(config_file.read(), path, "exec"), d.__dict__)
    except OSError as e:
        if e.errno in (errno.ENOENT, errno.EISDIR, errno.ENOTDIR):
            return False
        e.strerror = f"Unable to load configuration file ({e.strerror})"
        raise
    config = {}
    for key in dir(d):
        if key.isupper():
            config[key] = getattr(d, key)
    return config


def _load_config_modules(modules_to_load:List[os.PathLike[str]]) -> dict:
    """Combines config modules into a dictionary"""
    config = {}
    for m in modules_to_load:
        conf = _from_pyfile(m)
        recursive_update(config, conf)
    return config


def _get_modules(path: os.PathLike[str], filename="config.py") -> List[os.PathLike[str]]:
    """
    Finds config modules to load at a given path in form MODULENAME/config.py
    """
    modules = []
    print(f"Searching for config modules at - {path}")
    for e in os.scandir(path):
        if os.path.isfile(m := os.path.join(e.path, filename)) and not filename.startswith("~"):
            modules.append(m)
    print(f"Found {len(modules)} config modules")
    return modules


def load_plugin_config(path: os.PathLike[str]) -> dict[str:os.PathLike[str]]:
    """Loads plugin configuration files without loading the blueprints"""
    modules = _get_modules(path)
    return _load_config_modules(modules)


def get_blueprints(path: os.PathLike[str] = "src/appsrc/blueprints") -> Generator[Any, None, None]:
    """
    Gets a list of plugin blueprints from a folder
    "path" must be a subdirectory of base_import_path (the folder app.py lives in)
    """
    load_order_path = os.path.join(path, "load_order.json")
    with open(load_order_path) as f:
        load_order = json.load(f)
    base_import_path = os.path.dirname(__main__.__file__) # Launcher file folder
    rel_to_source = os.path.relpath(path, base_import_path)
    rel_to_source = rel_to_source.replace(os.sep, ".").strip(".")

    for batch in load_order:
        for bp_name in batch:
            module_name = f"{rel_to_source}.{bp_name}"
            print(module_name)
            module = __import__(module_name, globals(), locals(), ["blueprint"], 0)
            print(module.blueprint)
            yield module.blueprint