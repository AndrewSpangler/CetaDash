import os
from flask import (
    Blueprint,
    render_template,
    redirect,
    abort,
    url_for,
    flash,
    request
)
from ...main import app, db
from sqlalchemy import MetaData, or_
from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.automap import automap_base


blueprint = Blueprint(
    'database_viewer',
    __name__,
    template_folder=os.path.join(os.path.dirname(__file__), "templates"),
    url_prefix='/databases'
)


def get_table(engine, table_name):
    (metadata := MetaData(bind=engine)).reflect(only=[table_name])
    return metadata.tables[table_name]


def get_table_columns(engine, table_name):
    return get_table(engine, table_name).columns.keys()


def get_rows(engine, table_name, search_term=None, limit=1000):
    (Base := automap_base()).prepare(engine, reflect=True)
    if not (table_class := Base.classes.get(table_name)):
        raise ValueError("Table '{}' not found.".format(table_name))
    
    columns = [c.key for c in table_class.__table__.columns]
    q = [getattr(table_class, c) for c in columns]
    query = (session := sessionmaker(bind=engine)()).query(*q)
    if search_term: query = query.filter(or_(*[a.ilike(f"%{search_term}%") for a in q]))
    rows = [tuple(row) for row in query.limit(limit).all()]
    session.close()
    return rows


def get_orm_object(engine, table_name, primary_key):
    (Base := automap_base()).prepare(engine, reflect=True)
    if not (table_class := Base.classes.get(table_name)):
        raise ValueError("Table '{}' not found.".format(table_name))
    session = sessionmaker(bind=engine)()
    orm_object = session.query(table_class).get(primary_key)
    session.close()
    return orm_object


@blueprint.route("/")
@blueprint.route("/<database>")
@blueprint.route("/<database>/<table>/")
@blueprint.route("/<database>/<table>/<uid>")
@app.permission_required(app.models.core.PERMISSION_ENUM.ADMIN)
def view(database=None, table=None, uid=None):
    bind_url_map = {
        str(db.get_engine(bind_key=k).url): k
        for k in app.config["SQLALCHEMY_BINDS"]
    }

    databases = {k: [] for k in app.config["SQLALCHEMY_BINDS"]}
    engines = {}
    table_to_engine = {}

    for table_object, engine in db.get_binds().items():
        engine_url = str(engine.url)

        # Match by full normalized engine URL
        bind = bind_url_map.get(engine_url)

        if not bind:
            print(f"WARNING: Unrecognized engine URL: {engine_url}")
            continue

        databases[bind].append(table_object)
        engines[bind] = engine
        table_to_engine[table_object.name] = engine

    if (
        ((uid or table) and not database)
        or (table and not (engine := table_to_engine.get(table)))
        ):
        print("LOOKUP ERROR")
        flash("Lookup Error", "warning")
        return redirect(url_for("database_viewer.view")) 

    kw = { # Templating objects
        "databases":databases,
        "engines": engines,
        "database": database,
        "table" : table,
        "uid": uid,
    }

    if uid: # Database object page
        if not (db_object := get_orm_object(engine, table, uid)):
            return abort(404)
        return render_template(
            "object.html",
            object=db_object,
            **kw
        )

    if table: # Database object listing
        columns = get_table_columns(engine, table)
        rows = get_rows(engine, table, request.args.get('q'))
        return render_template(
            "db_table.html",
            columns = columns,
            rows = rows,
            query = request.args.get('q'),
            **kw
        )
        
    # Database table listing
    if database: return render_template("database.html", **kw) 
    # Database listing
    return render_template("databases.html", **kw)