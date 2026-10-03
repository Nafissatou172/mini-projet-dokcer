"""Petit gestionnaire de tâches (Flask + PostgreSQL)."""
import os
import time

import psycopg
from psycopg.rows import dict_row
from flask import Flask, abort, jsonify, redirect, render_template, request, url_for

app = Flask(__name__)

# On se connecte à la base via le nom du service ("db"), pas via une IP.
DB_DSN = (
    f"host={os.environ.get('DB_HOST', 'db')} "
    f"port={os.environ.get('DB_PORT', '5432')} "
    f"dbname={os.environ['POSTGRES_DB']} "
    f"user={os.environ['POSTGRES_USER']} "
    f"password={os.environ['POSTGRES_PASSWORD']}"
)

PRIORITIES = ("basse", "normale", "haute")


def get_conn():
    return psycopg.connect(DB_DSN, autocommit=True)


def init_db(retries=10):
    """Crée la table si elle n'existe pas encore.

    Postgres peut mettre quelques secondes à accepter les connexions, donc on réessaie.
    """
    for attempt in range(1, retries + 1):
        try:
            with get_conn() as conn:
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS tasks (
                        id         SERIAL PRIMARY KEY,
                        title      TEXT NOT NULL,
                        priority   TEXT NOT NULL DEFAULT 'normale',
                        done       BOOLEAN NOT NULL DEFAULT FALSE,
                        created_at TIMESTAMPTZ NOT NULL DEFAULT now()
                    )
                    """
                )
            return
        except psycopg.OperationalError as exc:
            print(f"[init_db] base indisponible (essai {attempt}/{retries}) : {exc}", flush=True)
            time.sleep(2)
    raise RuntimeError("Impossible de joindre la base de données")


def fetch_tasks(priority=None, status=None):
    query = "SELECT id, title, priority, done, created_at FROM tasks"
    clauses, params = [], []
    if priority in PRIORITIES:
        clauses.append("priority = %s")
        params.append(priority)
    if status == "todo":
        clauses.append("done = FALSE")
    elif status == "done":
        clauses.append("done = TRUE")
    if clauses:
        query += " WHERE " + " AND ".join(clauses)
    # Les tâches non faites d'abord, puis par priorité, puis les plus récentes
    query += (
        " ORDER BY done, CASE priority WHEN 'haute' THEN 0 WHEN 'normale' THEN 1 ELSE 2 END,"
        " created_at DESC"
    )
    with get_conn() as conn, conn.cursor(row_factory=dict_row) as cur:
        cur.execute(query, params)
        return cur.fetchall()


def create_task(title, priority):
    if priority not in PRIORITIES:
        priority = "normale"
    with get_conn() as conn, conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            "INSERT INTO tasks (title, priority) VALUES (%s, %s)"
            " RETURNING id, title, priority, done, created_at",
            (title, priority),
        )
        return cur.fetchone()


def toggle_task(task_id):
    with get_conn() as conn:
        cur = conn.execute("UPDATE tasks SET done = NOT done WHERE id = %s", (task_id,))
        return cur.rowcount == 1


def delete_task(task_id):
    with get_conn() as conn:
        cur = conn.execute("DELETE FROM tasks WHERE id = %s", (task_id,))
        return cur.rowcount == 1


# --- Pages HTML ---

@app.get("/")
def index():
    priority = request.args.get("priority")
    status = request.args.get("status")
    tasks = fetch_tasks(priority, status)
    return render_template(
        "index.html", tasks=tasks, priorities=PRIORITIES,
        current_priority=priority, current_status=status,
    )


@app.post("/tasks")
def add_task_form():
    title = request.form.get("title", "").strip()
    if title:
        create_task(title, request.form.get("priority", "normale"))
    return redirect(url_for("index"))


@app.post("/tasks/<int:task_id>/toggle")
def toggle_task_form(task_id):
    toggle_task(task_id)
    return redirect(request.referrer or url_for("index"))


@app.post("/tasks/<int:task_id>/delete")
def delete_task_form(task_id):
    delete_task(task_id)
    return redirect(request.referrer or url_for("index"))


# --- API JSON ---

@app.get("/api/tasks")
def api_list():
    tasks = fetch_tasks(request.args.get("priority"), request.args.get("status"))
    return jsonify([{**t, "created_at": t["created_at"].isoformat()} for t in tasks])


@app.post("/api/tasks")
def api_create():
    data = request.get_json(silent=True) or {}
    title = str(data.get("title", "")).strip()
    if not title:
        return jsonify(error="le champ 'title' est obligatoire"), 400
    task = create_task(title, data.get("priority", "normale"))
    return jsonify({**task, "created_at": task["created_at"].isoformat()}), 201


@app.patch("/api/tasks/<int:task_id>/done")
def api_toggle(task_id):
    if not toggle_task(task_id):
        abort(404)
    return jsonify(ok=True)


@app.delete("/api/tasks/<int:task_id>")
def api_delete(task_id):
    if not delete_task(task_id):
        abort(404)
    return "", 204


@app.get("/health")
def health():
    with get_conn() as conn:
        conn.execute("SELECT 1")
    return jsonify(status="ok")


init_db()
