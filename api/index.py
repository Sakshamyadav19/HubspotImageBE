from flask import Flask, request, jsonify
from flask_cors import CORS
import os
import json
from datetime import datetime

app = Flask(__name__)

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
        response = jsonify({'message': 'Upload endpoint working', 'timestamp': datetime.now().isoformat()})
        return add_cors_headers(response)
    except Exception as e:
        response = jsonify({'error': f'Upload failed: {str(e)}'})
        return add_cors_headers(response), 500

# For Vercel serverless
if __name__ == '__main__':
    app.run(debug=True)