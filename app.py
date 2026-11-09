import os
import psycopg2
from dotenv import load_dotenv

load_dotenv()
from psycopg2.extras import RealDictCursor
from flask import Flask, render_template, request, redirect, url_for, session, flash

app = Flask(__name__)

app.secret_key = os.environ.get("SECRET_KEY", "local-development-key")

DATABASE_URL = os.environ.get("DATABASE_URL")

# Подключение к базе данных Neon
def get_db_connection():
    if not DATABASE_URL:
        raise RuntimeError("Не задана переменная DATABASE_URL в настройках приложения")

    return psycopg2.connect(
        DATABASE_URL,
        cursor_factory=RealDictCursor
    )

# Создание таблиц
def init_db():
    conn = get_db_connection()

    try:
        with conn.cursor() as cursor:
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    id SERIAL PRIMARY KEY,
                    username TEXT UNIQUE NOT NULL,
                    password TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS favorites (
                    id SERIAL PRIMARY KEY,
                    user_id INTEGER NOT NULL REFERENCES users(id),
                    object_name TEXT NOT NULL,
                    description TEXT,
                    UNIQUE(user_id, object_name)
                )
            """)

        conn.commit()
    finally:
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

        from werkzeug.security import generate_password_hash

        hashed_password = generate_password_hash(password)
        conn = get_db_connection()

        try:
            with conn.cursor() as cursor:
                cursor.execute(
                    "INSERT INTO users (username, password) VALUES (%s, %s)",
                    (username, hashed_password)
                )

            conn.commit()
            flash("Регистрация прошла успешно! Теперь войди в аккаунт.")
            return redirect(url_for("login"))

        except psycopg2.errors.UniqueViolation:
            conn.rollback()
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

        from werkzeug.security import check_password_hash

        conn = get_db_connection()

        try:
            with conn.cursor() as cursor:
                cursor.execute(
                    "SELECT * FROM users WHERE username = %s",
                    (username,)
                )
                user = cursor.fetchone()
        finally:
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

    try:
        with conn.cursor() as cursor:
            cursor.execute(
                "SELECT * FROM users WHERE id = %s",
                (session["user_id"],)
            )
            user = cursor.fetchone()

            cursor.execute(
                "SELECT * FROM favorites WHERE user_id = %s ORDER BY id DESC",
                (session["user_id"],)
            )
            favorites = cursor.fetchall()
    finally:
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
        with conn.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO favorites (user_id, object_name, description)
                VALUES (%s, %s, %s)
                """,
                (session["user_id"], object_name, description)
            )

        conn.commit()
        flash("Объект добавлен в избранное!")

    except psycopg2.errors.UniqueViolation:
        conn.rollback()
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

    try:
        with conn.cursor() as cursor:
            cursor.execute(
                "DELETE FROM favorites WHERE id = %s AND user_id = %s",
                (favorite_id, session["user_id"])
            )

        conn.commit()
    finally:
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
        with conn.cursor() as cursor:
            cursor.execute(
                "UPDATE users SET username = %s WHERE id = %s",
                (new_username, session["user_id"])
            )

        conn.commit()
        session["username"] = new_username
        flash("Имя пользователя успешно изменено!")

    except psycopg2.errors.UniqueViolation:
        conn.rollback()
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

    from werkzeug.security import check_password_hash, generate_password_hash

    conn = get_db_connection()

    try:
        with conn.cursor() as cursor:
            cursor.execute(
                "SELECT * FROM users WHERE id = %s",
                (session["user_id"],)
            )
            user = cursor.fetchone()

            if not user or not check_password_hash(user["password"], old_password):
                flash("Старый пароль введён неправильно")
                return redirect(url_for("account"))

            if len(new_password) < 6:
                flash("Новый пароль должен содержать минимум 6 символов")
                return redirect(url_for("account"))

            hashed_password = generate_password_hash(new_password)

            cursor.execute(
                "UPDATE users SET password = %s WHERE id = %s",(hashed_password, session["user_id"])
            )

        conn.commit()
        flash("Пароль успешно изменён!")
    finally:
        conn.close()
    return redirect(url_for("account"))

# Выход из аккаунта
@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("home"))

# Создаём таблицы при запуске приложения
init_db()
@app.route('/robots.txt')
def robots():
    return """User-agent: *
Allow: /

Sitemap: https://orbit-space-a7cb.onrender.com/sitemap.xml"""

if __name__ == "__main__":
    app.run(debug=True)