import os
import logging
import inspect
import importlib
from flask import Flask, url_for
from jinja2 import Environment, BaseLoader
from typing import Callable, Iterable

class TemplateRenderer:
    def __init__(self, template_str: str, env: Environment):
        self.env = env
        self.template = self.env.from_string(template_str)

    def render(self, **kw) -> str:
        return self.template.render(**kw)


def accumulate(iterable:Iterable, callback:Callable, *args, **kw) -> str:
    """
    Applies a callback function to each item in the iterable and returns
    the results as a list
    """
    return [callback(i, *args, **kw) for i in iterable]


def collect_attr(itterable:Iterable, attr:str) -> list:
    """
    Collets a list of attributes from an itterable and returns the results
    as a list
    """
    return [getattr(i, attr) for i in itterable]


class WTFScript:
    reserved = [
        "app",
        "env"
        "macros",
        "renderers",
        "reserved",
        "signatures",
    ]

    builtins = {
        accumulate,
        all,
        any,
        bin,
        bool,
        bytearray,
        bytes,
        collect_attr,
        dict,
        dir,
        divmod,
        enumerate,
        filter,
        float,
        getattr,
        hasattr,
        hex,
        int,
        isinstance,
        issubclass,
        len,
        list, 
        max,
        min,
        next,
        oct,
        pow,
        range,
        reversed,
        round,
        set,
        slice,
        sorted,
        str,
        sum,        
        tuple,
        type,
        zip
    }

    def __init__(
        self,
        app,
        binds:dict = {} # Map of names to callables to register
    ):
        self.app = app  # Store app for later use
        self.macros = {}
        self.renderers = {}
        self.signatures = {}

        # create shared Jinja2 environment
        self.env = Environment(loader=BaseLoader())

        # Built-in functions
        for builtin in self.builtins:
            self._bind(builtin.__name__, builtin)

        for name, callback in binds.items():
            self._bind(name, callback)

        # Load dummy functions from headers.py
        self.dummy_functions = self._load_dummy_functions()

        macros_dir = os.path.join(os.path.dirname(__file__), "macros")
        for ent in os.scandir(macros_dir):
            if ent.name.endswith(".html"):
                name = ent.name[:-5]
                with open(ent.path) as f:
                    template = f.read()
                self.macros[name] = template
                func = self.dummy_functions.get(name)
                sig = inspect.signature(func) if func else None
                renderer = TemplateRenderer(template, env=self.env)
                self.renderers[name] = renderer
                self.signatures[name] = sig
                filt = self._make_filter(name)
                self._bind(name, filt)

    def _bind(self, name: str, callback: Callable) -> None:
        """
        Bind callable as filter/global/method
        """
        if name.startswith("_"):
            raise ValueError(f"Cannot bind macro {name} - macros starting with underscores are not allowed")
        if name in self.reserved:
            raise ValueError(f"Cannot bind macro {name} - name is reserved.")
        self.env.filters[name] = callback
        self.env.globals[name] = callback
        self.app.jinja_env.filters[name] = callback
        self.app.jinja_env.globals[name] = callback
        setattr(self, name, callback)

    def _load_dummy_functions(self):
        """Load dummy functions for arg checking."""
        header_path = os.path.join(os.path.dirname(__file__), "headers.py")
        spec = importlib.util.spec_from_file_location("header", header_path)
        header_module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(header_module)
        return {
            name: func
            for name, func in inspect.getmembers(header_module, inspect.isfunction)
        }

    def _make_filter(self, name):
        def _render_filter(*args, **kwargs):
            return self._render(name, *args, **kwargs)
        return _render_filter

    def _render(self, name, *args, **kwargs):
        renderer = self.renderers.get(name)
        sig = self.signatures.get(name)

        if not renderer or not sig:
            raise ValueError(f"No macro named '{name}' or missing signature")

        try:
            bound = sig.bind_partial(*args, **kwargs)
            bound.apply_defaults()
            context = dict(bound.arguments)
        except TypeError as e:
            raise ValueError(f"Invalid arguments for macro '{name}': {e}")

        return renderer.render(**context)