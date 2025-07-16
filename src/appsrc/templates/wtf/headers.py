"""
Cetadash WTFScript headers
"""
prefix = "cd"


def anchor(id=""): pass

def bicon(icon=""): pass
def back_link(content="", url=""): pass
def container_end(): pass
def container_start(classes="my-4"): pass

def data_table(
    name="",
    columns="",
    rows="",
    custom_script='console.log("Table loaded");',
    for_page=""
): pass
def data_table_script(name="", script="", default_rows=25): pass
def data_table_script_common(): pass
def icon_heading(content="", icon="", classes="", badge=""): pass
def script(src=""): pass
def stylesheet(href=""): pass
def section_card_end(id=""): pass
def section_card_start(id="", label="", classes="my-3"): pass
def section_card(content="", id="", label="", classes="my-3"): pass
def section(content="", id="", classes="", label=""): pass
def section_end(id=""): pass
def section_start(id="", label=""): pass

def table_button(
  text="",
  url_args=("",{}),
  on_submit=None,
  btn_type="success",
  classes="",
  float="left",
  do_action=True,
  on_click=None,
  tooltip=None,
  method="POST"
): pass
def table_icon_button(
    url_args:tuple[list, dict],
    on_submit:str=None,
    btn_type:str="transparent",
    classes:list[str]=[],
    float:str="left",
    do_action:bool=True,
    on_click:str=None,
    tooltip:str=None, 
    method:str="POST" 
): pass
def table_button_row(content=""): pass


def table_head(items="", id="", classes=""): pass
def table_row(items="", id="", classes=""): pass
def table_body(rows="", id="", classes=""): pass
def table(content="", id="", classes="table table-striped table-hoverable table-sm"): pass 

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






# Specialty
def creator_editor_box(obj=""): pass
def details_description_card(obj=""): pass
def edit_logs_card(obj="", log_url_callback=""):pass