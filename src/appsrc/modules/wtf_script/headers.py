"""lays out arg config for macros, all args must be keywords"""

# Standard order (omit as needed)
# (content/field, placeholder, classes, id)
def a(content="", url=""): pass
def bicon(icon=""): pass
def back_link(content="", url=""): pass
def badge(content="", state="success", classes=""): pass
def br(): pass
def button_submit(content=""): pass
def center(content=""): pass
def code_editor(
  id="",
  title="",
  mode="",
  content="",
  readonly=True,
  theme=None,
  card=True
):
    pass
def col(content="", classes="mb-3", id=""): pass
def container_end(): pass
def container_header(
    title="",
    back="",
    back_text="",
    header_elements="",
    value_boxes="",
    action_buttons=""
):
    pass
def container_start(classes="my-4"): pass
def container(content="", classes="my-4"): pass
def div(content="", classes="", id=""): pass
def dropdown_field(field="", classes="form-select"): pass
def env_editor(content="", id=""): pass
def env_field(field=""): pass
def env_viewer(content="", id="", title=""): pass
def field_errors(field=""): pass
def field_label(field="", classes="form-label"): pass
def form_submit(field=""): pass
def header_title(content=""): pass
def header_value_box(items={}): pass
def hr(classes="mt-1"): pass
def integer_field(field="", placeholder="", classes="form-control"): pass
def labeled_val(val="", key="", kclass="text-muted", vclass=""): pass
def md_editor(content="", id="", field=None): pass
def md_field(field=""): pass
def note(content="", classes="", id="",): pass
def row(content="", classes="", id="",): pass
def search_bar(
    endpoint,
    search_query="",
    query_arg="q",
    button_text="Search",
    placeholder_text="Enter Search Term"
):
    pass
def section_card_end(id=""): pass
def section_card_start(id="", label="", classes="my-3"): pass
def section_card(content="", id="", label="", classes="my-3"): pass
def section_end(id=""): pass
def section_start(id="", label=""): pass
def section(content="", id="", label="", classes="my-3"): pass
def sortable_field(field="", name_map="", items="", label="Items"): pass
def string_field(field="", placeholder="", classes="form-control"): pass
def table(content="", classes="table-striped", id=""): pass
def tbody(content="", classes="", id=""): pass
def td(content="", classes="", id=""): pass
def textarea_field(field="", classes="form-control"): pass
def th(content="", classes="", id=""): pass
def thead(content="", classes="", id=""): pass
def toggle_field(field="", classes="form-check-input"): pass
def tr( content="", classes="", id=""): pass
def yaml_editor(content="", id=""): pass
def yaml_field(field=""): pass
def yaml_viewer(content="", id="", title=""): pass


def icon_heading(content="", icon=""): pass

