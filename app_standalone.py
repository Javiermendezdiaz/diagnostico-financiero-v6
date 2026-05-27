#!/usr/bin/env python3
"""
Diagnóstico Financiero - Standalone (sin Docker)
FastAPI backend + React frontend (SimpleHTTPServer)
"""

import sys
import json
import os
import threading
import time
import logging
from pathlib import Path
from http.server import HTTPServer, SimpleHTTPRequestHandler

# Logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# App dir
app_dir = Path(__file__).parent.absolute()
os.chdir(app_dir)

# Create reports dir
output_dir = app_dir / "reports"
output_dir.mkdir(exist_ok=True)

# Import FastAPI
try:
        from fastapi import FastAPI, Request
        from fastapi.middleware.cors import CORSMiddleware
        import uvicorn
except ImportError as e:
        logger.error(f"Missing: {e}")
        sys.exit(1)

# Import diagnostic modules
try:
        from diagnostic_engine import DiagnosticEngine
        from diagnostic_report_generator import DiagnosticReportGenerator
except ImportError as e:
        logger.error(f"Modules error: {e}")
        sys.exit(1)

# Config
PORT_API = 8000
PORT_FRONTEND = 3000

# FastAPI app
app = FastAPI()
app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
)

# Load schema
schema_path = app_dir / "data-schema-500.json"
try:
        with open(schema_path, "r", encoding="utf-8") as f:
                    schema = json.load(f)
                total_preguntas = schema.get('metadata', {}).get('total_preguntas', 500)
    logger.info(f"Schema loaded: {total_preguntas} questions")
except FileNotFoundError:
    logger.error(f"Schema not found: {schema_path}")
    sys.exit(1)

# Create engine
try:
        diagnostic_engine = DiagnosticEngine(str(schema_path))
    report_generator = DiagnosticReportGenerator(str(output_dir))
    logger.info("Diagnostic engine initialized")
except Exception as e:
    logger.error(f"Engine error: {e}")
    sys.exit(1)

# API Endpoints

@app.get("/health")
def health():
        return {"status": "ok"}

@app.get("/api/v1/schema")
def get_schema():
        """Return all questions in flat array format"""
    questions = []
    question_id = 1

    capas = schema.get('capas', {})
    for capa_name, capa_data in capas.items():
                preguntas = capa_data.get('preguntas', [])

        for pregunta_data in preguntas:
                        # Parse respuestas and pesos
                        respuestas_list = pregunta_data.get('respuestas', [])
                        pesos = pregunta_data.get('pesos', {})

            questions.append({
                                "id": question_id,
                                "capa": capa_name,
                                "pregunta": pregunta_data.get('pregunta', ''),
                                "respuestas": respuestas_list,
                                "pesos": pesos
            })
            question_id += 1

    return {"questions": questions, "metadata": schema.get('metadata', {})}

@app.post("/api/v1/diagnose")
async def diagnose(request: Request):
        """Process answers and generate diagnostic result"""
    try:
                data = await request.json()
                answers = data.get("answers", {})

        # Run diagnostic
                result = diagnostic_engine.diagnose(answers)

        # Generate PDF report
                user_id = f"user_{int(time.time())}"
                report_filename = f"{user_id}_diagnostic.pdf"
                pdf_path = report_generator.generate_report(result, report_filename)

        # Return result
                result_dict = result if isinstance(result, dict) else result.__dict__
                return {
                    "success": True,
                    "results": result_dict,
                    "report_path": str(pdf_path)
                }
except Exception as e:
        logger.error(f"Diagnose error: {e}")
        import traceback
        traceback.print_exc()
        return {"success": False, "error": str(e)}

# Frontend server (separate thread)
class QuietHTTPRequestHandler(SimpleHTTPRequestHandler):
        def log_message(self, format, *args):
                    pass  # Suppress logging

def run_frontend():
        os.chdir(app_dir)
    server = HTTPServer(("0.0.0.0", PORT_FRONTEND), QuietHTTPRequestHandler)
    logger.info(f"Frontend running on port {PORT_FRONTEND}")
    server.serve_forever()

if __name__ == "__main__":
        # Start frontend in background thread
        frontend_thread = threading.Thread(target=run_frontend, daemon=True)
    frontend_thread.start()
    time.sleep(1)

    # Start API server
    logger.info(f"Starting API on port {PORT_API}")
    uvicorn.run(app, host="0.0.0.0", port=PORT_API)
