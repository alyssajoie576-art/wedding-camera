# Guest Wedding Photobooth

A tiny Flask app: guests scan a QR code → see a personalized camera with your
photo on the lens → tap anywhere → it flips open into a live viewfinder →
tap to snap → the photo auto-saves (fixed filter + timestamp baked in, no
choices for guests) straight to a shared album **and** to your Google Drive.

100% free to run — no paid services required (Google Drive storage is also free,
up to your account's normal Drive quota).

---

## 1. Personalize it

Open `app.py` and edit the block at the top:

```python
WEDDING = {
    "partner_1": "Amelia",
    "partner_2": "Daniel",
    "date": "October 3, 2026",
    "venue": "The Old Orchard Barn",
    "hashtag": "#AmeliaAndDaniel2026",
    "welcome_message": "Help us capture today from every angle...",
    "couple_photo": "couple.jpg",   # see step 1b below
}
GALLERY_PASSCODE = "ourwedding2026"   # what the couple types in to see photos
```

Also update `PARTNER_1` / `PARTNER_2` at the top of `generate_qr_card.py` to match.

### 1b. Add your photo to the camera

Drop a photo of the two of you at `static/couple.jpg` (a square-ish crop looks
best — it sits inside a circular lens). If you'd rather use a different
filename, just update `"couple_photo"` above to match. If no photo is found,
guests just see a heart icon instead — nothing breaks.

### 1c. The built-in look

Every photo automatically gets one fixed filter plus a burned-in date/time
stamp — guests can't change either. Edit it in `app.py`:

```python
BUILT_IN_FILTER = {
    "label": "Vintage",
    "css": "sepia(0.35) contrast(1.1) brightness(0.95) saturate(1.3)",
}
```
Any valid CSS `filter` value works (e.g. `"grayscale(1) contrast(1.05)"` for black & white).

## 2. Run it locally to test

```bash
pip install -r requirements.txt
python app.py
```

Visit `http://localhost:5000` on your computer to see the camera page, and
`http://localhost:5000/gallery` (passcode-protected) to see the album.

To test on your **phone** before the wedding, connect your phone to the same
WiFi as your computer, then visit `http://YOUR-COMPUTER-IP:5000` (find your
IP with `ipconfig`/`ifconfig`).

## 2b. Set up Google Drive backup (recommended — this is what makes photos permanent)

Free hosts like Render's free tier wipe their disk periodically, which is
why photos can vanish after a few days if you rely on local storage alone.
Google Drive is a separate, durable place for photos to land. One-time setup:

1. Go to [console.cloud.google.com](https://console.cloud.google.com) and create a new project (any name).
2. In "APIs & Services" → "Library", search for **Google Drive API** and click **Enable**.
3. Go to "APIs & Services" → "Credentials" → **Create Credentials** → **Service account**. Give it any name, click through the defaults, then **Done**.
4. Click into the new service account → **Keys** tab → **Add Key** → **Create new key** → **JSON**. This downloads a `.json` file — keep it private, don't commit it to GitHub.
5. In Google Drive, create a folder for wedding photos (e.g. "Amelia & Daniel Wedding Photos"). Right-click it → **Share** → paste the service account's email address (it looks like `something@your-project.iam.gserviceaccount.com`, found inside the JSON file or on the service account's page) → give it **Editor** access.
6. Open the folder in your browser and copy the folder ID from the URL: `https://drive.google.com/drive/folders/`**`THIS_PART`**.
7. Set two environment variables wherever you host the app (see step 3 — most hosts have an "Environment" tab in their dashboard):
   - `GDRIVE_FOLDER_ID` → the folder ID from step 6
   - `GOOGLE_SERVICE_ACCOUNT_JSON` → paste the **entire contents** of the JSON file you downloaded in step 4 (as one line)

That's it — once both variables are set, every photo guests take is uploaded
to that Drive folder automatically, in addition to the shared in-app album.
If you skip this section, the app still works fine; photos just stay local
only, which isn't durable long-term on most free hosts.

## 2c. Optional: automatic storage failover (Cloudflare R2 → Backblaze B2)

Photos go to Cloudflare R2 first. When R2 reaches its size cap (default 9.5 GB,
just under the free 10 GB) or an upload to it fails, the app switches to
Backblaze B2 automatically. R2 never refuses uploads on its own — it just
starts billing past 10 GB — so the cap is what keeps you free. You can set
either service up alone; unconfigured ones are skipped.

**Cloudflare R2** — create a bucket, then an API token with read/write access
to it (R2 → Manage API Tokens). Set these environment variables:
`R2_ACCOUNT_ID`, `R2_ACCESS_KEY_ID`, `R2_SECRET_ACCESS_KEY`, `R2_BUCKET`

**Backblaze B2** — create a private bucket and an application key limited to
it (App Keys). Set: `B2_ENDPOINT` (the bucket's S3 endpoint, e.g.
`https://s3.us-west-004.backblazeb2.com`), `B2_KEY_ID`, `B2_APPLICATION_KEY`,
`B2_BUCKET`, and `B2_REGION` (the region part of that endpoint, e.g. `us-west-004`).

Optional: `R2_MAX_GB` / `B2_MAX_GB` change the caps (default 9.5 each).
The upload response and server logs show which service each photo landed in.
This runs alongside Google Drive (2b) — use either, both, or neither.

## 3. Get it online for the wedding day (free options)

Guests need a public link to scan. Pick whichever feels easiest:

**Option A — Render.com (recommended, stays up permanently, free tier)**
1. Push this folder to a GitHub repo.
2. Go to render.com → New → Web Service → connect your repo.
3. Build command: `pip install -r requirements.txt`
   Start command: `gunicorn app:app` (add `gunicorn` to requirements.txt first)
4. Deploy — Render gives you a free `https://yourapp.onrender.com` URL.
   That's the link guests will scan.

**Option B — ngrok (fastest, great for a single-day event)**
1. Install ngrok (free account, free tier): https://ngrok.com/download
2. Run your app locally: `python app.py`
3. In another terminal: `ngrok http 5000`
4. ngrok gives you a temporary public `https://xxxx.ngrok-free.app` URL —
   use that for your QR code. Keep your laptop running & connected to power
   and internet during the event.

**Option C — PythonAnywhere (free tier, persistent, slightly more setup)**
Good if you want something that stays online without keeping your own
laptop running. Their free plan supports Flask apps with HTTPS out of the box.

> Note: some phone browsers restrict camera access to secure (https)
> pages — all three options above give you https, so you're covered.

## 4. Generate the printable QR card

Once you have your public URL from step 3:

```bash
python generate_qr_card.py https://yourapp.onrender.com
```

This creates `qr_card.png` — print it (4x6" or bigger works well) and place
it on tables, at the guestbook, or on a stand near the venue entrance.

You can also just visit `https://yourapp.onrender.com/qr.png` any time to
grab a quick QR image pointed at whatever URL the app is currently running on.

## 5. On the day

- Guests scan the code → see your photo on a personalized camera → tap
  anywhere → it flips open into a live viewfinder → tap anywhere to snap →
  the photo saves itself automatically (fixed filter + timestamp, no
  choices, no retake/confirm step) and the page resets for the next guest.
- The bride and groom (or a designated helper) can browse everything in
  Google Drive directly, or visit `/gallery` for a live in-app view during
  the event and tap "Download All" for a zip.

## Notes & tweaks

- The fixed filter is applied via canvas + a CSS filter string — change it
  in the `BUILT_IN_FILTER` dict in `app.py`. The timestamp is drawn directly
  onto the photo in `templates/index.html` (`stampTimestamp` function).
- Local copies in `static/uploads/` power the live `/gallery` view during
  the event, but aren't guaranteed to persist on free hosting — Google Drive
  (step 2b) is the permanent archive.
- Guests can tap the small ⟳ button in the top-right of the viewfinder to
  switch between front and back camera.
