import os
import json

META_DIR = "/etc/sftp-users"

def save_metadata(username, data):
    os.makedirs(META_DIR, exist_ok=True)
    path = os.path.join(META_DIR, f"{username}.json")
    with open(path, "w") as f:
        json.dump(data, f, indent=4)
    return path


def load_metadata(username):
    path = os.path.join(META_DIR, f"{username}.json")
    if not os.path.exists(path):
        return None
    with open(path) as f:
        return json.load(f)


def delete_metadata(username):
    path = os.path.join(META_DIR, f"{username}.json")
    if os.path.exists(path):
        os.remove(path)
