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
    raise ValueError("HUBSPOT_ACCESS_TOKEN environment variable is required. Please check your .env file.")

app = Flask(__name__)

# Configure Flask from environment variables
app.config['MAX_CONTENT_LENGTH'] = int(os.getenv('MAX_CONTENT_LENGTH', 16777216))  # 16MB default

# Store uploaded files in memory (in production, use a proper file storage system)
uploaded_files = {}

def add_cors_headers(response):
    """Add CORS headers to response"""
    response.headers.add('Access-Control-Allow-Origin', 'https://hubspot-image-fe.vercel.app')
    response.headers.add('Access-Control-Allow-Headers', 'Content-Type, Authorization')
    response.headers.add('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
    return response

# Fix CORS configuration
CORS(app, 
     resources={r"/*": {"origins": ["http://localhost:3000", "http://127.0.0.1:3000", "https://hubspot-image-fe.vercel.app"]}},
     allow_headers=["Content-Type", "Authorization"],
     methods=["GET", "POST", "OPTIONS"])

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

@app.route('/upload', methods=['POST', 'OPTIONS'])
def upload_file():
    # Handle preflight OPTIONS request
    if request.method == 'OPTIONS':
        response = jsonify({'status': 'ok'})
        response.headers.add('Access-Control-Allow-Origin', 'https://hubspot-image-fe.vercel.app')
        response.headers.add('Access-Control-Allow-Headers', 'Content-Type')
        response.headers.add('Access-Control-Allow-Methods', 'POST')
        return response
    
    try:
        file = request.files['file']
        if not file:
            return jsonify({'error': 'No file uploaded'}), 400

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
            return jsonify({'error': 'Unsupported file format'}), 400

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

def generate_images_stream(df, selected_columns):
    """Generator function to stream images one by one"""
    count = 0
    total_count = 0
    errors = []
    
    # Count total images first
    for col in selected_columns:
        if col in df.columns:
            total_count += len(df[col].dropna())
    
    yield f"data: {json.dumps({'type': 'start', 'total': total_count})}\n\n"
    
    for col in selected_columns:
        if col not in df.columns:
            error_msg = f"Column '{col}' not found in file"
            errors.append(error_msg)
            yield f"data: {json.dumps({'type': 'error', 'message': error_msg})}\n\n"
            continue
            
        for idx, signed_url in df[col].dropna().items():
            try:
                if pd.isna(signed_url) or not str(signed_url).strip():
                    continue
                    
                url_str = str(signed_url).strip()
                count += 1
                
                # Send progress update
                yield f"data: {json.dumps({'type': 'progress', 'current': count, 'total': total_count, 'column': col})}\n\n"
                
                # Download image data
                image_info = download_file_from_hubspot(url_str)
                if image_info:
                    filename = f"{secure_filename(col)}_{str(count).zfill(3)}.{image_info['extension']}"
                    
                    # Send image data
                    image_data = {
                        'type': 'image',
                        'column': col,
                        'filename': filename,
                        'data': image_info['data'],
                        'size': image_info['size'],
                        'current': count,
                        'total': total_count
                    }
                    yield f"data: {json.dumps(image_data)}\n\n"
                else:
                    count -= 1  # rollback if failed
                    error_msg = f"Failed to download from {url_str}"
                    errors.append(error_msg)
                    yield f"data: {json.dumps({'type': 'error', 'message': error_msg})}\n\n"
                    
            except Exception as e:
                error_msg = f"Error processing {signed_url}: {str(e)}"
                errors.append(error_msg)
                yield f"data: {json.dumps({'type': 'error', 'message': error_msg})}\n\n"
                count -= 1
    
    # Send completion message
    yield f"data: {json.dumps({'type': 'complete', 'total_downloaded': count, 'errors': errors[:10]})}\n\n"

@app.route('/download-images-stream', methods=['POST', 'OPTIONS'])
def download_images_stream():
    # Handle preflight OPTIONS request
    if request.method == 'OPTIONS':
        response = jsonify({'status': 'ok'})
        response.headers.add('Access-Control-Allow-Origin', 'https://hubspot-image-fe.vercel.app')
        response.headers.add('Access-Control-Allow-Headers', 'Content-Type')
        response.headers.add('Access-Control-Allow-Methods', 'POST')
        return response
    
    try:
        # Get the file from the request
        file = request.files.get('file')
        if not file:
            return jsonify({'error': 'No file provided'}), 400

        # Get form data
        columns_data = request.form.get('columns')
        if not columns_data:
            return jsonify({'error': 'Missing required parameters'}), 400

        # Parse selected columns
        try:
            selected_columns = json.loads(columns_data) if isinstance(columns_data, str) else columns_data
        except:
            return jsonify({'error': 'Invalid columns format'}), 400

        # Process file in memory
        ext = os.path.splitext(file.filename)[1].lower()
        file_stream = io.BytesIO(file.read())
        
        if ext == ".csv":
            df = pd.read_csv(file_stream)
        elif ext in [".xls", ".xlsx"]:
            df = pd.read_excel(file_stream)
        else:
            return jsonify({'error': 'Unsupported file format'}), 400

        # Return Server-Sent Events stream
        return Response(
            generate_images_stream(df, selected_columns),
            mimetype='text/event-stream',
            headers={
                'Cache-Control': 'no-cache',
                'Connection': 'keep-alive',
                'Access-Control-Allow-Origin': 'http://localhost:3000',
                'Access-Control-Allow-Credentials': 'true'
            }
        )

    except Exception as e:
        print(f"Download stream error: {e}")
        return jsonify({'error': f'Download failed: {str(e)}'}), 500

# Keep the original endpoint for backward compatibility
@app.route('/download-images', methods=['POST', 'OPTIONS'])
def download_images():
    # Handle preflight OPTIONS request
    if request.method == 'OPTIONS':
        response = jsonify({'status': 'ok'})
        response.headers.add('Access-Control-Allow-Origin', 'https://hubspot-image-fe.vercel.app')
        response.headers.add('Access-Control-Allow-Headers', 'Content-Type')
        response.headers.add('Access-Control-Allow-Methods', 'POST')
        return response
    
    try:
        # Get JSON data from request
        data = request.get_json()
        
        if not data:
            return jsonify({'error': 'No data provided'}), 400

        filename = data.get('filename')
        selected_columns = data.get('columns', [])
        download_path = data.get('downloadPath', '')

        if not filename or not selected_columns:
            return jsonify({'error': 'Missing required parameters'}), 400

        # Handle default downloads folder
        if download_path == 'downloads':
            # Use the user's default downloads folder
            downloads_path = os.path.expanduser('~/Downloads')
            download_path = os.path.join(downloads_path, 'hubspot-images')
        else:
            # Use the provided path
            if not download_path:
                return jsonify({'error': 'Download path is required'}), 400

        # Create download directory if it doesn't exist
        try:
            os.makedirs(download_path, exist_ok=True)
        except Exception as e:
            return jsonify({'error': f'Cannot create download directory: {str(e)}'}), 400

        # Get the stored file data
        if filename not in uploaded_files:
            return jsonify({'error': 'File not found. Please upload the file again.'}), 400

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

# Add a health check endpoint
@app.route('/health', methods=['GET'])
def health_check():
    response = jsonify({'status': 'healthy', 'message': 'HubSpot Image Downloader API is running'})
    return add_cors_headers(response)

if __name__ == '__main__':
    # Validate environment setup
    if not ACCESS_TOKEN:
        print("❌ ERROR: HUBSPOT_ACCESS_TOKEN is not set!")

    print("🔐 Environment variables loaded successfully")
    
    debug_mode = os.getenv('FLASK_DEBUG', 'True').lower() == 'true'
    app.run(host='127.0.0.1', port=5000, debug=debug_mode)