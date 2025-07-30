from flask import Flask, request, jsonify
from flask_cors import CORS
from werkzeug.utils import secure_filename
import os
import io
import pandas as pd
import json
from datetime import datetime

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

@app.route('/health', methods=['GET'])
def health_check():
    response = jsonify({'status': 'healthy', 'message': 'HubSpot Image Downloader API is running'})
    return add_cors_headers(response)

@app.route('/test', methods=['GET'])
def test():
    response = jsonify({'message': 'Backend is working!', 'timestamp': datetime.now().isoformat()})
    return add_cors_headers(response)

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

        file_data = uploaded_files[filename]
        df = file_data['dataframe']

        # Count total URLs in selected columns
        total_urls = 0
        for col in selected_columns:
            if col in df.columns:
                # Count non-null values in the column
                total_urls += df[col].notna().sum()

        if total_urls == 0:
            response = jsonify({
                'success': False,
                'error': 'Please try different columns.',
                'total_images': 0
            })
            return add_cors_headers(response), 400

        # For now, return success response (actual download logic will be added later)
        response = jsonify({
            'success': True,
            'message': f'{total_urls} image URLs found in {len(selected_columns)} columns. Images would be downloaded to Downloads/hubspot-images/',
            'total_images': total_urls,
            'download_path': 'Downloads/hubspot-images/'
        })
        return add_cors_headers(response)

    except Exception as e:
        response = jsonify({'error': f'Download failed: {str(e)}'})
        return add_cors_headers(response), 500

# For Vercel serverless
if __name__ == '__main__':
    app.run(debug=True)