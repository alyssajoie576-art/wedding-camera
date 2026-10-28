import os
import io
import base64
import zipfile
import json
import logging
from datetime import datetime
from functools import wraps

from flask import (
    Flask, render_template, request, redirect, url_for,
    session, send_file, jsonify, abort
)
import qrcode
from werkzeug.exceptions import HTTPException

logger = logging.getLogger("wedding-camera")

# ─────────────────────────────────────────────────────────────
# WEDDING DETAILS — edit these for your event, that's it!
# ─────────────────────────────────────────────────────────────
WEDDING = {
    "partner_1": "Gab",
    "partner_2": "Aly",
    "date": "November 29, 2026",
    "venue": "The Veranda Tagaytay",
    "hashtag": "#GabfoundhisfinAly",
    "welcome_message": "Help us capture today from every angle — tap the camera to snap a photo. It'll land straight in our shared album!",
    # Drop a photo of the two of you at static/couple.jpg (square-ish photos work best).
    "couple_photo": "couple.jpg",
    # Optional intro video: put an mp4 at static/intro.mp4. It plays on its own
    # (muted) when the page opens; guests tap to open the camera.
    "intro_video": "intro.mp4",
}

# Passcode the bride & groom use to view the private gallery.
GALLERY_PASSCODE = os.environ.get("GALLERY_PASSCODE", "ourwedding2026")

# The one built-in look every photo gets automatically. Guests can't change this.
BUILT_IN_FILTER = {
    "label": "Vintage",
    "css": "sepia(0.35) contrast(1.1) brightness(0.95) saturate(1.3)",
}

# ─────────────────────────────────────────────────────────────
# Google Drive (first choice for storing photos)
# ─────────────────────────────────────────────────────────────
# Uploads happen AS YOU (not as a robot account), so photos use your own Drive
# space. Environment variables needed (see README section 2b):
#   GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET, GOOGLE_REFRESH_TOKEN, GDRIVE_FOLDER_ID

class DriveBackend:
    name = "Google Drive"
    SAFETY_MARGIN = 50 * 1024 * 1024  # stop 50 MB before the account is actually full

    def __init__(self):
        env = os.environ.get
        self.client_id = env("GOOGLE_CLIENT_ID")
        self.client_secret = env("GOOGLE_CLIENT_SECRET")
        self.refresh_token = env("GOOGLE_REFRESH_TOKEN")
        self.folder_id = env("GDRIVE_FOLDER_ID")
        self._service = None
        self._quota = None
        self._quota_checked_at = 0

    @property
    def configured(self):
        return all([self.client_id, self.client_secret, self.refresh_token, self.folder_id])

    def service(self):
        if self._service is None:
            from google.oauth2.credentials import Credentials
            from googleapiclient.discovery import build
            creds = Credentials(
                None,
                refresh_token=self.refresh_token,
                client_id=self.client_id,
                client_secret=self.client_secret,
                token_uri="https://oauth2.googleapis.com/token",
                scopes=["https://www.googleapis.com/auth/drive"],
            )
            self._service = build("drive", "v3", credentials=creds, cache_discovery=False)
        return self._service

    def has_room(self, incoming_bytes):
        """True unless the Google account is (nearly) out of storage. Checked at most every 5 min."""
        import time
        now = time.time()
        if self._quota is None or now - self._quota_checked_at > USAGE_CACHE_SECONDS:
            about = self.service().about().get(fields="storageQuota").execute()
            self._quota = about.get("storageQuota", {})
            self._quota_checked_at = now
        limit = self._quota.get("limit")
        if not limit:  # no limit reported (unlimited plan)
            return True
        return int(self._quota.get("usage", 0)) + incoming_bytes + self.SAFETY_MARGIN <= int(limit)

    def upload(self, filename, binary, mimetype="image/jpeg"):
        from googleapiclient.http import MediaIoBaseUpload
        media = MediaIoBaseUpload(io.BytesIO(binary), mimetype=mimetype, resumable=False)
        self.service().files().create(
            body={"name": filename, "parents": [self.folder_id]},
            media_body=media, fields="id",
        ).execute()
        if self._quota is not None:
            self._quota["usage"] = int(self._quota.get("usage", 0)) + len(binary)


# ─────────────────────────────────────────────────────────────
# Storage chain: Google Drive first, then Cloudflare R2, then Backblaze B2
# ─────────────────────────────────────────────────────────────
# R2 and B2 are S3-compatible, so one class handles both. Each photo goes to the
# first backend that is configured, has room, and works. If Drive is full or
# failing, the app moves on to R2, and then B2, automatically.
#
# R2 env vars:  R2_ACCOUNT_ID, R2_ACCESS_KEY_ID, R2_SECRET_ACCESS_KEY, R2_BUCKET
# B2 env vars:  B2_ENDPOINT, B2_KEY_ID, B2_APPLICATION_KEY, B2_BUCKET
# Optional caps (in GB): R2_MAX_GB, B2_MAX_GB  (default 9.5, just under the free 10 GB)

USAGE_CACHE_SECONDS = 300


class S3Backend:
    def __init__(self, name, endpoint, key_id, secret, bucket, max_gb, region="auto"):
        self.name = name
        self.endpoint = endpoint
        self.key_id = key_id
        self.secret = secret
        self.bucket = bucket
        self.max_bytes = int(float(max_gb) * 1024 ** 3)
        self.region = region
        self._client = None
        self._used_bytes = None
        self._used_checked_at = 0

    @property
    def configured(self):
        return all([self.endpoint, self.key_id, self.secret, self.bucket])

    def client(self):
        if self._client is None:
            import boto3
            from botocore.config import Config
            self._client = boto3.client(
                "s3",
                endpoint_url=self.endpoint,
                aws_access_key_id=self.key_id,
                aws_secret_access_key=self.secret,
                region_name=self.region,
                config=Config(retries={"max_attempts": 2}, connect_timeout=8, read_timeout=20),
            )
        return self._client

    def used_bytes(self):
        """Total size of the bucket, cached briefly so we don't list it on every upload."""
        import time
        now = time.time()
        if self._used_bytes is None or now - self._used_checked_at > USAGE_CACHE_SECONDS:
            total = 0
            paginator = self.client().get_paginator("list_objects_v2")
            for page in paginator.paginate(Bucket=self.bucket):
                for obj in page.get("Contents", []):
                    total += obj["Size"]
            self._used_bytes = total
            self._used_checked_at = now
        return self._used_bytes

    def has_room(self, incoming_bytes):
        return self.used_bytes() + incoming_bytes <= self.max_bytes

    def upload(self, filename, binary, mimetype="image/jpeg"):
        self.client().put_object(
            Bucket=self.bucket, Key=filename, Body=binary, ContentType=mimetype
        )
        if self._used_bytes is not None:
            self._used_bytes += len(binary)


def _build_backends():
    env = os.environ.get
    r2_account = env("R2_ACCOUNT_ID")
    return [
        DriveBackend(),
        S3Backend(
            "Cloudflare R2",
            f"https://{r2_account}.r2.cloudflarestorage.com" if r2_account else None,
            env("R2_ACCESS_KEY_ID"), env("R2_SECRET_ACCESS_KEY"), env("R2_BUCKET"),
            env("R2_MAX_GB", "9.5"), region="auto",
        ),
        S3Backend(
            "Backblaze B2",
            env("B2_ENDPOINT"),
            env("B2_KEY_ID"), env("B2_APPLICATION_KEY"), env("B2_BUCKET"),
            env("B2_MAX_GB", "9.5"), region=env("B2_REGION", "us-west-004"),
        ),
    ]


STORAGE_CHAIN = _build_backends()


def store_in_cloud(filename, binary, mimetype="image/jpeg"):
    """Try each configured backend in order (Drive, R2, B2). Returns its name, or None."""
    for backend in STORAGE_CHAIN:
        if not backend.configured:
            continue
        try:
            if not backend.has_room(len(binary)):
                logger.warning("%s is at its size cap — moving to the next backend.", backend.name)
                continue
            backend.upload(filename, binary, mimetype)
            return backend.name
        except Exception:
            logger.exception("%s upload failed — trying the next backend.", backend.name)
    return None


app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "change-this-to-any-random-string")  # needed for login session

UPLOAD_FOLDER = os.path.join(app.static_folder, "uploads")
os.makedirs(UPLOAD_FOLDER, exist_ok=True)


def login_required(f):
    @wraps(f)
    def wrapped(*args, **kwargs):
        if not session.get("gallery_ok"):
            return redirect(url_for("gallery_login", next=request.path))
        return f(*args, **kwargs)
    return wrapped


@app.errorhandler(Exception)
def handle_error(e):
    """Return the real error as JSON (and log it) instead of a blank 500 page."""
    if isinstance(e, HTTPException):
        return e
    logger.exception("Unhandled error")
    return jsonify({"ok": False, "error": f"{type(e).__name__}: {e}"}), 500


@app.route("/drive-test")
@login_required
def drive_test():
    """Log in at /gallery/login, then open /drive-test to see the exact Google Drive error."""
    d = STORAGE_CHAIN[0]
    if not d.configured:
        return ("Missing one of GOOGLE_CLIENT_ID / GOOGLE_CLIENT_SECRET / "
                "GOOGLE_REFRESH_TOKEN / GDRIVE_FOLDER_ID in Render's Environment tab"), 500
    try:
        d.upload("drive-test.txt", b"hello", "text/plain")
        return "Drive OK. Check your Drive folder for drive-test.txt"
    except Exception as e:
        logger.exception("Drive test failed")
        return f"Drive FAILED: {type(e).__name__}: {e}", 500


@app.route("/")
def camera():
    """The page guests land on after scanning the QR code."""
    intro = WEDDING.get("intro_video")
    if intro and not os.path.exists(os.path.join(app.static_folder, intro)):
        intro = None  # no video file yet -> fall back to the camera illustration
    return render_template("index.html", wedding=WEDDING, filter=BUILT_IN_FILTER, intro_video=intro)


@app.route("/upload", methods=["POST"])
def upload():
    data = request.get_json(silent=True)
    if not data or "image" not in data:
        return jsonify({"ok": False, "error": "No image received"}), 400

    image_data = data["image"]
    guest_name = (data.get("guest_name") or "Guest").strip()[:40]
    guest_name = "".join(c for c in guest_name if c.isalnum() or c in " -_").strip() or "Guest"

    try:
        header, encoded = image_data.split(",", 1)
        binary = base64.b64decode(encoded)
    except Exception:
        return jsonify({"ok": False, "error": "Malformed image data"}), 400

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    filename = f"{timestamp}_{guest_name.replace(' ', '_')}.jpg"
    filepath = os.path.join(UPLOAD_FOLDER, filename)

    # Local copy powers the live in-event gallery view.
    with open(filepath, "wb") as f:
        f.write(binary)

    # Permanent copy: Google Drive first, then R2, then B2 (first one that works).
    # The local copy above only powers the live /gallery view.
    stored_in = store_in_cloud(filename, binary, mimetype="image/jpeg")

    return jsonify({"ok": True, "filename": filename, "cloud_storage": stored_in})


@app.route("/gallery/login", methods=["GET", "POST"])
def gallery_login():
    error = None
    if request.method == "POST":
        if request.form.get("passcode", "") == GALLERY_PASSCODE:
            session["gallery_ok"] = True
            return redirect(request.args.get("next") or url_for("gallery"))
        error = "That passcode isn't right — try again."
    return render_template("login.html", wedding=WEDDING, error=error)


@app.route("/gallery/logout")
def gallery_logout():
    session.pop("gallery_ok", None)
    return redirect(url_for("gallery_login"))


@app.route("/gallery")
@login_required
def gallery():
    files = sorted(os.listdir(UPLOAD_FOLDER), reverse=True)
    photos = [f for f in files if f.lower().endswith((".jpg", ".jpeg", ".png")) and not f.startswith(".")]
    return render_template("gallery.html", wedding=WEDDING, photos=photos, count=len(photos))


@app.route("/gallery/download-all")
@login_required
def download_all():
    files = [f for f in os.listdir(UPLOAD_FOLDER) if f.lower().endswith((".jpg", ".jpeg", ".png"))]
    if not files:
        abort(404)
    mem = io.BytesIO()
    with zipfile.ZipFile(mem, "w", zipfile.ZIP_DEFLATED) as zf:
        for fname in files:
            zf.write(os.path.join(UPLOAD_FOLDER, fname), arcname=fname)
    mem.seek(0)
    zip_name = f"{WEDDING['partner_1']}-{WEDDING['partner_2']}-photos.zip".replace(" ", "")
    return send_file(mem, mimetype="application/zip", as_attachment=True, download_name=zip_name)


@app.route("/qr.png")
def qr_code():
    """A scannable QR code that points guests at the camera page."""
    target_url = request.url_root
    img = qrcode.make(target_url)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return send_file(buf, mimetype="image/png")


if __name__ == "__main__":
    # host=0.0.0.0 so phones on the same wifi (or via a tunnel) can reach it
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)), debug=False)
