from flask import Flask, request, jsonify
from flask_cors import CORS
from werkzeug.utils import secure_filename
import os
import io
import csv
import json
import requests
import urllib.parse
import base64
from datetime import datetime
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Get access token from environment variable
ACCESS_TOKEN = os.getenv('HUBSPOT_ACCESS_TOKEN')

if not ACCESS_TOKEN:
    print("⚠️  WARNING: HUBSPOT_ACCESS_TOKEN is not set!")

app = Flask(__name__)

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
    """Extract file ID from HubSpot signed URL"""
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
    """Get file extension from URL"""
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

@app.route('/test-download', methods=['GET'])
def test_download():
    """Test endpoint to verify download functionality"""
    try:
        # Create a simple test image (1x1 pixel PNG)
        test_image_data = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg=="
        
        response = jsonify({
            'success': True,
            'images': [{
                'column': 'test',
                'filename': 'test_image.png',
                'data': test_image_data,
                'extension': 'png',
                'size': 95
            }]
        })
        return add_cors_headers(response)
    except Exception as e:
        response = jsonify({'error': f'Test failed: {str(e)}'})
        return add_cors_headers(response), 500

@app.route('/test-upload', methods=['POST', 'OPTIONS'])
def test_upload():
    if request.method == 'OPTIONS':
        response = jsonify({'status': 'ok'})
        return add_cors_headers(response)
    
    try:
        response = jsonify({
            'message': 'Test upload endpoint working',
            'content_type': request.content_type,
            'has_files': 'file' in request.files,
            'timestamp': datetime.now().isoformat()
        })
        return add_cors_headers(response)
    except Exception as e:
        response = jsonify({'error': f'Test failed: {str(e)}'})
        return add_cors_headers(response), 500

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
        # Check if this is a file upload or test request
        if 'file' not in request.files:
            # This might be a test request, return success
            response = jsonify({'message': 'Upload endpoint ready for file uploads', 'timestamp': datetime.now().isoformat()})
            return add_cors_headers(response)
        
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
            # Read CSV file and extract columns
            file_stream.seek(0)
            csv_reader = csv.reader(file_stream.read().decode('utf-8').splitlines())
            rows = list(csv_reader)
            
            if not rows:
                response = jsonify({'error': 'Empty CSV file'})
                return add_cors_headers(response), 400
                
            columns = rows[0]  # First row contains column headers
            
            # Clean up column names (remove extra whitespace)
            columns = [col.strip() for col in columns]
            
            # Handle case where column names contain commas and got split
            # If we have more columns than expected, try to reconstruct
            if len(columns) > 4:  # More than the expected 4 columns
                # Look for patterns that suggest a column name was split
                reconstructed_columns = []
                i = 0
                while i < len(columns):
                    if i < len(columns) - 1 and columns[i].endswith('professional') and columns[i+1].startswith('but ideally'):
                        # This looks like a split column name
                        reconstructed_columns.append(columns[i] + ', ' + columns[i+1])
                        i += 2
                    else:
                        reconstructed_columns.append(columns[i])
                        i += 1
                columns = reconstructed_columns
            
            # Store the file data for later use
            uploaded_files[filename] = {
                'content': file_content,
                'extension': extension,
                'rows': rows,
                'columns': columns
            }
        else:
            response = jsonify({'error': 'Only CSV files are supported'})
            return add_cors_headers(response), 400

        response = jsonify({
            'columns': columns,
            'filename': filename
        })
        return add_cors_headers(response)

    except Exception as e:
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

        # Get the stored file data
        if filename not in uploaded_files:
            response = jsonify({'error': 'File not found. Please upload the file again.'})
            return add_cors_headers(response), 400

        print(f"Processing download for file: {filename}")
        print(f"Selected columns: {selected_columns}")
        print(f"Available files in memory: {list(uploaded_files.keys())}")

        file_data = uploaded_files[filename]
        rows = file_data['rows']
        columns = file_data['columns']

        # Count total URLs in selected columns
        total_urls = 0
        for col in selected_columns:
            if col in columns:
                col_index = columns.index(col)
                # Count non-empty values in the column (skip header row)
                for row in rows[1:]:  # Skip header row
                    if len(row) > col_index and row[col_index].strip():
                        total_urls += 1

        if total_urls == 0:
            response = jsonify({
                'success': False,
                'error': 'Please try different columns.',
                'total_images': 0
            })
            return add_cors_headers(response), 400

        # In serverless environment, we can't save files to disk
        # Instead, we'll return the images as base64 data for frontend to download
        successful_downloads = []
        errors = []

        print(f"Starting image download process...")
        print(f"Total rows to process: {len(rows) - 1}")  # Exclude header

        for col in selected_columns:
            if col not in columns:
                errors.append(f"Column '{col}' not found in file")
                continue
            
            col_index = columns.index(col)
            count = 0
            
            print(f"Processing column: {col} (index: {col_index})")
            
            for i, row in enumerate(rows[1:], 1):  # Skip header row
                try:
                    if len(row) <= col_index or not row[col_index].strip():
                        continue
                        
                    signed_url = row[col_index].strip()
                    print(f"Processing row {i}: {signed_url[:50]}...")
                    
                    # Download image data
                    image_info = download_file_from_hubspot(signed_url)
                    if image_info:
                        filename = f"{secure_filename(col)}_{str(count + 1).zfill(3)}.{image_info['extension']}"
                        
                        successful_downloads.append({
                            'column': col,
                            'filename': filename,
                            'data': image_info['data'],  # base64 encoded image data
                            'extension': image_info['extension'],
                            'size': image_info['size']
                        })
                        count += 1
                        print(f"Successfully downloaded: {filename}")
                    else:
                        errors.append(f"Failed to download from {signed_url[:50]}...")
                        print(f"Failed to download from row {i}")
                except Exception as e:
                    errors.append(f"Error processing row {i}: {str(e)}")
                    print(f"Error processing row {i}: {str(e)}")

        print(f"Download process complete. Successful: {len(successful_downloads)}, Errors: {len(errors)}")

        if successful_downloads:
            # For large responses, we'll return a success message without the image data
            # The frontend will need to handle this differently
            response = jsonify({
                'success': True,
                'message': f'{len(successful_downloads)} images processed successfully!',
                'total_images': len(successful_downloads),
                'download_ready': True,
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
        response = jsonify({'error': f'Download failed: {str(e)}'})
        return add_cors_headers(response), 500

# Store processed images temporarily (in production, use a proper storage solution)
processed_images = {}

@app.route('/get-images', methods=['POST', 'OPTIONS'])
def get_images():
    if request.method == 'OPTIONS':
        response = jsonify({'status': 'ok'})
        return add_cors_headers(response)
    
    try:
        data = request.get_json()
        filename = data.get('filename')
        column = data.get('column')
        start_index = data.get('start_index', 0)
        batch_size = data.get('batch_size', 10)
        
        if not filename or not column:
            response = jsonify({'error': 'Missing required parameters'})
            return add_cors_headers(response), 400
            
        # Get the stored file data
        if filename not in uploaded_files:
            response = jsonify({'error': 'File not found. Please upload the file again.'})
            return add_cors_headers(response), 400

        file_data = uploaded_files[filename]
        rows = file_data['rows']
        columns = file_data['columns']
        
        if column not in columns:
            response = jsonify({'error': 'Column not found'})
            return add_cors_headers(response), 400
            
        col_index = columns.index(column)
        images = []
        count = 0
        
        for i, row in enumerate(rows[1:], 1):  # Skip header row
            if len(row) <= col_index or not row[col_index].strip():
                continue
                
            if count < start_index:
                count += 1
                continue
                
            if len(images) >= batch_size:
                break
                
            signed_url = row[col_index].strip()
            
            # Download image data
            image_info = download_file_from_hubspot(signed_url)
            if image_info:
                filename_img = f"{secure_filename(column)}_{str(count + 1).zfill(3)}.{image_info['extension']}"
                
                images.append({
                    'column': column,
                    'filename': filename_img,
                    'data': image_info['data'],
                    'extension': image_info['extension'],
                    'size': image_info['size']
                })
            
            count += 1
            
        response = jsonify({
            'success': True,
            'images': images,
            'has_more': count < len([r for r in rows[1:] if len(r) > col_index and r[col_index].strip()]),
            'next_index': start_index + batch_size
        })
        return add_cors_headers(response)
        
    except Exception as e:
        response = jsonify({'error': f'Failed to get images: {str(e)}'})
        return add_cors_headers(response), 500

# For Vercel serverless
if __name__ == '__main__':
    app.run(debug=True)