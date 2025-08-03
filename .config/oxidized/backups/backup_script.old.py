from flask import Flask, request
import os
import json
from datetime import datetime

app = Flask(__name__)

# Define where to store the backups
BACKUP_ROOT = os.path.expanduser("~/.config/oxidized/backups/backup_files")

@app.route("/save_config", methods=["POST"])
def save_config():
    try:
        data = request.get_json()

        device_name = data.get("node", "unknown_device")
        config = data.get("config", "")

        # Ensure device-specific directory exists
        device_dir = os.path.join(BACKUP_ROOT, device_name)
        os.makedirs(device_dir, exist_ok=True)

        # Timestamped filename
        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        filename = f"{device_name}_{timestamp}.txt"
        file_path = os.path.join(device_dir, filename)

        # Write config to file
        with open(file_path, "w") as f:
            f.write(config)

        print(f"[✓] Saved config for {device_name} at {file_path}")
        return {"status": "success"}, 200

    except Exception as e:
        print(f"[✗] Error: {e}")
        return {"status": "error", "message": str(e)}, 500

if __name__ == "__main__":
    print(f"[i] Starting config receiver on http://0.0.0.0:8080/save_config")
    app.run(host="0.0.0.0", port=5000)

