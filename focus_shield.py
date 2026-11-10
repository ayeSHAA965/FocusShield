
import os
import json
import time
import psutil

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SHIELD_STATE_FILE = os.path.join(BASE_DIR, "shield_state.json")

CHECK_INTERVAL = 2


def read_shield_state():
    try:
        with open(SHIELD_STATE_FILE, "r") as file:
            state = json.load(file)

        if isinstance(state, dict):
            return state

    except (FileNotFoundError, json.JSONDecodeError, OSError):
        pass

    return {"active": False, "blocked_apps": []}


def block_selected_apps(selected_apps):
    selected_apps = {
        app.lower()
        for app in selected_apps
        if isinstance(app, str) and app.lower().endswith(".exe")
    }

    for process in psutil.process_iter(["pid", "name"]):
        try:
            app_name = process.info["name"]

            if app_name and app_name.lower() in selected_apps:
                print(f"Focus Shield blocked: {app_name}")
                process.terminate()

        except (
            psutil.NoSuchProcess,
            psutil.AccessDenied,
            psutil.ZombieProcess
        ):
            continue


def start_shield():
    print("=" * 45)
    print("             FOCUS SHIELD")
    print("=" * 45)
    print("Windows protection engine started.")
    print("Custom application monitoring enabled.")
    print("Press CTRL + C to stop.")
    print("=" * 45)

    previous_state = None

    try:
        while True:
            state = read_shield_state()

            active = state.get("active", False)
            selected_apps = state.get("blocked_apps", [])

            if not isinstance(selected_apps, list):
                selected_apps = []

            if active != previous_state:
                print(
                    "\nProtection ACTIVE"
                    if active else "\nProtection INACTIVE"
                )
                previous_state = active

            if active:
                block_selected_apps(selected_apps)

            time.sleep(CHECK_INTERVAL)

    except KeyboardInterrupt:
        print("\nFocus Shield stopped safely.")


if __name__ == "__main__":
    start_shield()
