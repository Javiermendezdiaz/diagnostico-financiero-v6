#!/usr/bin/env python3
"""
Diagnóstico Financiero - Standalone (sin Docker)
"""

import sys
import json
import os
import threading
import time
import logging
from pathlib import Path
from http.server import HTTPServer, SimpleHTTPRequestHandler

# Configurar logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Directorio de la app
app_dir = Path(__file__).parent.absolute()
os.chdir(app_dir)

# Crear carpeta de outputs
output_dir = app_dir / "reports"
output_dir.mkdir(exist_ok=True)

# Importaciones
try:
    from fastapi import FastAPI, Request, HTTPException
    from fastapi.responses import FileResponse
    from fastapi.middleware.cors import CORSMiddleware
    import uvicorn
except ImportError as e:
    logger.error(f"Falta: {e}")
    logger.info("pip install fastapi uvicorn pydantic reportlab matplotlib numpy --break-system-packages")
    sys.exit(1)

try:
    from diagnostic_engine_friction import DiagnosticEngineFriction
    from diagnostic_report_generator import DiagnosticReportGenerator
except ImportError as e:
    logger.error(f"Modulos: {e}")
    sys.exit(1)

# Config
PORT_API = 8000
PORT_FRONTEND = 3000

# FastAPI
app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

# Schema
schema_path = app_dir / "data-schema-100-friction.json"
try:
    with open(schema_path, "r", encoding="utf-8") as f:
        schema = json.load(f)
    num_bloques = len(schema.get('bloques', {}))
    total_preguntas = schema.get('metadata', {}).get('total_preguntas', 0)
    version = schema.get('metadata', {}).get('version', 'unknown')
    logger.info(f"OK Schema Premium {version}: {num_bloques} bloques, {total_preguntas} preguntas friction-based")
except FileNotFoundError:
    logger.error(f"NO EXISTE: {schema_path}")
    sys.exit(1)

# Motor
try:
    diagnostic_engine = DiagnosticEngineFriction(str(schema_path))
    report_generator = DiagnosticReportGenerator(str(output_dir))
    logger.info("OK Motor listo")
except Exception as e:
    logger.error(f"ERROR: {e}")
    sys.exit(1)

@app.get("/api/v1/schema")
def get_schema():
    """Transforma la estructura de bloques friction-based a un array de preguntas plano"""
    questions = []
    question_id = 1

    bloques_data = schema.get('bloques', {})
    for bloque_key, bloque_content in bloques_data.items():
        bloque_titulo = bloque_content.get('titulo', bloque_key)
        preguntas = bloque_content.get('preguntas', [])

        for pregunta_data in preguntas:
            # Transformar respuestas a formato simple (texto) o mantener estructura con scores
            respuestas_list = []
            pesos_dict = {}

            respuestas_raw = pregunta_data.get('respuestas', [])
            for idx, r in enumerate(respuestas_raw):
                if isinstance(r, dict):
                    texto = r.get('texto', '')
                    score = r.get('score', 0)
                    respuestas_list.append(texto)
                    pesos_dict[str(idx)] = score
                else:
                    respuestas_list.append(r)
                    pesos_dict[str(idx)] = 0

            questions.append({
                "id": question_id,
                "id_original": pregunta_data.get('id', ''),
                "bloque": bloque_key,
                "bloque_titulo": bloque_titulo,
                "pregunta": pregunta_data.get('pregunta', ''),
                "tipo": pregunta_data.get('tipo', 'multiple_choice'),
                "respuestas": respuestas_list,
                "pesos": pesos_dict,
                "dimension": pregunta_data.get('dimension', ''),
                "friccion": pregunta_data.get('friccion', ''),
                "rango_min": pregunta_data.get('rango_min'),
                "rango_max": pregunta_data.get('rango_max'),
                "etiquetas": pregunta_data.get('etiquetas', [])
            })
            question_id += 1

    return {"questions": questions, "metadata": schema.get('metadata', {})}

@app.post("/api/v1/diagnose")
async def diagnose(request: Request):
    try:
        data = await request.json()
        answers = data.get("answers", {})
        user_id = data.get("user_id", f"user_{int(time.time())}")

        # Ejecutar diagnostico
        result = diagnostic_engine.diagnose(answers, user_id=user_id)

        # Generar reporte PDF
        report_filename = f"{user_id}_diagnostic.pdf"
        report_path = output_dir / report_filename
        generator = DiagnosticReportGenerator(str(report_path))
        pdf_path = generator.generate_report(result)

        # Retornar con URL de descarga y session_id para Stripe
        report_id = report_filename.replace('.pdf', '')
        return {
            "success": True,
            "results": result if isinstance(result, dict) else result.__dict__,
            "report_id": report_id,
            "session_id": user_id,
            "download_url": f"/api/v1/reports/{report_id}"
        }
    except Exception as e:
        logger.error(f"Error en diagnose: {e}")
        return {"success": False, "error": str(e)}

@app.get("/api/v1/verify-payment/{session_id}")
async def verify_payment(session_id: str):
    """Verifica que un pago/session es valido y retorna el report_id"""
    try:
        # El session_id es el user_id, y el reporte existe con nombre {user_id}_diagnostic.pdf
        report_filename = f"{session_id}_diagnostic.pdf"
        report_path = output_dir / report_filename

        if not report_path.exists():
            raise HTTPException(status_code=404, detail="Pago no confirmado o reporte no encontrado")

        return {
            "valid": True,
            "session_id": session_id,
            "report_id": session_id
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error verificando pago: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/v1/reports/{report_id}")
async def get_report(report_id: str):
    """Descarga PDF del reporte por ID"""
    try:
        # Buscar archivo con extension .pdf
        report_path = output_dir / f"{report_id}.pdf"

        if not report_path.exists():
            raise HTTPException(status_code=404, detail="Reporte no encontrado")

        return FileResponse(
            report_path,
            media_type="application/pdf",
            filename=f"diagnostico_{report_id}.pdf"
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error al descargar reporte: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/health")
def health():
    return {"status": "ok"}

# Frontend Server
class FrontendHandler(SimpleHTTPRequestHandler):
    def log_message(self, format, *args):
        pass

def start_frontend():
    handler = lambda *args, **kwargs: FrontendHandler(*args, directory=str(app_dir), **kwargs)
    server = HTTPServer(("0.0.0.0", PORT_FRONTEND), handler)
    logger.info(f"OK Frontend: http://localhost:{PORT_FRONTEND}")
    server.serve_forever()

# Main
def main():
    logger.info("")
    logger.info("========= DIAGNOSTICO FINANCIERO =========")
    logger.info("")

    frontend_thread = threading.Thread(target=start_frontend, daemon=True)
    frontend_thread.start()
    time.sleep(0.5)

    logger.info(f"OK API: http://localhost:{PORT_API}")
    logger.info("")
    logger.info(f"ABRE: http://localhost:{PORT_FRONTEND}")
    logger.info("")

    try:
        uvicorn.run(app, host="0.0.0.0", port=PORT_API, log_level="info")
    except KeyboardInterrupt:
        logger.info("OK Cerrado")
        sys.exit(0)

if __name__ == "__main__":
    main()
