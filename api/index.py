from flask import Flask, request, jsonify
from flask_cors import CORS
from werkzeug.utils import secure_filename
import os
import io
import csv
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