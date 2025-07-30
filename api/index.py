from flask import Flask, request, jsonify, Response
from flask_cors import CORS
from werkzeug.utils import secure_filename
import os
import io
import pandas as pd
import requests
import urllib.parse
from dotenv import load_dotenv
import base64
import json
from datetime import datetime

# Load environment variables from .env file
load_dotenv()

# Get access token from environment variable
ACCESS_TOKEN = os.getenv('HUBSPOT_ACCESS_TOKEN')

if not ACCESS_TOKEN:
    print("⚠️  WARNING: HUBSPOT_ACCESS_TOKEN is not set!")

app = Flask(__name__)

# Configure Flask from environment variables
app.config['MAX_CONTENT_LENGTH'] = int(os.getenv('MAX_CONTENT_LENGTH', 16777216))  # 16MB default

# Store uploaded files in memory (in production, use a proper file storage system)
uploaded_files = {}

# CORS configuration
CORS(app, resources={r"/*": {"origins": "*"}})

def add_cors_headers(response):
    """Add CORS headers to response"""
    response.headers.add('Access-Control-Allow-Origin', '*')
    response.headers.add('Access-Control-Allow-Headers', 'Content-Type, Authorization')
    response.headers.add('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
    return response

def get_file_id_from_url(signed_url):
    parsed = urllib.parse.urlparse(signed_url)
    parts = parsed.path.strip("/").split("/")
    if "signed-url-redirect" in parts:
        try:
            idx = parts.index("signed-url-redirect")
            return parts[idx + 1]
        except IndexError:
            return None
    return None

def get_extension_from_url(url):
    parsed = urllib.parse.urlparse(url)
    path = parsed.path
    ext = os.path.splitext(path)[-1].lstrip('.')
    return ext if ext else "jpg"

def download_file_from_hubspot(signed_url):
    """Download file and return base64 encoded data with metadata"""
    if not ACCESS_TOKEN:
        return None
        
    file_id = get_file_id_from_url(signed_url)
    if not file_id:
        return None

    headers = {
        "Authorization": f"Bearer {ACCESS_TOKEN}"
    }

    try:
        # Get signed URL
        api_url = f"https://api.hubapi.com/files/v3/files/{file_id}/signed-url"
        response = requests.get(api_url, headers=headers, timeout=30)
        if response.status_code != 200:
            return None

        signed_download_url = response.json().get("url")
        if not signed_download_url:
            return None

        # Download image
        img_response = requests.get(signed_download_url, timeout=30)
        if img_response.status_code == 200:
            # Convert to base64
            image_data = base64.b64encode(img_response.content).decode('utf-8')
            extension = get_extension_from_url(signed_url)
            
            return {
                'data': image_data,
                'extension': extension,
                'size': len(img_response.content)
            }
        else:
            return None
    except Exception as e:
        print(f"❌ Error downloading file_id {file_id}: {e}")
        return None

@app.route('/health', methods=['GET'])
def health_check():
    response = jsonify({'status': 'healthy', 'message': 'HubSpot Image Downloader API is running'})
    return add_cors_headers(response)

@app.route('/test', methods=['GET'])
def test():
    response = jsonify({'message': 'Backend is working!', 'timestamp': datetime.now().isoformat()})
    return add_cors_headers(response)

@app.route('/', methods=['GET'])
def root():
    response = jsonify({
        'message': 'HubSpot Image Downloader API',
        'status': 'running',
        'endpoints': ['/upload', '/download-images', '/health', '/test'],
        'timestamp': datetime.now().isoformat()
    })
    return add_cors_headers(response)

@app.route('/upload', methods=['POST', 'OPTIONS'])
def upload_file():
    if request.method == 'OPTIONS':
        response = jsonify({'status': 'ok'})
        return add_cors_headers(response)
    
    try:
        file = request.files['file']
        if not file:
            response = jsonify({'error': 'No file uploaded'})
            return add_cors_headers(response), 400

        filename = secure_filename(file.filename)
        extension = os.path.splitext(filename)[1].lower()

        # Process file in memory and store it
        file_content = file.read()
        file_stream = io.BytesIO(file_content)

        if extension == ".csv":
            df = pd.read_csv(file_stream)
        elif extension in [".xls", ".xlsx"]:
            df = pd.read_excel(file_stream)
        else:
            response = jsonify({'error': 'Unsupported file format'})
            return add_cors_headers(response), 400

        # Store the file data for later use
        uploaded_files[filename] = {
            'content': file_content,
            'extension': extension,
            'dataframe': df
        }

        columns = df.columns.tolist()
        response = jsonify({'columns': columns, 'filename': filename})
        return add_cors_headers(response)

    except Exception as e:
        print(f"Upload error: {e}")
        response = jsonify({'error': f'Upload failed: {str(e)}'})
        return add_cors_headers(response), 500

@app.route('/download-images', methods=['POST', 'OPTIONS'])
def download_images():
    if request.method == 'OPTIONS':
        response = jsonify({'status': 'ok'})
        return add_cors_headers(response)
    
    try:
        # Get JSON data from request
        data = request.get_json()
        
        if not data:
            response = jsonify({'error': 'No data provided'})
            return add_cors_headers(response), 400

        filename = data.get('filename')
        selected_columns = data.get('columns', [])
        download_path = data.get('downloadPath', '')

        if not filename or not selected_columns:
            response = jsonify({'error': 'Missing required parameters'})
            return add_cors_headers(response), 400

        # Handle default downloads folder
        if download_path == 'downloads':
            # Use the user's default downloads folder
            downloads_path = os.path.expanduser('~/Downloads')
            download_path = os.path.join(downloads_path, 'hubspot-images')
        else:
            # Use the provided path
            if not download_path:
                response = jsonify({'error': 'Download path is required'})
                return add_cors_headers(response), 400

        # Create download directory if it doesn't exist
        try:
            os.makedirs(download_path, exist_ok=True)
        except Exception as e:
            response = jsonify({'error': f'Cannot create download directory: {str(e)}'})
            return add_cors_headers(response), 400

        # Get the stored file data
        if filename not in uploaded_files:
            response = jsonify({'error': 'File not found. Please upload the file again.'})
            return add_cors_headers(response), 400

        file_data = uploaded_files[filename]
        df = file_data['dataframe']

        count = 0
        successful_downloads = []
        errors = []

        for col in selected_columns:
            if col not in df.columns:
                errors.append(f"Column '{col}' not found in file")
                continue
                
            # Create column directory inside the main download folder
            column_dir = os.path.join(download_path, secure_filename(col))
            try:
                os.makedirs(column_dir, exist_ok=True)
            except Exception as e:
                errors.append(f"Cannot create directory for column '{col}': {str(e)}")
                continue
            
            for idx, signed_url in df[col].dropna().items():
                try:
                    if pd.isna(signed_url) or not str(signed_url).strip():
                        continue
                        
                    url_str = str(signed_url).strip()
                    count += 1
                    
                    # Download image data
                    image_info = download_file_from_hubspot(url_str)
                    if image_info:
                        filename = f"{secure_filename(col)}_{str(count).zfill(3)}.{image_info['extension']}"
                        file_path = os.path.join(column_dir, filename)
                        
                        # Save image to file
                        try:
                            with open(file_path, 'wb') as f:
                                f.write(base64.b64decode(image_info['data']))
                            successful_downloads.append({
                                'column': col,
                                'filename': filename,
                                'path': file_path,
                                'size': image_info['size']
                            })
                        except Exception as e:
                            errors.append(f"Failed to save {filename}: {str(e)}")
                            count -= 1
                    else:
                        count -= 1  # rollback if failed
                        errors.append(f"Failed to download from {url_str}")
                except Exception as e:
                    errors.append(f"Error processing {signed_url}: {str(e)}")
                    count -= 1

        if successful_downloads:
            response = jsonify({
                'success': True,
                'message': f'{len(successful_downloads)} images downloaded successfully to Downloads/hubspot-images/',
                'total_images': len(successful_downloads),
                'download_path': download_path,
                'errors': errors[:10]  # Limit errors shown
            })
            return add_cors_headers(response)
        else:
            response = jsonify({
                'success': False,
                'error': 'Please try different columns.',
                'total_images': 0
            })
            return add_cors_headers(response), 400

    except Exception as e:
        print(f"Download error: {e}")
        response = jsonify({'error': f'Download failed: {str(e)}'})
        return add_cors_headers(response), 500

# For Vercel serverless
if __name__ == '__main__':
    app.run(debug=True)