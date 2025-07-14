"""
Cetadash WTFScript headers
"""
prefix = "cd"

def anchor(id=""): pass
def bicon(icon=""): pass
def back_link(content="", url=""): pass
def icon_heading(content="", icon="", classes="", badge=""): pass
def script(src=""): pass
def stylesheet(href=""): pass
def table_head(items="", id="", classes=""): pass
def table_row(items="", id="", classes=""): pass
def table_body(rows="", id="", classes=""): pass
def table(content="", id="", classes="table table-striped table-hoverable table-sm"): pass 

def section_card_end(id=""): pass
def section_card_start(id="", label="", classes="my-3"): pass
def section_card(content="", id="", label="", classes="my-3"): pass
def section(content="", id="", classes="", label=""): pass
def section_end(id=""): pass
def section_start(id="", label=""): pass

def container_end(): pass
def container_start(classes="my-4"): pass

def labeled_val(val="", key="", kclass="text-muted", vclass=""): pass
def note(content="", id="", classes=""): pass

def search_bar(
    search_query="",
    endpoint="",
    query_arg="q",
    button_text="Search",
    placeholder="Enter Search Term"
):
    pass

def container_header(
    title="",
    back="",
    back_text="",
    header_elements="",
    value_boxes="",
    action_buttons=""
):
    pass
def header_title(content=""): pass
def header_value_box(items={}): pass
def js_confirm(action="", text=""): pass