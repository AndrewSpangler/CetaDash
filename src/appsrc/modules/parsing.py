import re
import time
import datetime
import requests
from flask import render_template
from typing import List

def recursive_update(d1:dict, d2:dict) -> None:
    """Recursively combine two dictionaries into d1"""
    for key, value in d2.items():
        if key in d1 and isinstance(d1[key], dict) and isinstance(value, dict):
            recursive_update(d1[key], value)
        else:
            d1[key] = value


def make_table_page(
    name:str,
    *args,
    custom_script:str = 'console.log("Table loaded");',
    **kw
) -> str:
    """
    Creates a table page from a list of columns and rows
    """
    script = custom_script
    return render_template(
        "pages/table_page.html",
        name = name,
        custom_script = custom_script,
        **kw
    )