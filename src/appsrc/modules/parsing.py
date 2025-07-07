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

def localize(utc_datetime:datetime.datetime) -> datetime.datetime:
    """Localize to system timezone"""
    if not utc_datetime: return None
    return utc_datetime.replace(tzinfo=datetime.timezone.utc).astimezone()


def pretty_date(
        local_datetime: datetime.datetime,
        seconds: bool = False,
        minutes: bool = True,
        hours: bool = True,
        use24: bool=True,
        show_tz: bool=False
    ) -> str:
    """
    Template helper function to make dates look better
    """
    if not local_datetime: return None
    format_string = f"%m/%d/%y "
    if hours: format_string += f"%{'H' if use24 else 'I'}"
    if minutes: format_string += ":%M"
    if seconds: format_string += ":%S"
    if not use24: format_string += "%p"
    if show_tz: format_string += "%Z"
    t = local_datetime.strftime(format_string)
    if show_tz:
        t.replace(
            "Pacific Daylight Time", "PDT"
        ).replace(
            "Pacific Standard Time", "PST"
        )
    return t


def from_timestamp(time_in:int)->datetime.datetime:
    return datetime.datetime.fromtimestamp(time_in)


def pretty_from_timestamp(time_in:int, *args, **kw)->str:
    return pretty_date(from_timestamp(time_in), *args, **kw)


def from_rfc_timestamp(ts:str) -> datetime.datetime:
    """Docker timestamp processor"""
    ts_trimmed = ts[:26]
    return datetime.datetime.strptime(ts[:26], "%Y-%m-%dT%H:%M:%S.%f")


def format_seconds(time_in_seconds:int)->str:
    """
    Formats an integer number of seconds to a nice H:MM:SS format
    """
    hours, remainder = divmod(time_in_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    out = ""
    if int(hours): out += f"{int(hours)}:"
    if int(hours) or int(minutes): out += f"{str(int(minutes)).zfill(2)}:"
    return out + f"{str(int(seconds)).zfill(2)}"


def get_tz_from_localization(local_tz) -> str:
    """Template helper function to get server's local tz"""
    return (
        datetime.datetime.now()
        .replace(tzinfo=datetime.timezone.utc)
        .astimezone(local_tz)
    ).strftime("%Z")


def format_bytes(size:int) -> str:
    """Nicely formats a byte count"""
    for suffix in ['B', 'KB', 'MB', 'GB', 'TB']:
        if size < 1024: break
        size /= 1024
    return "{:.2f} {}".format(size, suffix)


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


def make_search_bar(
    endpoint:str,
    search_query:str = "",
    query_arg:str = 'q',
    button_text:str = 'Search',
    placeholder_text:str = "Search",
):
    return render_template(
        "includes/search_bar.html",
        endpoint = endpoint,
        search_query = search_query,
        query_arg = query_arg,
        button_text = button_text,
        placeholder_text = placeholder_text 
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