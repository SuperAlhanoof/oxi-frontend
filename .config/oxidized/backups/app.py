from flask import Flask, render_template, render_template_string, request, redirect, url_for, jsonify, send_from_directory
import os
import requests
from datetime import datetime
import calendar

app = Flask(__name__)
app.static_folder = 'static'

OXIDIZED_API = "http://localhost:8888"
BACKUP_DIR = os.path.expanduser("~/.config/oxidized/backups/backup_files")
MODEL_PATH = "/home/oxidized/.rbenv/versions/3.2.2/lib/ruby/gems/3.2.0/gems/oxidized-0.34.0/lib/oxidized/model"

@app.route("/")
def dashboard():
    try:
        res = requests.get(f"{OXIDIZED_API}/nodes.json")
        nodes = sorted(res.json(), key=lambda x: x['name']) if res.ok else []
    except Exception:
        nodes = []

    # Load metadata from network.db
    device_meta = {}
    db_path = os.path.expanduser("~/.config/oxidized/network.db")
    if os.path.exists(db_path):
        with open(db_path, "r") as f:
            for line in f:
                parts = line.strip().split(":")
                if len(parts) >= 3:
                    name, ip, model = parts[:3]
                    user = parts[3] if len(parts) > 3 else ""
                    password = parts[4] if len(parts) > 4 else ""
                    device_meta[name] = {
                        "ip": ip,
                        "model": model,
                        "user": user,
                        "password": password
                    }

    devices = []
    missing_today = []
    today_str = datetime.now().strftime("%Y-%m-%d")
    last_day = calendar.monthrange(datetime.now().year, datetime.now().month)[1]
    end_of_month = datetime(datetime.now().year, datetime.now().month, last_day)
    days_left = (end_of_month - datetime.now()).days

    for node in nodes:
        name = node['name']
        meta = device_meta.get(name, {})
        ip = meta.get("ip", node.get("ip", "N/A"))
        model = meta.get("model", "")
        user = meta.get("user", "")
        password = meta.get("password", "")

        folder = os.path.join(BACKUP_DIR, name)
        last_config = None
        status_class = "fail"
        note = "No configuration file generated today"
        latest_file = None
        for root, _, files in os.walk(folder):
            txts = [f for f in files if f.endswith(".txt") and f.startswith(f"{name}_")]
            txts = sorted(txts, reverse=True)
            if txts:
                candidate = os.path.join(root, txts[0])
                if not latest_file or os.path.getmtime(candidate) > os.path.getmtime(latest_file):
                    latest_file = candidate

        if latest_file:
            filename = os.path.basename(latest_file)
            timestamp_str = filename.replace(name + "_", "").replace(".txt", "")
            last_config = timestamp_str.replace("_", ":")
            last_config_date = timestamp_str.split("_")[0]
            if last_config_date == today_str:
                status_class = "ok"
            else:
                missing_today.append({"name": name, "ip": ip, "note": note})
        else:
            missing_today.append({"name": name, "ip": ip, "note": note})

        epoch = int(os.path.getmtime(latest_file)) if latest_file else None
        devices.append({
            "name": name,
            "ip": ip,
            "model": model,
            "user": user,
            "password": password,
            "last_config": last_config,
            "status_class": status_class,
            "epoch": epoch
        })

    models = [f[:-3] for f in os.listdir(MODEL_PATH) if f.endswith('.rb')]
    return render_template("dashboard.html", devices=devices, missing_today=missing_today, days_left=days_left, models=models)

@app.route("/fetch/<device>")
def fetch_device(device):
    requests.get(f"{OXIDIZED_API}/node/next/{device}")
    return redirect(url_for('dashboard'))

@app.route("/reset_backups")
def reset_backups():
    for device in os.listdir(BACKUP_DIR):
        device_path = os.path.join(BACKUP_DIR, device)
        if os.path.isdir(device_path):
            for year in os.listdir(device_path):
                year_path = os.path.join(device_path, year)
                if os.path.isdir(year_path):
                    for month in os.listdir(year_path):
                        month_path = os.path.join(year_path, month)
                        if os.path.isdir(month_path):
                            files = sorted([
                                f for f in os.listdir(month_path) if f.endswith(".txt")
                            ], reverse=True)
                            for f in files[1:]:
                                os.remove(os.path.join(month_path, f))
    return redirect(url_for("dashboard"))

@app.route("/monitor")
def monitor_page():
    return "<h2>Monitoring Page Placeholder</h2><p>Coming soon!</p>"

@app.route("/monitor/<device>")
def isTheresBackupToday(device):
    folder = os.path.join(BACKUP_DIR, device)
    today_str = datetime.now().strftime("%Y-%m-%d")

    if not os.path.exists(folder):
        return jsonify({
            "device": device,
            "status": "fail",
            "note": f"No backup folder found for device '{device}'"
        })

    latest_file = None
    for root, _, files in os.walk(folder):
        txts = [f for f in files if f.endswith(".txt") and f.startswith(f"{device}_")]
        txts = sorted(txts, reverse=True)
        if txts:
            candidate = os.path.join(root, txts[0])
            if not latest_file or os.path.getmtime(candidate) > os.path.getmtime(latest_file):
                latest_file = candidate

    if not latest_file:
        return jsonify(False)

    filename = os.path.basename(latest_file)
    timestamp_str = filename.replace(device + "_", "").replace(".txt", "")
    last_date = timestamp_str.split("_")[0]

    return jsonify(last_date == today_str)

@app.route("/reload_nodes")
def reload_nodes():
    try:
        response = requests.get(f"{OXIDIZED_API}/reload.json")
        return response.text, 200
    except Exception as e:
        return f"Error: {e}", 500

@app.route("/view/<device>")
def view_config(device):
    base_folder = os.path.join(BACKUP_DIR, device)
    if not os.path.exists(base_folder):
        return f"No backups found for {device}", 404

    latest_file = None
    for root, _, files in os.walk(base_folder):
        txts = [f for f in files if f.endswith(".txt") and f.startswith(f"{device}_")]
        txts = sorted(txts, reverse=True)
        if txts:
            candidate = os.path.join(root, txts[0])
            if not latest_file or os.path.getmtime(candidate) > os.path.getmtime(latest_file):
                latest_file = candidate

    if not latest_file:
        return f"No backup files for {device}", 404

    directory, filename = os.path.split(latest_file)
    return send_from_directory(directory, filename, mimetype="text/plain")

@app.route("/logs/<device>")
def show_logs(device):
    base_folder = os.path.join(BACKUP_DIR, device)
    if not os.path.exists(base_folder):
        return f"No logs found for {device}", 404

    html = f"""
    <html>
    <head>
        <title>Logs for {device}</title>
        <style>
            .folder {{ cursor: pointer; font-weight: bold; margin-top: 10px; }}
            .nested {{ display: none; margin-left: 20px; }}
            .active {{ display: block; }}
        </style>
    </head>
    <body>
    <h2>Logs for {device}</h2>
    <script>
        function toggle(id) {{
            var el = document.getElementById(id);
            el.classList.toggle("active");
        }}
    </script>
    """

    folder_counter = 0
    for year in sorted(os.listdir(base_folder), reverse=True):
        year_path = os.path.join(base_folder, year)
        if not os.path.isdir(year_path): continue
        year_id = f"year_{folder_counter}"
        html += f'<div class="folder" onclick="toggle(\'{year_id}\')">📁 {year}</div>'
        html += f'<div id="{year_id}" class="nested">'
        for month in sorted(os.listdir(year_path), reverse=True):
            month_path = os.path.join(year_path, month)
            if not os.path.isdir(month_path): continue
            month_id = f"month_{folder_counter}"
            html += f'<div class="folder" onclick="toggle(\'{month_id}\')">📁 {month}</div>'
            html += f'<div id="{month_id}" class="nested"><ul>'
            files = sorted([f for f in os.listdir(month_path) if f.endswith(".txt")], reverse=True)
            for file in files:
                rel_path = os.path.join(year, month, file)
                html += f'<li><a href="/logs/{device}/{rel_path}">{file}</a></li>'
            html += '</ul></div>'
            folder_counter += 1
        html += '</div>'

    html += "</body></html>"
    return html

@app.route("/logs/<device>/<path:relpath>")
def read_log_file(device, relpath):
    base_path = os.path.join(BACKUP_DIR, device)
    file_path = os.path.join(base_path, relpath)

    if not os.path.commonpath([os.path.abspath(file_path), os.path.abspath(base_path)]) == os.path.abspath(base_path):
        return "Invalid file path", 400

    if not os.path.exists(file_path):
        return "File not found", 404

    with open(file_path, 'r') as f:
        return f.read(), 200, {'Content-Type': 'text/plain'}

@app.route("/save_config", methods=["POST"])
def save_config():
    try:
        data = request.get_json()
        device_name = data.get("node", "unknown_device")
        config = data.get("config", "")

        now = datetime.now()
        year = str(now.year)
        month = str(now.month).zfill(2)

        device_dir = os.path.join(BACKUP_DIR, device_name, year, month)
        os.makedirs(device_dir, exist_ok=True)

        timestamp = now.strftime("%Y-%m-%d_%H-%M-%S")
        filename = f"{device_name}_{timestamp}.txt"
        file_path = os.path.join(device_dir, filename)

        with open(file_path, "w") as f:
            f.write(config)

        print(f"[✓] Saved config for {device_name} at {file_path}")
        return jsonify({"status": "success"}), 200

    except Exception as e:
        print(f"[✗] Error saving config: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route("/add_device", methods=["POST"])
def add_device():
    name = request.form.get("device", "").strip()
    ip = request.form.get("ip", "").strip()
    model = request.form.get("model", "").strip()
    user = request.form.get("user", "").strip()
    password = request.form.get("password", "").strip()

    fields = [name, ip, model]

    # Add username and password
    fields.append(user)      # will be empty string if missing
    fields.append(password)  # will be empty string if missing

    line = ":".join(fields)

    db_path = os.path.expanduser("~/.config/oxidized/network.db")

    # Ensure last line ends with newline
    if os.path.exists(db_path):
        with open(db_path, "rb+") as f:
            f.seek(-1, os.SEEK_END)
            if f.read(1) != b"\n":
                f.write(b"\n")

    with open(db_path, "a") as f:
        f.write(line + "\n")

    print(f"[+] Added device to DB: {line!r}")
    return redirect(url_for("dashboard"))

@app.route("/edit_device", methods=["POST"])
def edit_device():
    original_name = request.form.get("original_name")
    name = request.form.get("device").strip()
    ip = request.form.get("ip").strip()
    model = request.form.get("model").strip()
    user = request.form.get("user", "").strip()
    password = request.form.get("password", "").strip()

    updated_line = f"{name}:{ip}:{model}:{user}:{password}"

    db_path = os.path.expanduser("~/.config/oxidized/network.db")

    with open(db_path, "r") as f:
        lines = f.readlines()

    new_lines = []
    for line in lines:
        if line.strip().startswith(f"{original_name}:"):
            new_lines.append(updated_line + "\n")
        else:
            new_lines.append(line)

    with open(db_path, "w") as f:
        f.writelines(new_lines)

    print(f"[✓] Updated device: {original_name} → {updated_line}")
    return redirect(url_for("dashboard"))

@app.route("/delete_device/<device_name>", methods=["POST"])
def delete_device(device_name):
    db_path = os.path.expanduser("~/.config/oxidized/network.db")
    with open(db_path, "r") as f:
        lines = f.readlines()

    new_lines = [l for l in lines if not l.startswith(f"{device_name}:")]

    with open(db_path, "w") as f:
        f.writelines(new_lines)

    flash(f"Device '{device_name}' deleted.")
    return redirect(url_for("dashboard"))


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
