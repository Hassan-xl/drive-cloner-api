from flask import Flask, request, jsonify
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
import os
import re

app = Flask(__name__)

SCOPES = ['https://www.googleapis.com/auth/drive']
CLIENT_SECRET_FILE = 'client_secret_379893520226-1hla1a0tgqp21aavuircrftmemrrc9lo.apps.googleusercontent.com.json'
TOKEN_FILE = 'token.json'


def get_drive_service():
    creds = None
    if os.path.exists(TOKEN_FILE):
        creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(CLIENT_SECRET_FILE, SCOPES)
            creds = flow.run_local_server(port=0)
        with open(TOKEN_FILE, 'w') as token:
            token.write(creds.to_json())
    return build('drive', 'v3', credentials=creds)


def extract_id(url_or_id):
    match = re.search(r"/folders/([a-zA-Z0-9_-]+)", url_or_id)
    if match:
        return match.group(1)
    return url_or_id.strip()


def list_files(service, folder_id):
    files = []
    page_token = None
    while True:
        response = service.files().list(
            q=f"'{folder_id}' in parents and trashed=false",
            supportsAllDrives=True,
            includeItemsFromAllDrives=True,
            fields="nextPageToken, files(id, name, mimeType)",
            pageToken=page_token
        ).execute()
        files.extend(response.get('files', []))
        page_token = response.get('nextPageToken')
        if not page_token:
            break
    return files


def copy_file(service, file_id, name, parent_id):
    copied_file = {'name': name, 'parents': [parent_id]}
    return service.files().copy(
        fileId=file_id,
        body=copied_file,
        supportsAllDrives=True,
        fields='id'
    ).execute().get('id')


def create_folder(service, name, parent_id=None):
    metadata = {'name': name, 'mimeType': 'application/vnd.google-apps.folder'}
    if parent_id:
        metadata['parents'] = [parent_id]
    return service.files().create(
        body=metadata,
        fields='id',
        supportsAllDrives=True
    ).execute().get('id')


def clone_folder_recursive(service, src_folder_id, dest_parent_id, new_root_name):
    new_folder_id = create_folder(service, new_root_name, dest_parent_id)
    items = list_files(service, src_folder_id)
    for item in items:
        if item['mimeType'] == 'application/vnd.google-apps.folder':
            clone_folder_recursive(service, item['id'], new_folder_id, item['name'])
        else:
            copy_file(service, item['id'], item['name'], new_folder_id)
    return new_folder_id


@app.route("/clone-folder", methods=["POST"])
def clone_endpoint():
    data = request.get_json()
    template_id = data.get("template_folder_id")
    new_name = data.get("new_name", "Client Folder")

    if not template_id:
        return jsonify({"error": "Missing template_folder_id"}), 400

    try:
        service = get_drive_service()
        src_id = extract_id(template_id)
        new_id = clone_folder_recursive(service, src_id, None, new_name)
        url = f"https://drive.google.com/drive/folders/{new_id}"
        return jsonify({"status": "success", "folder_url": url}), 200
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


#if __name__ == "__main__":
   # app.run(host="0.0.0.0", port=5000)
