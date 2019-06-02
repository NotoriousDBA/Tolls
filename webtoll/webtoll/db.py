import mysql.connector

from flask import current_app, g

def get_db():
    if 'db' not in g:
        g.db = mysql.connector.connect(
            database=current_app.config['DBNAME'],
            autocommit=True,
        )

    return g.db

def close_db(e=None):
    db = g.pop('db', None)

    if db is not None:
        db.close()

def init_app(app):
    app.teardown_appcontext(close_db)
