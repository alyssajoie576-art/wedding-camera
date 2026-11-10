// Wedding Camera uploader: saves each photo into your Google Drive folder.
// 1) Replace the two values below. 2) Deploy as a Web app (see README / chat steps).

const FOLDER_ID = 'PASTE_YOUR_FOLDER_ID_HERE';
const SECRET = 'PASTE_A_LONG_RANDOM_PASSWORD_HERE';   // must match APPS_SCRIPT_SECRET on Render

function doPost(e) {
  try {
    const d = JSON.parse(e.postData.contents);
    if (d.secret !== SECRET) return reply({ ok: false, error: 'wrong secret' });
    const blob = Utilities.newBlob(
      Utilities.base64Decode(d.data), d.mimeType || 'image/jpeg', d.filename || ('photo_' + Date.now() + '.jpg'));
    DriveApp.getFolderById(FOLDER_ID).createFile(blob);
    return reply({ ok: true });
  } catch (err) {
    return reply({ ok: false, error: String(err) });
  }
}

// Opening the web app link in a browser should show this message.
function doGet() {
  return reply({ ok: true, message: 'Wedding camera uploader is running' });
}

// Run this once from the editor so Google asks you for permission.
function authorize() {
  Logger.log('Folder found: ' + DriveApp.getFolderById(FOLDER_ID).getName());
}

function reply(obj) {
  return ContentService.createTextOutput(JSON.stringify(obj)).setMimeType(ContentService.MimeType.JSON);
}
