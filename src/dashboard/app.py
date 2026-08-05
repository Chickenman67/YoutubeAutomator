from typing import Optional

from flask import Flask, jsonify, send_from_directory
from flask_cors import CORS

from dashboard.store import DashboardStore


def create_app(
    store: Optional[DashboardStore] = None,
    queue_root: str = "queue",
) -> Flask:
    app = Flask(__name__)
    CORS(app)
    app.config["JSON_SORT_KEYS"] = False
    store = store or DashboardStore(queue_root=queue_root)

    @app.get("/pending")
    def list_pending():
        return jsonify({"videos": [v.to_dict() for v in store.list_pending()]})

    @app.get("/video/<video_id>")
    def video_details(video_id):
        try:
            package = store.get_video(video_id)
        except FileNotFoundError:
            return jsonify({"error": f"video not found: {video_id}"}), 404
        return jsonify(package.to_dict())

    @app.post("/approve/<video_id>")
    def approve(video_id):
        try:
            store.approve(video_id)
        except FileNotFoundError:
            return jsonify({"error": f"video not found: {video_id}"}), 404
        return jsonify({"video_id": video_id, "status": "approved"})

    @app.post("/reject/<video_id>")
    def reject(video_id):
        try:
            store.reject(video_id)
        except FileNotFoundError:
            return jsonify({"error": f"video not found: {video_id}"}), 404
        return jsonify({"video_id": video_id, "status": "rejected"})

    @app.get("/video/<video_id>/asset/<path:filename>")
    def serve_asset(video_id, filename):
        folder = store.pending_dir / video_id
        if not folder.is_dir():
            return jsonify({"error": f"video not found: {video_id}"}), 404
        if not (folder / filename).is_file():
            return jsonify({"error": f"file not found: {filename}"}), 404
        return send_from_directory(folder, filename)

    return app


if __name__ == "__main__":
    create_app().run(debug=True, host="127.0.0.1", port=5000)
