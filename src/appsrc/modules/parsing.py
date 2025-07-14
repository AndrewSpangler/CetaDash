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


def make_table_button(
    text:str,
    url_args:tuple[list, dict],
    on_submit:str=None,
    btn_type:str="success",
    classes:List[str]=[],
    float:str="left",
    do_action:bool=True,
    on_click:str=None,
    tooltip:str=None,
    method:str="POST"
) -> str:
    url_args, url_kwargs = url_args
    clss = set(classes)
    if tooltip:
        clss.add("table-tooltip")
    return render_template(
        "includes/table_button.html",
        text=text,
        url_args=url_args,
        url_kwargs=url_kwargs,
        on_submit=on_submit,
        classes=list(clss),
        float=float,
        btn_type=btn_type,
        do_action=do_action,
        on_click=on_click,
        tooltip=tooltip,
        method=method
    )


def make_table_icon_button(
    url_args:tuple[list, dict],
    on_submit:str=None,
    btn_type:str="transparent",
    classes:List[str]=[],
    float:str="left",
    do_action:bool=True,
    on_click:str=None,
    tooltip:str=None, 
    method:str="POST" 
):
    clss = set(classes)
    clss.update(["big-icon", "text-normal"])
    return make_table_button(
        "",
        url_args,
        on_submit=on_submit,
        btn_type=btn_type,
        classes=list(clss),
        float=float,
        do_action=do_action,
        on_click=on_click,
        tooltip=tooltip,
        method=method
    )

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
        for_page = True,
        **kw
    )