from flask import Flask, render_template, request, redirect, url_for, session, flash
import os
import sqlite3
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "local-development-key")

DATABASE = "orbit.db"

# Подключение к базе данных
def get_db_connection():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn

# Создание и обновление таблиц
def init_db():
    conn = get_db_connection()

    conn.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Проверяем, есть ли столбец даты в старой базе
    columns = [
        row["name"]
        for row in conn.execute("PRAGMA table_info(users)").fetchall()
    ]

    if "created_at" not in columns:
        conn.execute("ALTER TABLE users ADD COLUMN created_at TEXT")
        conn.execute("""
            UPDATE users
            SET created_at = CURRENT_TIMESTAMP
            WHERE created_at IS NULL
        """)

    # Таблица избранного
    conn.execute("""
        CREATE TABLE IF NOT EXISTS favorites (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            object_name TEXT NOT NULL,
            description TEXT,
            UNIQUE(user_id, object_name),
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    """)

    conn.commit()
    conn.close()

# Главная страница
@app.route("/")
def home():
    return render_template("index.html")

# Регистрация
@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = request.form["username"].strip()
        password = request.form["password"]

        if not username or not password:
            flash("Заполни все поля")
            return redirect(url_for("register"))

        if len(password) < 6:
            flash("Пароль должен содержать не менее 6 символов")
            return redirect(url_for("register"))

        conn = get_db_connection()

        try:
            hashed_password = generate_password_hash(password)

            conn.execute(
                "INSERT INTO users (username, password) VALUES (?, ?)",
                (username, hashed_password)
            )

            conn.commit()
            flash("Регистрация прошла успешно! Теперь войди в аккаунт.")
            return redirect(url_for("login"))

        except sqlite3.IntegrityError:
            flash("Такое имя пользователя уже занято")
            return redirect(url_for("register"))

        finally:
            conn.close()

    return render_template("register.html")

# Вход в аккаунт
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form["username"].strip()
        password = request.form["password"]

        conn = get_db_connection()

        user = conn.execute(
            "SELECT * FROM users WHERE username = ?",
            (username,)
        ).fetchone()

        conn.close()

        if user and check_password_hash(user["password"], password):
            session["user_id"] = user["id"]
            session["username"] = user["username"]

            return redirect(url_for("account"))

        flash("Неверное имя пользователя или пароль")

    return render_template("login.html")

# Личный кабинет
@app.route("/account")
def account():
    if "user_id" not in session:
        return redirect(url_for("login"))

    conn = get_db_connection()

    user = conn.execute(
        "SELECT * FROM users WHERE id = ?",
        (session["user_id"],)
    ).fetchone()

    favorites = conn.execute(
        "SELECT * FROM favorites WHERE user_id = ? ORDER BY id DESC",
        (session["user_id"],)
    ).fetchall()

    conn.close()

    if user is None:
        session.clear()
        return redirect(url_for("login"))

    return render_template(
        "account.html",
        user=user,
        favorites=favorites
    )

# Добавление объекта в избранное
@app.route("/favorite/add", methods=["POST"])
def add_favorite():
    if "user_id" not in session:
        return redirect(url_for("login"))

    object_name = request.form.get("object_name", "").strip()
    description = request.form.get("description", "").strip()

    if not object_name:
        flash("Не удалось добавить объект")
        return redirect(url_for("home"))

    conn = get_db_connection()

    try:
        conn.execute(
            """
            INSERT INTO favorites (user_id, object_name, description)
            VALUES (?, ?, ?)
            """,
            (session["user_id"], object_name, description)
        )
        conn.commit()
        flash("Объект добавлен в избранное!")

    except sqlite3.IntegrityError:
        flash("Этот объект уже есть в избранном")

    finally:
        conn.close()

    return redirect(request.referrer or url_for("account"))

# Удаление объекта из избранного
@app.route("/favorite/delete/<int:favorite_id>", methods=["POST"])
def delete_favorite(favorite_id):
    if "user_id" not in session:
        return redirect(url_for("login"))

    conn = get_db_connection()

    conn.execute(
        "DELETE FROM favorites WHERE id = ? AND user_id = ?",
        (favorite_id, session["user_id"])
    )

    conn.commit()
    conn.close()

    flash("Объект удалён из избранного")

    return redirect(url_for("account"))
# Изменение имени пользователя
@app.route("/account/update_username", methods=["POST"])
def update_username():
    if "user_id" not in session:
        return redirect(url_for("login"))

    new_username = request.form.get("new_username", "").strip()

    if not new_username:
        flash("Введите новое имя пользователя")
        return redirect(url_for("account"))

    conn = get_db_connection()

    try:
        conn.execute(
            "UPDATE users SET username = ? WHERE id = ?",
            (new_username, session["user_id"])
        )

        conn.commit()
        session["username"] = new_username
        flash("Имя пользователя успешно изменено!")

    except sqlite3.IntegrityError:
        flash("Такое имя пользователя уже занято")

    finally:
        conn.close()

    return redirect(url_for("account"))

# Изменение пароля
@app.route("/account/update_password", methods=["POST"])
def update_password():
    if "user_id" not in session:
        return redirect(url_for("login"))

    old_password = request.form.get("old_password", "")
    new_password = request.form.get("new_password", "")

    conn = get_db_connection()

    user = conn.execute(
        "SELECT * FROM users WHERE id = ?",
        (session["user_id"],)
    ).fetchone()

    if not user or not check_password_hash(user["password"], old_password):
        conn.close()
        flash("Старый пароль введён неправильно")
        return redirect(url_for("account"))

    if len(new_password) < 6:
        conn.close()
        flash("Новый пароль должен содержать минимум 6 символов")
        return redirect(url_for("account"))

    hashed_password = generate_password_hash(new_password)

    conn.execute(
        "UPDATE users SET password = ? WHERE id = ?",
        (hashed_password, session["user_id"])
    )

    conn.commit()
    conn.close()

    flash("Пароль успешно изменён!")

    return redirect(url_for("account"))
# Выход из аккаунта
@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("home"))

if __name__ == "__main__":
    init_db()
    app.run(debug=True)