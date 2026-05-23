from flask import Flask, render_template, request
import os
import json
import sqlite3
from datetime import datetime
import numpy as np
from PIL import Image
from flask import Flask, render_template, request, redirect, url_for, flash
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
import tensorflow as tf
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Image as RLImage
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.pagesizes import letter
from flask import send_file

app = Flask(__name__)

app.secret_key = "crop_disease_secret_key"

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = "login"


class User(UserMixin):
    def __init__(self, id, name, email, password):
        self.id = id
        self.name = name
        self.email = email
        self.password = password


@login_manager.user_loader
def load_user(user_id):
    conn = sqlite3.connect("database/history.db")
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM users WHERE id = ?", (user_id,))
    user = cursor.fetchone()

    conn.close()

    if user:
        return User(user[0], user[1], user[2], user[3])

    return None

def init_db():
    os.makedirs("database", exist_ok=True)

    conn = sqlite3.connect("database/history.db")
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT,
            email TEXT UNIQUE,
            password TEXT
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            image_path TEXT,
            disease_name TEXT,
            confidence REAL,
            date_time TEXT
        )
    """)

    conn.commit()
    conn.close()

init_db()

UPLOAD_FOLDER = "static/uploads"
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER

model = tf.keras.models.load_model(
    "model.keras",
    compile=False
)

with open("labels.json", "r") as f:
    labels = json.load(f)

with open("disease_info.json", "r") as f:
    disease_info = json.load(f)


def predict_disease(image_path):
    img = Image.open(image_path).convert("RGB")
    img = img.resize((224, 224))

    img_array = np.array(img) / 255.0
    img_array = np.expand_dims(img_array, axis=0)

    prediction = model.predict(img_array)
    index = np.argmax(prediction)

    disease_name = labels[index]
    print("Predicted disease name:", disease_name)
    print("Available disease info keys:", disease_info.keys())
    confidence = round(float(np.max(prediction) * 100), 2)

    print("Predicted:", disease_name)

    info = disease_info.get(disease_name) or {
        "title": disease_name,
        "cause": "Information not available.",
        "symptoms": "Information not available.",
        "treatment": "Consult agriculture expert.",
        "fertilizer": "Use balanced fertilizer.",
        "prevention": "Maintain good crop hygiene."
    }

    return disease_name, confidence, info


advice_data = {
    "watering": {
        "title": "Watering Advice",
        "image": "watering.jpg",
        "video": "watering.mp4",
        "points": [
            "Water crops early in the morning or evening.",
            "Avoid watering leaves directly to reduce fungal diseases.",
            "Use drip irrigation for better water saving.",
            "Check soil moisture before watering.",
            "Do not overwater tomato and potato plants.",
            "Increase watering during dry weather.",
            "Reduce watering during rainy season."
        ]
    },
    "fertilizer": {
        "title": "Fertilizer Advice",
        "image": "fertilizer.jpg",
        "video": "fertilizer.mp4",
        "points": [
            "Use organic compost to improve soil quality.",
            "Use balanced NPK fertilizer according to crop needs.",
            "Avoid excessive nitrogen because it increases leaf growth but reduces fruit quality.",
            "Use potassium-rich fertilizer during flowering and fruiting.",
            "Add calcium for tomato plants to prevent fruit disorders.",
            "Test soil before applying fertilizer.",
            "Apply fertilizer near roots, not directly on leaves."
        ]
    },
    "pest": {
        "title": "Pest Control Advice",
        "image": "pest.jpg",
        "video": "pest.mp4",
        "points": [
            "Check leaves weekly for insects and eggs.",
            "Remove infected leaves early.",
            "Use neem oil spray for natural pest control.",
            "Keep field clean and remove weeds.",
            "Use yellow sticky traps for flying insects.",
            "Avoid overuse of chemical pesticides.",
            "Consult an agriculture expert for severe pest attacks."
        ]
    },
    "soil": {
        "title": "Soil Health Advice",
        "image": "soil.jpg",
        "video": "soil.mp4",
        "points": [
            "Maintain proper soil drainage.",
            "Use crop rotation to reduce disease risk.",
            "Add compost and organic matter regularly.",
            "Avoid continuous planting of the same crop.",
            "Maintain soil pH according to crop requirements.",
            "Do not allow waterlogging.",
            "Mulching helps maintain soil moisture."
        ]
    }
}


@app.route("/")
def home():
    return render_template("index.html")


@app.route("/detect")
@login_required
def detect():
    return render_template("detect.html")


    methods=["POST"]
def predict():
    if "image" not in request.files:
        return "No image uploaded"

    file = request.files["image"]

    if file.filename == "":
        return "No selected file"

    image_path = os.path.join(app.config["UPLOAD_FOLDER"], file.filename)
    file.save(image_path)

    disease_name, confidence, info = predict_disease(image_path)

    return render_template(
        "result.html",
        disease_name=disease_name,
        confidence=confidence,
        info=info,
        image_path=image_path
    )

@app.route("/predict", methods=["POST"])
@login_required
def predict():
    if "image" not in request.files:
        return "No image uploaded"

    file = request.files["image"]

    if file.filename == "":
        return "No selected file"

    os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)

    image_path = os.path.join(app.config["UPLOAD_FOLDER"], file.filename)
    file.save(image_path)

    disease_name, confidence, info = predict_disease(image_path)

    conn = sqlite3.connect("database/history.db")
    cursor = conn.cursor()

    cursor.execute("""
    INSERT INTO history (user_id, image_path, disease_name, confidence, date_time)
    VALUES (?, ?, ?, ?, ?)
""", (
    current_user.id,
    image_path,
    disease_name,
    confidence,
    datetime.now().strftime("%d-%m-%Y %I:%M %p")
))

    conn.commit()
    conn.close()

    return render_template(
        "result.html",
        disease_name=disease_name,
        confidence=confidence,
        info=info,
        image_path=image_path
    )
@app.route("/download_report")
@login_required
def download_report():

    disease = request.args.get("disease")
    confidence = request.args.get("confidence")
    cause = request.args.get("cause")
    symptoms = request.args.get("symptoms")
    treatment = request.args.get("treatment")
    fertilizer = request.args.get("fertilizer")
    prevention = request.args.get("prevention")
    image_path = request.args.get("image")

    os.makedirs("static/reports", exist_ok=True)

    pdf_path = "static/reports/report.pdf"

    doc = SimpleDocTemplate(
        pdf_path,
        pagesize=letter
    )

    styles = getSampleStyleSheet()
    elements = []

    title = Paragraph(
        "<b>Crop Disease Detection Report</b>",
        styles["Title"]
    )

    elements.append(title)
    elements.append(Spacer(1, 20))

    if image_path and os.path.exists(image_path):
        img = RLImage(image_path, width=250, height=250)
        elements.append(img)
        elements.append(Spacer(1, 20))

    report_text = f"""
    <b>Disease:</b> {disease}<br/><br/>
    <b>Confidence:</b> {confidence}%<br/><br/>
    <b>Cause:</b> {cause}<br/><br/>
    <b>Symptoms:</b> {symptoms}<br/><br/>
    <b>Treatment:</b> {treatment}<br/><br/>
    <b>Fertilizer:</b> {fertilizer}<br/><br/>
    <b>Prevention:</b> {prevention}
    """

    elements.append(
        Paragraph(report_text, styles["BodyText"])
    )

    doc.build(elements)

    return send_file(pdf_path, as_attachment=True)
@app.route("/advisory")
def advisory():
    return render_template("advisory.html")


@app.route("/advice/<topic>")
def advice_detail(topic):
    advice = advice_data.get(topic)

    if advice is None:
        return "Advice not found"

    return render_template("advice_detail.html", advice=advice)


@app.route("/about")
def about():
    return render_template("about.html")


@app.route("/contact")
def contact():
    return render_template("contact.html")

@app.route("/history")
@login_required
def history():
    conn = sqlite3.connect("database/history.db")
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM history WHERE user_id = ? ORDER BY id DESC",(current_user.id,)
                   )
    records = cursor.fetchall()

    conn.close()

    return render_template("history.html", records=records)


@app.route("/irrigation", methods=["GET", "POST"])
def irrigation():
    result = None

    crop_water_need = {
        "tomato": 5,
        "potato": 4,
        "pepper": 4.5,
        "wheat": 3.5,
        "rice": 8,
        "maize": 5.5
    }

    if request.method == "POST":
        land_size = float(request.form["land_size"])
        crop_type = request.form["crop_type"]

        water_per_m2 = crop_water_need.get(crop_type, 4)
        total_water = land_size * water_per_m2

        if crop_type == "rice":
            timing = "Irrigate daily or maintain shallow water level."
        elif crop_type in ["tomato", "pepper"]:
            timing = "Irrigate every 2 to 3 days, preferably early morning."
        elif crop_type == "potato":
            timing = "Irrigate every 3 to 4 days depending on soil moisture."
        else:
            timing = "Irrigate every 3 to 5 days based on weather and soil condition."

        result = {
            "crop": crop_type.title(),
            "land_size": land_size,
            "water": round(total_water, 2),
            "timing": timing
        }

    return render_template("irrigation.html", result=result)

@app.route("/dashboard")
@login_required
def dashboard():
    conn = sqlite3.connect("database/history.db")
    cursor = conn.cursor()

    cursor.execute("SELECT COUNT(*) FROM history")
    total_scans = cursor.fetchone()[0]

    cursor.execute("SELECT disease_name, COUNT(*) FROM history GROUP BY disease_name")
    disease_counts = cursor.fetchall()

    cursor.execute("SELECT AVG(confidence) FROM history")
    avg_confidence = cursor.fetchone()[0]

    conn.close()

    labels_chart = [item[0].replace("_", " ") for item in disease_counts]
    data_chart = [item[1] for item in disease_counts]

    return render_template(
        "dashboard.html",
        total_scans=total_scans,
        avg_confidence=round(avg_confidence or 0, 2),
        disease_counts=disease_counts,
        labels_chart=labels_chart,
        data_chart=data_chart
    )

@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        name = request.form["name"]
        email = request.form["email"]
        password = generate_password_hash(request.form["password"])

        try:
            conn = sqlite3.connect("database/history.db")
            cursor = conn.cursor()

            cursor.execute("""
                INSERT INTO users (name, email, password)
                VALUES (?, ?, ?)
            """, (name, email, password))

            conn.commit()
            conn.close()

            return redirect(url_for("login"))

        except:
            return "Email already registered"

    return render_template("register.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form["email"]
        password = request.form["password"]

        conn = sqlite3.connect("database/history.db")
        cursor = conn.cursor()

        cursor.execute("SELECT * FROM users WHERE email = ?", (email,))
        user = cursor.fetchone()

        conn.close()

        if user and check_password_hash(user[3], password):
            login_user(User(user[0], user[1], user[2], user[3]))
            return redirect(url_for("dashboard"))

        return "Invalid email or password"

    return render_template("login.html")


@app.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("login"))


if __name__ == "__main__":
    app.run(debug=True)
