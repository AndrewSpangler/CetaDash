import os
import logging
import inspect
import importlib
from flask import url_for
from jinja2 import Environment, BaseLoader


class TemplateRenderer:
    def __init__(self, template_str: str, env: Environment):
        self.env = env
        self.template = self.env.from_string(template_str)

    def render(self, **kw) -> str:
        return self.template.render(**kw)


class WTFScript:
    def __init__(self, app):
        self.macros = {}
        self.renderers = {}
        self.signatures = {}

        # Create shared Jinja2 environment
        self.env = Environment(loader=BaseLoader())
        self.env.globals["url_for"] = url_for # for flask rendering

        # Load dummy functions from headers.py
        self.dummy_functions = self._load_dummy_functions()

        # Register dummy functions for macro args
        for name, func in self.dummy_functions.items():
            filt = self._make_filter(name)
            self.env.filters[name] = filt
            self.env.globals[name] = filt

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
                app.jinja_env.filters[name] = filt
                app.jinja_env.globals[name] = filt

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