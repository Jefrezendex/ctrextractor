import os, threading, uuid, zipfile
from flask import Flask, request, jsonify, send_file, render_template
import pdfkit
from bs4 import BeautifulSoup
import re
from PyPDF2 import PdfMerger

app = Flask(__name__, template_folder='templates')
JOBS = {}
WKHTML = os.environ.get('WKHTMLTOPDF_PATH', '/usr/bin/wkhtmltopdf')

def ensure_dirs():
    os.makedirs('results', exist_ok=True)
    os.makedirs('tmp_html', exist_ok=True)
ensure_dirs()

def generate_job(jobId, ids):
    try:
        out_dir = os.path.join('results', jobId)
        os.makedirs(out_dir, exist_ok=True)
        pdfs = []
        total = len(ids)
        for idx, id_ in enumerate(ids, start=1):
            html = f"<html><body><h1>ID: {id_}</h1><p>Documento gerado para {id_}</p></body></html>"
            html_path = os.path.join('tmp_html', f"{jobId}_{id_}.html")
            with open(html_path, 'w', encoding='utf-8') as f:
                f.write(html)
            pdf_path = os.path.join(out_dir, f"{id_}.pdf")
            try:
                pdfkit.from_file(html_path, pdf_path, configuration=pdfkit.configuration(wkhtmltopdf=WKHTML))
            except Exception:
                # create empty placeholder on failure
                with open(pdf_path, 'wb') as f:
                    f.write(b'')
            pdfs.append(pdf_path)
            JOBS[jobId]['progress'] = int((idx/total)*90)
        merger = PdfMerger()
        for p in pdfs:
            merger.append(p)
        merged_path = os.path.join(out_dir, 'todos_unidos.pdf')
        merger.write(merged_path); merger.close()
        zip_path = os.path.join('results', f"{jobId}.zip")
        with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zf:
            for p in pdfs:
                zf.write(p, os.path.basename(p))
            zf.write(merged_path, os.path.basename(merged_path))
        JOBS[jobId]['progress'] = 100
        JOBS[jobId]['status'] = 'done'
        JOBS[jobId]['zip'] = zip_path
    except Exception:
        JOBS[jobId]['status'] = 'error'
        JOBS[jobId]['progress'] = 0

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/start', methods=['POST'])
def start():
    data = request.get_json(force=True)
    ids = data.get('ids') or []
    jobId = str(uuid.uuid4())
    JOBS[jobId] = {'progress': 0, 'status': 'processing', 'zip': None}
    t = threading.Thread(target=generate_job, args=(jobId, ids), daemon=True)
    t.start()
    return jsonify({'jobId': jobId})

@app.route('/status/<jobId>', methods=['GET'])
def status(jobId):
    job = JOBS.get(jobId)
    if not job:
        return jsonify({'error': 'not found'}), 404
    return jsonify({'progress': job['progress'], 'status': job['status'], 'downloadUrl': f"/download/{jobId}" if job.get('zip') else None})

@app.route('/download/<jobId>', methods=['GET'])
def download(jobId):
    job = JOBS.get(jobId)
    if not job or not job.get('zip'):
        return "Not found", 404
    return send_file(job['zip'], as_attachment=True)

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT',5000)))
