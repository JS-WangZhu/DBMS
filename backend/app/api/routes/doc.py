import os
from flask import Blueprint, send_from_directory, current_app, abort

bp = Blueprint("doc", __name__, url_prefix="/doc")

@bp.route("/api")
def serve_api_doc():
    """
    公开访问的 API 接口文档
    Url: /api/v1/doc/api
    """
    doc_dir = os.path.join(current_app.root_path, "..", "doc")
    filename = "api_manual.md"
    
    if not os.path.exists(os.path.join(doc_dir, filename)):
        abort(404, description="Document not found")
        
    return send_from_directory(doc_dir, filename, mimetype='text/markdown; charset=utf-8')
