import os
from datetime import datetime, timezone
import logging
from typing import Optional
from fastapi import FastAPI, HTTPException, UploadFile, File, Form, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from pymongo import MongoClient
from bson import ObjectId
from dotenv import load_dotenv
import google.generativeai as genai
import json
from services.enrutamiento_service import EnrutamientoService
import threading

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("zflow-ai")

# Robust .env loader
def load_env():
    base_dir = os.path.dirname(os.path.abspath(__file__))
    paths = [
        os.path.join(base_dir, ".env"),
        os.path.join(base_dir, "..", ".env"),
        os.path.join(base_dir, "../..", ".env"),
        os.path.join(base_dir, "../../..", ".env"),
    ]
    for path in paths:
        if os.path.exists(path):
            logger.info(f"Loading environment variables from: {path}")
            load_dotenv(dotenv_path=path)
            return
    logger.warning("No .env file found by zflow-ai.")

load_env()

# Configure Gemini
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)
    logger.info("Google Gemini API configured successfully.")
else:
    logger.warning("GEMINI_API_KEY not found in environment variables.")

app = FastAPI(title="ZFlow AI Microservice", version="1.0.0")

# CORS setup
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# MongoDB setup
MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017/zflow")
MONGO_DB = os.getenv("MONGO_DB", "zflow")

logger.info(f"Connecting to MongoDB at {MONGO_URI}, database: {MONGO_DB}")
try:
    mongo_client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=2000)
    db = mongo_client[MONGO_DB]
    # Simple ping to verify connection
    mongo_client.admin.command('ping')
    logger.info("Connected to MongoDB successfully.")
except Exception as e:
    logger.error(f"Failed to connect to MongoDB: {e}")
    db = None

class PrioridadRequest(BaseModel):
    fecha_asignacion: datetime = Field(..., description="Timestamp of when the task was assigned")
    funcionario_id: Optional[str] = Field(None, description="ID of the funcionario requesting or assigned to the task")
    tipo: Optional[str] = Field("normal", description="Type of task: 'critico' or 'normal'")
    actividad_nombre: Optional[str] = Field(None, description="Name of the activity/step")

class PrioridadResponse(BaseModel):
    prioridad: str = Field(..., description="Calculated priority: 'alta', 'media', or 'baja'")
    score: int = Field(..., ge=0, le=100, description="Calculated priority score (0-100)")

class EnrutamientoRequest(BaseModel):
    carga_raw: int = Field(..., description="Cantidad de tareas pendientes en el departamento")
    horas_raw: float = Field(..., description="Horas transcurridas desde la asignación")
    paso_critico: bool = Field(..., description="Indica si el paso actual es crítico")
    documentos_count: int = Field(..., description="Cantidad de documentos adjuntos al trámite")
    documentos_size_bytes: int = Field(..., description="Tamaño total de los documentos en bytes")

class EnrutamientoResponse(BaseModel):
    prioridadScore: int = Field(..., description="Recomendación de prioridad score (0-100)")
    prioridadLabel: str = Field(..., description="Recomendación de prioridad label ('alta', 'media', 'baja')")
    riesgoDemora: float = Field(..., description="Probabilidad de riesgo de demora (0.0 a 1.0)")
    anomaliaDetectada: bool = Field(..., description="Indica si se detectó comportamiento anómalo")
    anomaliaScore: float = Field(..., description="Score de anomalía (0.0 a 1.0)")
    rutaOptimaSugerida: str = Field(..., description="Paso óptimo siguiente recomendado por la IA")

enrutamiento_service = EnrutamientoService()

@app.on_event("startup")
def startup_event():
    def train_models():
        if not enrutamiento_service.cargar_modelos():
            enrutamiento_service.entrenar_modelos_startup()
    threading.Thread(target=train_models, daemon=True).start()


def count_pending_tasks(funcionario_id: str) -> int:
    if db is None:
        logger.warning("MongoDB not connected. Returning 0 pending tasks.")
        return 0
    try:
        # Try finding the user by string ID or ObjectId
        user = db.usuarios.find_one({"_id": funcionario_id})
        if not user and ObjectId.is_valid(funcionario_id):
            user = db.usuarios.find_one({"_id": ObjectId(funcionario_id)})
            
        if not user:
            logger.warning(f"User not found for ID: {funcionario_id}")
            return 0
            
        dept_id = user.get("departamento_id")
        if not dept_id:
            logger.warning(f"User {funcionario_id} does not have a departamento_id.")
            return 0
            
        # Count tramites in process that have a pending step in the user's department
        count = db.tramites.count_documents({
            "estado": "EN_PROCESO",
            "historial": {
                "$elemMatch": {
                    "fin": None,
                    "departamento_id": dept_id
                }
            }
        })
        logger.info(f"Pending tasks count for department {dept_id}: {count}")
        return count
    except Exception as e:
        logger.error(f"Error querying pending tasks for {funcionario_id}: {e}")
        return 0

@app.post("/api/ai/prioridad", response_model=PrioridadResponse)
def calcular_prioridad(req: PrioridadRequest):
    score = 0
    
    # 1. Antigüedad (hours since assignment) - Max 40 points
    now = datetime.now(timezone.utc)
    # Ensure req.fecha_asignacion has timezone info, default to UTC if naive
    fecha_asig = req.fecha_asignacion
    if fecha_asig.tzinfo is None:
        fecha_asig = fecha_asig.replace(tzinfo=timezone.utc)
        
    diff = now - fecha_asig
    horas = diff.total_seconds() / 3600.0
    
    if horas > 20:
        score += 40
    elif horas > 12:
        score += 25
    elif horas > 6:
        score += 10
        
    # 2. Carga del funcionario (based on pending department tasks) - Max 30 points
    if req.funcionario_id:
        tareas_pendientes = count_pending_tasks(req.funcionario_id)
        if tareas_pendientes > 10:
            score += 30
        elif tareas_pendientes > 5:
            score += 15
            
    # 3. Tipo de paso (critical vs normal) - Max 30 points
    is_critical = False
    if req.tipo and req.tipo.lower() == "critico":
        is_critical = True
    elif req.actividad_nombre:
        # Heuristic: check keywords in the activity name
        keywords = ["aprobacion", "aprobación", "firma", "evaluacion", "evaluación", "decidir", "decision", "decisión", "crítico", "critico"]
        name_lower = req.actividad_nombre.lower()
        if any(kw in name_lower for kw in keywords):
            is_critical = True
            
    if is_critical:
        score += 30
    else:
        score += 10
        
    # Cap score at 100 just in case
    score = min(score, 100)
    
    # Priority resolution
    if score >= 70:
        prioridad = "alta"
    elif score >= 40:
        prioridad = "media"
    else:
        prioridad = "baja"
        
    logger.info(f"Priority calculated: {prioridad} (score: {score}) for hours: {horas:.2f}, critical: {is_critical}")
    return PrioridadResponse(prioridad=prioridad, score=score)

@app.post("/api/ai/voz-formulario")
async def procesar_voz_formulario(
    file: UploadFile = File(...),
    esquema: str = Form(...)
):
    if not GEMINI_API_KEY:
        raise HTTPException(status_code=500, detail="Gemini API Key is not configured on the server.")
        
    try:
        schema_data = json.loads(esquema)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid schema format: {e}")
        
    audio_bytes = await file.read()
    
    prompt = f"""
    You are a form-filling assistant. You are given:
    1. An audio recording of a user dictating values for a form.
    2. A schema of the form fields to fill:
    {json.dumps(schema_data, indent=2, ensure_ascii=False)}

    Your task:
    Analyze the audio dictation and extract the appropriate values for each field in the schema.
    
    Rules:
    - Return a JSON object where the keys are the field 'id' strings, and the values are the extracted values matching the field's 'tipo' (e.g., numbers for NUMERO, strings for TEXTO or SELECTOR, dates for FECHA).
    - If a field is a SELECTOR, match the spoken value to one of the allowed options if possible.
    - If a field is not mentioned in the audio, do NOT invent a value. Set it to null or omit it.
    - Output ONLY the JSON object. Do not include markdown code block formatting (like ```json).
    """

    try:
        model = genai.GenerativeModel(
            "gemini-2.5-flash",
            generation_config={"response_mime_type": "application/json"}
        )
        response = model.generate_content([
            {
                "mime_type": file.content_type or "audio/webm",
                "data": audio_bytes
            },
            prompt
        ])
        
        result_json = json.loads(response.text)
        logger.info(f"Gemini voice form extraction result: {result_json}")
        return result_json
        
    except Exception as e:
        logger.error(f"Error calling Gemini API: {e}")
        raise HTTPException(status_code=500, detail=f"Error processing audio with Gemini: {str(e)}")

@app.post("/api/ai/analizar-documento")
async def analizar_documento(
    file: UploadFile = File(...),
    contexto: str = Form(...)
):
    if not GEMINI_API_KEY:
        raise HTTPException(status_code=500, detail="Gemini API Key is not configured on the server.")
        
    try:
        context_data = json.loads(contexto)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid context format: {e}")
        
    file_bytes = await file.read()
    
    prompt = f"""
    You are an AI Document Auditor. You are given:
    1. A document file uploaded by a client.
    2. The context of the application form fields completed by the client so far:
    {json.dumps(context_data, indent=2, ensure_ascii=False)}

    Your task:
    Read the document carefully, extract the relevant data (e.g. names, IDs, dates, financial amounts, salary, employer name, address) and perform a cross-reference verification against the application context data.

    Determine:
    - If there are any critical mismatches (discrepancies) between what is written in the document and the form context (e.g. name misspelled, different ID number, different addresses, requested loan amount completely unsupported by income slips).
    - If the document itself appears valid, legible, and not expired.

    Return a JSON response matching this exact schema:
    {{
        "valido": boolean (true if no critical mismatches or expired/invalid files are found, false otherwise),
        "scoreDiscrepancia": integer (0 to 100, where 0 means perfect match/no discrepancy, and 100 means total mismatch or invalid/fake document),
        "resumen": "string (a concise, professional summary of the verification results in Spanish)",
        "alertas": ["string", "string", ...] (a list of specific mismatch/validation alerts found, in Spanish. If no warnings, return an empty list)
    }}

    Rules:
    - Ensure your response is strictly valid JSON. Do not wrap it in markdown code blocks like ```json.
    - Write the 'resumen' and 'alertas' in Spanish.
    - Be strict: if the name is completely different, set 'valido' to false and write an alert. If the document is expired, set 'valido' to false.
    """

    try:
        model = genai.GenerativeModel(
            "gemini-2.5-flash",
            generation_config={"response_mime_type": "application/json"}
        )
        response = model.generate_content([
            {
                "mime_type": file.content_type or "application/pdf",
                "data": file_bytes
            },
            prompt
        ])
        
        result_json = json.loads(response.text)
        logger.info(f"Gemini document analysis result: {result_json}")
        return result_json
        
    except Exception as e:
        logger.error(f"Error calling Gemini API for document analysis: {e}")
        raise HTTPException(status_code=500, detail=f"Error analyzing document with Gemini: {str(e)}")

@app.post("/api/ai/politica/sugerir")
async def sugerir_politica(
    file: UploadFile = File(...),
    politicas: str = Form(...)
):
    if not GEMINI_API_KEY:
        raise HTTPException(status_code=500, detail="Gemini API Key is not configured on the server.")
        
    try:
        politicas_list = json.loads(politicas)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid politicas format: {e}")
        
    audio_bytes = await file.read()
    
    prompt = f"""
    You are an AI Policy Router. You are given:
    1. An audio file of a client describing their situation in Spanish.
    2. A list of active policies available in the organization:
    {json.dumps(politicas_list, indent=2, ensure_ascii=False)}

    Your task:
    1. Transcribe the spoken audio description into Spanish.
    2. Match the spoken description against the available policies (by comparing the description with policy 'nombre' and 'descripcion').
    3. Determine if there is a highly confident match (confidence > 70%).
    4. If there is a high-confidence match, set 'sugerenciaConfianza' to true and 'politicaSugeridaId' to that policy's 'id'.
    5. If the description is too vague, ambiguous, or matches multiple policies similarly without a clear winner, set 'sugerenciaConfianza' to false and 'politicaSugeridaId' to null.
    6. Provide a list of candidate policy IDs ('politicasCandidatasIds') that could fit the client's request, sorted from most relevant to least relevant. If none match, return an empty list.

    Return a JSON response matching this exact schema:
    {{
        "transcripcion": "string (the Spanish transcription of the audio)",
        "sugerenciaConfianza": boolean,
        "politicaSugeridaId": "string or null",
        "politicasCandidatasIds": ["string", "string", ...]
    }}

    Rules:
    - Ensure your response is strictly valid JSON. Do not wrap it in markdown code blocks.
    - Write the 'transcripcion' in Spanish.
    """

    try:
        model = genai.GenerativeModel(
            "gemini-2.5-flash",
            generation_config={"response_mime_type": "application/json"}
        )
        response = model.generate_content([
            {
                "mime_type": file.content_type or "audio/wav",
                "data": audio_bytes
            },
            prompt
        ])
        
        result_json = json.loads(response.text)
        logger.info(f"Gemini policy suggestion result: {result_json}")
        return result_json
        
    except Exception as e:
        logger.error(f"Error calling Gemini API for policy suggestion: {e}")
        raise HTTPException(status_code=500, detail=f"Error suggesting policy with Gemini: {str(e)}")

@app.post("/api/ai/voz/transcribir")
async def transcribir_audio(
    file: UploadFile = File(...)
):
    if not GEMINI_API_KEY:
        raise HTTPException(status_code=500, detail="Gemini API Key is not configured on the server.")
        
    audio_bytes = await file.read()
    
    prompt = """
    You are a speech-to-text assistant. Transcribe the spoken audio in Spanish.
    Return ONLY the transcribed text. Do not add any extra explanations or formatting.
    """

    try:
        model = genai.GenerativeModel("gemini-2.5-flash")
        response = model.generate_content([
            {
                "mime_type": file.content_type or "audio/wav",
                "data": audio_bytes
            },
            prompt
        ])
        
        transcription = response.text.strip()
        logger.info(f"Gemini audio transcription result: {transcription}")
        return {"text": transcription}
        
    except Exception as e:
        logger.error(f"Error calling Gemini API for transcription: {e}")
        raise HTTPException(status_code=500, detail=f"Error transcribing audio with Gemini: {str(e)}")

def serialize_mongo(data):
    if isinstance(data, list):
        return [serialize_mongo(item) for item in data]
    if isinstance(data, dict):
        return {k: serialize_mongo(v) for k, v in data.items()}
    if isinstance(data, ObjectId):
        return str(data)
    if isinstance(data, datetime):
        return data.isoformat()
    return data

def generate_report_pdf(prompt: str, explanation: str, summary: str, data: list) -> bytes:
    from io import BytesIO
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle

    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        rightMargin=40, leftMargin=40, topMargin=40, bottomMargin=40
    )
    story = []
    
    styles = getSampleStyleSheet()
    
    title_style = ParagraphStyle(
        'ReportTitle',
        parent=styles['Heading1'],
        fontName='Helvetica-Bold',
        fontSize=18,
        textColor=colors.HexColor('#0f172a'),
        spaceAfter=10
    )
    
    subtitle_style = ParagraphStyle(
        'ReportSubtitle',
        parent=styles['Normal'],
        fontName='Helvetica-Oblique',
        fontSize=9,
        textColor=colors.HexColor('#475569'),
        spaceAfter=15
    )
    
    section_style = ParagraphStyle(
        'SectionHeading',
        parent=styles['Heading2'],
        fontName='Helvetica-Bold',
        fontSize=11,
        textColor=colors.HexColor('#1e293b'),
        spaceBefore=10,
        spaceAfter=5
    )
    
    body_style = ParagraphStyle(
        'ReportBody',
        parent=styles['BodyText'],
        fontName='Helvetica',
        fontSize=9,
        textColor=colors.HexColor('#334155'),
        leading=12,
        spaceAfter=6
    )
    
    story.append(Paragraph("ZFLOW BPM — REPORTE DE ANALÍTICA INTELIGENTE", title_style))
    story.append(Paragraph(f"Generado el: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')} | Solicitud: \"{prompt}\"", subtitle_style))
    story.append(Spacer(1, 10))
    
    story.append(Paragraph("Descripción Técnica de la Búsqueda:", section_style))
    story.append(Paragraph(explanation, body_style))
    story.append(Spacer(1, 8))
    
    story.append(Paragraph("Resumen de Hallazgos (Generado por IA):", section_style))
    story.append(Paragraph(summary, body_style))
    story.append(Spacer(1, 12))
    
    story.append(Paragraph("Datos Detallados de la Consulta:", section_style))
    
    if not data:
        story.append(Paragraph("No se encontraron registros en la base de datos para esta consulta.", body_style))
    else:
        headers = list(data[0].keys())
        max_cols = 6
        if len(headers) > max_cols:
            headers = headers[:max_cols]
            
        table_data = []
        header_row = [Paragraph(f"<b>{h.upper()}</b>", ParagraphStyle('HCol', parent=body_style, textColor=colors.white)) for h in headers]
        table_data.append(header_row)
        
        cell_style = ParagraphStyle('CellText', parent=body_style, fontSize=8, leading=10, spaceAfter=0)
        for row in data:
            row_cells = []
            for h in headers:
                val = row.get(h, '')
                if val is None:
                    val_str = '-'
                elif isinstance(val, (dict, list)):
                    val_str = json.dumps(val, ensure_ascii=False)
                    if len(val_str) > 40:
                        val_str = val_str[:37] + "..."
                else:
                    val_str = str(val)
                row_cells.append(Paragraph(val_str, cell_style))
            table_data.append(row_cells)
            
        col_width = 532.0 / len(headers)
        t = Table(table_data, colWidths=[col_width]*len(headers))
        t.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#0f172a')),
            ('ALIGN', (0,0), (-1,-1), 'LEFT'),
            ('VALIGN', (0,0), (-1,-1), 'TOP'),
            ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor('#cbd5e1')),
            ('ROWBACKGROUNDS', (0,1), (-1,-1), [colors.white, colors.HexColor('#f8fafc')]),
            ('BOTTOMPADDING', (0,0), (-1,0), 5),
            ('TOPPADDING', (0,0), (-1,0), 5),
            ('BOTTOMPADDING', (0,1), (-1,-1), 3),
            ('TOPPADDING', (0,1), (-1,-1), 3),
        ]))
        story.append(t)
        
    doc.build(story)
    return buffer.getvalue()

async def get_query_data(prompt: Optional[str], file: Optional[UploadFile]):
    if not GEMINI_API_KEY:
        raise HTTPException(status_code=500, detail="Gemini API Key is not configured on the server.")

    transcription = ""
    if file is not None:
        try:
            audio_bytes = await file.read()
            transcription_prompt = """
            You are a speech-to-text assistant. Transcribe the spoken audio in Spanish.
            Return ONLY the transcribed text. Do not add any extra explanations or formatting.
            """
            model = genai.GenerativeModel("gemini-2.5-flash")
            response = model.generate_content([
                {
                    "mime_type": file.content_type or "audio/wav",
                    "data": audio_bytes
                },
                transcription_prompt
            ])
            transcription = response.text.strip()
            logger.info(f"Report voice transcription: {transcription}")
        except Exception as e:
            logger.error(f"Error transcribing report voice: {e}")

    final_prompt = prompt or ""
    if transcription:
        final_prompt = (final_prompt + " " + transcription).strip()

    if not final_prompt:
        raise HTTPException(status_code=400, detail="Debe proporcionar un prompt de texto o un archivo de audio.")

    db_schema_description = """
    We have the following collections in MongoDB:
    1. 'tramites':
       - _id: ObjectId or String
       - politica_id: String (references politicas._id)
       - cliente_id: String (references usuarios._id)
       - estado: String ("EN_PROCESO", "FINALIZADO", "PAUSADO")
       - paso_actual: List of String
       - created_at: Date
       - updated_at: Date
       - historial: List of objects:
         - actividad_id: String
         - funcionario_id: String (references usuarios._id)
         - datos_formulario: Map/Object of field values
         - inicio: Date
         - fin: Date (null if step is active)
         - estado: String
         - lane_name: String
         - departamento_id: String (references departamentos._id)
       - prioridad: String ("alta", "media", "baja")
       - prioridadScore: Integer (0-100)
       - politicaNombre: String
       - pasoActualNombre: String
    """

    translate_prompt = f"""
    You are a MongoDB aggregate query generator.
    Translate the user's natural language request (in Spanish) into a MongoDB aggregation pipeline for the 'tramites' collection.
    
    Database Schema:
    {db_schema_description}

    User Prompt: "{final_prompt}"

    Rules:
    - The aggregation pipeline must filter and return complete documents from the 'tramites' collection.
    - If user asks for active/pending workflows, filter by estado: "EN_PROCESO".
    - You must return complete documents, retaining all main fields (like _id, politica_id, cliente_id, estado, created_at, prioridad, etc.) because the results will be displayed directly in a table of tramites.
    - Return ONLY a valid JSON object matching this schema:
      {{
        "pipeline": [ ... aggregation pipeline stages ... ],
        "explicacion": "A brief explanation in Spanish of what the query does"
      }}
    - Do NOT include any markdown format (e.g. ```json).
    - If the request is not related to ZFlow data, return an empty pipeline list.
    """

    pipeline = []
    explicacion = ""
    try:
        model = genai.GenerativeModel(
            "gemini-2.5-flash",
            generation_config={"response_mime_type": "application/json"}
        )
        response = model.generate_content(translate_prompt)
        res_json = json.loads(response.text)
        pipeline = res_json.get("pipeline", [])
        explicacion = res_json.get("explicacion", "Consulta dinámica generada por IA.")
        logger.info(f"Generated MongoDB pipeline: {pipeline}")
    except Exception as e:
        logger.error(f"Error calling Gemini for pipeline generation: {e}")
        pipeline = [{"$limit": 50}]
        explicacion = "Listado de trámites (fallback)."

    raw_data = []
    if db is not None:
        try:
            raw_data = list(db.tramites.aggregate(pipeline))
            logger.info(f"MongoDB query returned {len(raw_data)} documents.")
        except Exception as e:
            logger.error(f"Error running aggregation pipeline: {e}")
            try:
                raw_data = list(db.tramites.find().limit(50))
            except Exception as e2:
                logger.error(f"Fallback find also failed: {e2}")

    serialized_data = serialize_mongo(raw_data)
    return serialized_data, final_prompt, transcription, explicacion

@app.post("/api/ai/reporte/datos")
async def query_reporte_datos(
    file: Optional[UploadFile] = File(None),
    prompt: Optional[str] = Form(None)
):
    try:
        data, final_prompt, transcription, explicacion = await get_query_data(prompt, file)
        return {"data": data, "final_prompt": final_prompt, "explicacion": explicacion}
    except HTTPException as he:
        raise he
    except Exception as e:
        logger.error(f"Error in query_reporte_datos: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/ai/reporte/generar")
async def generar_reporte(
    file: Optional[UploadFile] = File(None),
    prompt: Optional[str] = Form(None)
):
    try:
        serialized_data, final_prompt, transcription, explicacion = await get_query_data(prompt, file)
    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    summary_prompt = f"""
    Analyze the following data returned by a MongoDB query for the prompt: "{final_prompt}".
    Query explanation: "{explicacion}"
    
    Data:
    {json.dumps(serialized_data[:20], ensure_ascii=False)}
    
    Your task:
    Write a concise, professional executive summary of 2-3 sentences in Spanish summarizing the query results.
    - Focus on main numbers, trends, bottlenecks, or key findings.
    - Write in professional, clear tone.
    - DO NOT use emojis.
    - Output ONLY the summary text. Do not wrap in markdown or JSON.
    """

    summary = "Reporte generado con éxito."
    try:
        model = genai.GenerativeModel("gemini-2.5-flash")
        response = model.generate_content(summary_prompt)
        summary = response.text.strip()
        logger.info(f"Report executive summary: {summary}")
    except Exception as e:
        logger.error(f"Error generating executive summary: {e}")

    try:
        pdf_bytes = generate_report_pdf(final_prompt, explicacion, summary, serialized_data)
        return Response(content=pdf_bytes, media_type="application/pdf")
    except Exception as e:
        logger.error(f"Error generating ReportLab PDF: {e}")
        raise HTTPException(status_code=500, detail=f"Error generating PDF: {str(e)}")

class CuelloBotellaAiRequest(BaseModel):
    politicaNombre: str
    actividades: list[dict]
    tiemposPromedio: dict[str, float]
    cargaFuncionarios: dict[str, int]

class CuelloBotellaAiResponse(BaseModel):
    sugerencias: list[str]

def calcular_cuellos_botella_local(req: CuelloBotellaAiRequest) -> list[str]:
    sugerencias = []
    for act_id, hours in req.tiemposPromedio.items():
        act_name = act_id
        for act in req.actividades:
            if act.get("id") == act_id or act.get("actividadId") == act_id:
                act_name = act.get("nombre", act_id)
                break
        if hours > 12.0:
            sugerencias.append(f"CRÍTICO: El paso '{act_name}' tarda en promedio {hours:.1f} horas. Se sugiere simplificar el formulario (heurística local).")
        elif hours > 6.0:
            sugerencias.append(f"ADVERTENCIA: El paso '{act_name}' tarda en promedio {hours:.1f} horas. Considere reasignar apoyo (heurística local).")
            
    for func, count in req.cargaFuncionarios.items():
        if count > 20:
            sugerencias.append(f"SUGERENCIA: El funcionario '{func}' completó {count} tareas. Se recomienda redistribuir para evitar sobrecarga (heurística local).")
            
    if not sugerencias:
        sugerencias.append("No se detectaron cuellos de botella con la heurística local. El flujo se encuentra optimizado.")
    return sugerencias

@app.post("/api/ai/cuellos-botella", response_model=CuelloBotellaAiResponse)
def analizar_cuellos_botella(req: CuelloBotellaAiRequest):
    if not GEMINI_API_KEY:
        return CuelloBotellaAiResponse(sugerencias=calcular_cuellos_botella_local(req))
        
    prompt = f"""
    You are an Expert BPM Business Process Auditor.
    You are analyzing the performance metrics of a policy/process workflow named "{req.politicaNombre}".
    
    Here is the process context:
    1. Activities defined in the policy:
    {json.dumps(req.actividades, indent=2, ensure_ascii=False)}
    
    2. Average completion time (in hours) for each activity:
    {json.dumps(req.tiemposPromedio, indent=2, ensure_ascii=False)}
    
    3. Workload (number of completed tasks) per funcionario:
    {json.dumps(req.cargaFuncionarios, indent=2, ensure_ascii=False)}

    Your task:
    Identify bottlenecks, overloaded officials, and make concrete recommendations.
    
    Rules for suggestions:
    - Focus on steps that take too long (e.g. average time is high).
    - Focus on officials who are performing disproportionately more tasks than others (overloaded).
    - Draft 2 to 4 concrete, actionable improvements in Spanish.
    - DO NOT use emojis.
    - Return a JSON object matching this schema:
      {{
        "sugerencias": [
          "string (suggestion 1 in Spanish)",
          "string (suggestion 2 in Spanish)",
          ...
        ]
      }}
    - Output ONLY the valid JSON object. Do not include markdown code block formatting.
    """

    try:
        model = genai.GenerativeModel(
            "gemini-2.5-flash",
            generation_config={"response_mime_type": "application/json"}
        )
        response = model.generate_content(prompt)
        result_json = json.loads(response.text)
        logger.info(f"Gemini bottleneck analysis suggestions: {result_json}")
        return CuelloBotellaAiResponse(sugerencias=result_json.get("sugerencias", []))
    except Exception as e:
        logger.error(f"Error calling Gemini for bottleneck analysis: {e}")
        return CuelloBotellaAiResponse(sugerencias=calcular_cuellos_botella_local(req))

@app.get("/health")
def health_check():
    mongo_status = "connected" if db is not None else "disconnected"
    return {"status": "ok", "mongodb": mongo_status}

@app.post("/api/ai/enrutamiento-inteligente", response_model=EnrutamientoResponse)
def enrutamiento_inteligente(req: EnrutamientoRequest):
    try:
        # Normalizaciones de inputs
        carga_norm = min(1.0, req.carga_raw / 20.0)
        horas_norm = min(1.0, req.horas_raw / 48.0)
        critico_norm = 1.0 if req.paso_critico else 0.0
        doc_cnt_norm = min(1.0, req.documentos_count / 10.0)
        doc_sz_norm = min(1.0, req.documentos_size_bytes / (10 * 1024 * 1024))

        preds = enrutamiento_service.predecir(carga_norm, horas_norm, critico_norm, doc_cnt_norm, doc_sz_norm)
        logger.info(f"TensorFlow enrutamiento inteligente predictions: {preds}")
        return EnrutamientoResponse(**preds)
    except Exception as e:
        logger.error(f"Error in enrutamiento_inteligente: {e}")
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)
