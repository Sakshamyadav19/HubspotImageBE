from flask import Flask, request, jsonify
from flask_cors import CORS
import os
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

        # For now, return mock data to test the frontend
        # In a real implementation, you would process the file here
        mock_columns = ['Image URL', 'Product Image', 'Banner Image', 'Logo', 'Thumbnail']
        filename = file.filename if file.filename else 'uploaded_file.csv'
        
        response = jsonify({
            'columns': mock_columns,
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

        # For now, return mock success response
        # In a real implementation, you would process the download here
        response = jsonify({
            'success': True,
            'message': f'{len(selected_columns)} columns processed successfully. Images would be downloaded to Downloads/hubspot-images/',
            'total_images': len(selected_columns) * 5,  # Mock: 5 images per column
            'download_path': 'Downloads/hubspot-images/'
        })
        return add_cors_headers(response)

    except Exception as e:
        response = jsonify({'error': f'Download failed: {str(e)}'})
        return add_cors_headers(response), 500

# For Vercel serverless
if __name__ == '__main__':
    app.run(debug=True)