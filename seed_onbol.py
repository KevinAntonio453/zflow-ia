import random
import sys
from datetime import datetime, timedelta
from pymongo import MongoClient
from bson import ObjectId

import os

# Configuración de URI
MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017/zflow")
client = MongoClient(MONGO_URI)
db = client.get_database()

# HASH para password123 (BCrypt)
PASSWORD_HASH = "$2a$10$n2rJWBDu3Q41loRl6ekwcujLlbDqFxCh8.y8RaO54u9y8H7Qap2Z2"

print("--- INICIANDO SEEDING DE ONBOL RUMGAS ---")

# Helper function to build laid out BPMN XML
def build_bpmn_xml(process_id, collaboration_id, participant_id, lanes, steps, flows):
    max_y = max(s["y"] for s in steps)
    participant_height = max_y + 120
    participant_width = len(lanes) * 250
    
    xml_str = f'<?xml version="1.0" encoding="UTF-8"?>\n'
    xml_str += f'<bpmn:definitions xmlns:bpmn="http://www.omg.org/spec/BPMN/20100524/MODEL" '
    xml_str += f'xmlns:bpmndi="http://www.omg.org/spec/BPMN/20100524/DI" '
    xml_str += f'xmlns:dc="http://www.omg.org/spec/DD/20100524/DC" '
    xml_str += f'xmlns:di="http://www.omg.org/spec/DD/20100524/DI" '
    xml_str += f'id="Definitions_zflow" targetNamespace="http://zflow.io/schema/bpmn">\n'
    
    xml_str += f'  <bpmn:collaboration id="{collaboration_id}">\n'
    xml_str += f'    <bpmn:participant id="{participant_id}" name="ONBOL RUMGAS" processRef="{process_id}" />\n'
    xml_str += f'  </bpmn:collaboration>\n'
    
    xml_str += f'  <bpmn:process id="{process_id}" isExecutable="true">\n'
    
    xml_str += f'    <bpmn:laneSet id="LaneSet_1">\n'
    for l in lanes:
        xml_str += f'      <bpmn:lane id="{l["id"]}" name="{l["name"]}">\n'
        for s in steps:
            if s["lane"] == l["id"]:
                xml_str += f'        <bpmn:flowNodeRef>{s["id"]}</bpmn:flowNodeRef>\n'
        xml_str += f'      </bpmn:lane>\n'
    xml_str += f'    </bpmn:laneSet>\n'
    
    for s in steps:
        if s["type"] == "start":
            xml_str += f'    <bpmn:startEvent id="{s["id"]}" name="{s.get("name", "Inicio")}">\n'
            for f in flows:
                if f["source"] == s["id"]:
                    xml_str += f'      <bpmn:outgoing>{f["id"]}</bpmn:outgoing>\n'
            xml_str += f'    </bpmn:startEvent>\n'
        elif s["type"] == "end":
            xml_str += f'    <bpmn:endEvent id="{s["id"]}" name="{s.get("name", "Fin")}">\n'
            for f in flows:
                if f["target"] == s["id"]:
                    xml_str += f'      <bpmn:incoming>{f["id"]}</bpmn:incoming>\n'
            xml_str += f'    </bpmn:endEvent>\n'
        elif s["type"] == "task":
            xml_str += f'    <bpmn:task id="{s["id"]}" name="{s["name"]}">\n'
            for f in flows:
                if f["target"] == s["id"]:
                    xml_str += f'      <bpmn:incoming>{f["id"]}</bpmn:incoming>\n'
            for f in flows:
                if f["source"] == s["id"]:
                    xml_str += f'      <bpmn:outgoing>{f["id"]}</bpmn:outgoing>\n'
            xml_str += f'    </bpmn:task>\n'
        elif s["type"] == "gateway":
            g_type = s.get("gateway_type", "exclusiveGateway")
            xml_str += f'    <bpmn:{g_type} id="{s["id"]}" name="{s.get("name", "")}">\n'
            for f in flows:
                if f["target"] == s["id"]:
                    xml_str += f'      <bpmn:incoming>{f["id"]}</bpmn:incoming>\n'
            for f in flows:
                if f["source"] == s["id"]:
                    xml_str += f'      <bpmn:outgoing>{f["id"]}</bpmn:outgoing>\n'
            xml_str += f'    </bpmn:{g_type}>\n'
            
    for f in flows:
        cond_str = ""
        if f.get("condition"):
            cond_str = f'\n      <bpmn:conditionExpression>${{{f["condition"]}}}</bpmn:conditionExpression>\n    '
        xml_str += f'    <bpmn:sequenceFlow id="{f["id"]}" sourceRef="{f["source"]}" targetRef="{f["target"]}">{cond_str}</bpmn:sequenceFlow>\n'
        
    xml_str += f'  </bpmn:process>\n'
    
    xml_str += f'  <bpmndi:BPMNDiagram id="Diagram_1">\n'
    xml_str += f'    <bpmndi:BPMNPlane id="Plane_1" bpmnElement="{collaboration_id}">\n'
    
    xml_str += f'      <bpmndi:BPMNShape id="{participant_id}_di" bpmnElement="{participant_id}" isHorizontal="false">\n'
    xml_str += f'        <dc:Bounds x="20" y="60" width="{participant_width}" height="{participant_height}" />\n'
    xml_str += f'      </bpmndi:BPMNShape>\n'
    
    for idx, l in enumerate(lanes):
        lane_x = 20 + idx * 250
        xml_str += f'      <bpmndi:BPMNShape id="{l["id"]}_di" bpmnElement="{l["id"]}" isHorizontal="false">\n'
        xml_str += f'        <dc:Bounds x="{lane_x}" y="90" width="250" height="{participant_height - 30}" />\n'
        xml_str += f'      </bpmndi:BPMNShape>\n'
    
    step_coords = {}
    for s in steps:
        lane_names = [l["id"] for l in lanes]
        lane_idx = lane_names.index(s["lane"])
        lane_x = 20 + lane_idx * 250
        x_center = lane_x + 125
        
        if s["type"] == "start" or s["type"] == "end":
            width, height = 36, 36
        elif s["type"] == "gateway":
            width, height = 50, 50
        else:
            width, height = 100, 80
            
        x = x_center - (width // 2)
        y = s["y"] - (height // 2)
        
        xml_str += f'      <bpmndi:BPMNShape id="{s["id"]}_di" bpmnElement="{s["id"]}">\n'
        xml_str += f'        <dc:Bounds x="{x}" y="{y}" width="{width}" height="{height}" />\n'
        xml_str += f'      </bpmndi:BPMNShape>\n'
        
        step_coords[s["id"]] = {
            "x": x, "y": y, "w": width, "h": height,
            "x_center": x_center, "y_center": s["y"],
            "lane_idx": lane_idx
        }
        
    for f in flows:
        sc = step_coords[f["source"]]
        tc = step_coords[f["target"]]
        
        xml_str += f'      <bpmndi:BPMNEdge id="{f["id"]}_di" bpmnElement="{f["id"]}">\n'
        
        y_source_bottom = sc["y_center"] + (sc["h"] // 2)
        x_source_center = sc["x_center"]
        y_target_top = tc["y_center"] - (tc["h"] // 2)
        x_target_center = tc["x_center"]
        
        if tc["y_center"] < sc["y_center"]:
            wps = [
                (sc["x"], sc["y_center"]),
                (sc["x"] - 50, sc["y_center"]),
                (tc["x"] - 50, tc["y_center"]),
                (tc["x"], tc["y_center"])
            ]
        elif sc["lane_idx"] == tc["lane_idx"]:
            wps = [
                (x_source_center, y_source_bottom),
                (x_target_center, y_target_top)
            ]
        else:
            y_mid = (y_source_bottom + y_target_top) // 2
            wps = [
                (x_source_center, y_source_bottom),
                (x_source_center, y_mid),
                (x_target_center, y_mid),
                (x_target_center, y_target_top)
            ]
            
        for wp in wps:
            xml_str += f'        <di:waypoint x="{wp[0]}" y="{wp[1]}" />\n'
            
        xml_str += f'      </bpmndi:BPMNEdge>\n'
        
    xml_str += f'    </bpmndi:BPMNPlane>\n'
    xml_str += f'  </bpmndi:BPMNDiagram>\n'
    xml_str += f'</bpmn:definitions>'
    
    return xml_str

# 1. Limpieza de datos
print("Limpiando colecciones previas...")
db.usuarios.delete_many({})
db.departamentos.delete_many({})
db.politicas.delete_many({})
db.tramites.delete_many({})
db.auditoria.delete_many({})
db.documentos.delete_many({})
db.notificaciones.delete_many({})

# 2. Creación de Departamentos
print("Creando Departamentos...")
deptos = [
    {"nombre": "Técnica", "desc": "Inspectores y ingenieros matriculados"},
    {"nombre": "Administración", "desc": "Contratos, cobros y permisos ANH"},
    {"nombre": "Operaciones", "desc": "Cuadrilla técnica en terreno y soldadores"},
    {"nombre": "Gerencia", "desc": "Dirección general de la empresa"},
    {"nombre": "Soporte", "desc": "Atención al cliente y primer filtro"}
]

depto_map = {}
for d in deptos:
    res = db.departamentos.insert_one({
        "nombre": d["nombre"],
        "descripcion": d["desc"],
        "activo": True,
        "created_at": datetime.now() - timedelta(days=60),
        "_class": "com.Miproyecto.ZFlow.auth.domain.model.Departamento"
    })
    depto_map[d["nombre"]] = res.inserted_id

# 3. Creación de Usuarios
print("Creando Usuarios...")
admin_id = db.usuarios.insert_one({
    "nombre": "Administrador ONBOL",
    "email": "admin@onbol.com",
    "password_hash": PASSWORD_HASH,
    "rol": "ADMIN",
    "activo": True,
    "created_at": datetime.now() - timedelta(days=50),
    "_class": "com.Miproyecto.ZFlow.auth.domain.model.Usuario"
}).inserted_id

jefe_tecnica = db.usuarios.insert_one({
    "nombre": "Jefe de Técnica",
    "email": "jefe.tecnica@onbol.com",
    "password_hash": PASSWORD_HASH,
    "rol": "JEFE",
    "departamento_id": str(depto_map["Técnica"]),
    "activo": True,
    "created_at": datetime.now() - timedelta(days=50),
    "_class": "com.Miproyecto.ZFlow.auth.domain.model.Usuario"
}).inserted_id

jefe_ops = db.usuarios.insert_one({
    "nombre": "Jefe de Operaciones",
    "email": "jefe.ops@onbol.com",
    "password_hash": PASSWORD_HASH,
    "rol": "JEFE",
    "departamento_id": str(depto_map["Operaciones"]),
    "activo": True,
    "created_at": datetime.now() - timedelta(days=50),
    "_class": "com.Miproyecto.ZFlow.auth.domain.model.Usuario"
}).inserted_id

db.departamentos.update_one({"_id": depto_map["Técnica"]}, {"$set": {"jefe_id": str(jefe_tecnica)}})
db.departamentos.update_one({"_id": depto_map["Operaciones"]}, {"$set": {"jefe_id": str(jefe_ops)}})

funcionarios_ids = []
user_idx = 1

def crear_funcionarios(depto_nombre, count):
    global user_idx
    ids = []
    for _ in range(count):
        res = db.usuarios.insert_one({
            "nombre": f"Funcionario {depto_nombre} {user_idx}",
            "email": f"func.{depto_nombre.lower()}{user_idx}@onbol.com",
            "password_hash": PASSWORD_HASH,
            "rol": "FUNCIONARIO",
            "departamento_id": str(depto_map[depto_nombre]),
            "activo": True,
            "created_at": datetime.now() - timedelta(days=45),
            "_class": "com.Miproyecto.ZFlow.auth.domain.model.Usuario"
        })
        ids.append(res.inserted_id)
        user_idx += 1
    return ids

funcs_tecnica = crear_funcionarios("Técnica", 25)
funcs_admin = crear_funcionarios("Administración", 20)
funcs_ops = crear_funcionarios("Operaciones", 35)

funcionarios_ids.extend(funcs_tecnica)
funcionarios_ids.extend(funcs_admin)
funcionarios_ids.extend(funcs_ops)

clientes_ids = []
for i in range(1, 21):
    res = db.usuarios.insert_one({
        "nombre": f"Cliente ONBOL {i}",
        "email": f"cliente{i}@gmail.com",
        "password_hash": PASSWORD_HASH,
        "rol": "CLIENTE",
        "activo": True,
        "created_at": datetime.now() - timedelta(days=45),
        "_class": "com.Miproyecto.ZFlow.auth.domain.model.Usuario"
    })
    clientes_ids.append(res.inserted_id)

# 4. Creación de Políticas (BPMN XML)
print("Creando Políticas...")

# layouts
p1_lanes = [{"id": "Lane_Cliente", "name": "Cliente"}, {"id": "Lane_Tecnica", "name": "Técnica"}, {"id": "Lane_Admin", "name": "Administración"}, {"id": "Lane_Ops", "name": "Operaciones"}]
p1_steps = [
    {"id": "StartEvent_1", "type": "start", "lane": "Lane_Cliente", "name": "Inicio", "y": 120},
    {"id": "Paso1", "type": "task", "lane": "Lane_Cliente", "name": "Solicitud de Conexión", "y": 220},
    {"id": "Paso2", "type": "task", "lane": "Lane_Tecnica", "name": "Inspección y Factibilidad Técnica", "y": 320},
    {"id": "Gate1", "type": "gateway", "lane": "Lane_Tecnica", "name": "Factible?", "y": 420},
    {"id": "Fork1", "type": "gateway", "lane": "Lane_Ops", "gateway_type": "parallelGateway", "name": "Fork", "y": 520},
    {"id": "Paso3A", "type": "task", "lane": "Lane_Admin", "name": "Aprobación del Proyecto (ANH)", "y": 620},
    {"id": "Paso3B", "type": "task", "lane": "Lane_Ops", "name": "Acopio de Materiales y Logística", "y": 620},
    {"id": "Join1", "type": "gateway", "lane": "Lane_Ops", "gateway_type": "parallelGateway", "name": "Join", "y": 720},
    {"id": "Paso4", "type": "task", "lane": "Lane_Ops", "name": "Ejecución de Obra de Red Interna", "y": 820},
    {"id": "Paso5", "type": "task", "lane": "Lane_Ops", "name": "Prueba de Hermeticidad Inicial", "y": 920},
    {"id": "Gate2", "type": "gateway", "lane": "Lane_Ops", "name": "Presión Ok?", "y": 1020},
    {"id": "Paso6", "type": "task", "lane": "Lane_Tecnica", "name": "Inspección Final de YPFB y Habilitación", "y": 1120},
    {"id": "EndEvent_1", "type": "end", "lane": "Lane_Tecnica", "name": "Fin", "y": 1220}
]
p1_flows = [
    {"id": "Flow_0", "source": "StartEvent_1", "target": "Paso1"},
    {"id": "Flow_1", "source": "Paso1", "target": "Paso2"},
    {"id": "Flow_2", "source": "Paso2", "target": "Gate1"},
    {"id": "Flow_2a", "source": "Gate1", "target": "Paso1", "condition": "factible == false"},
    {"id": "Flow_2b", "source": "Gate1", "target": "Fork1", "condition": "factible == true"},
    {"id": "Flow_3a", "source": "Fork1", "target": "Paso3A"},
    {"id": "Flow_3b", "source": "Fork1", "target": "Paso3B"},
    {"id": "Flow_4a", "source": "Paso3A", "target": "Join1"},
    {"id": "Flow_4b", "source": "Paso3B", "target": "Join1"},
    {"id": "Flow_5", "source": "Join1", "target": "Paso4"},
    {"id": "Flow_6", "source": "Paso4", "target": "Paso5"},
    {"id": "Flow_7", "source": "Paso5", "target": "Gate2"},
    {"id": "Flow_7a", "source": "Gate2", "target": "Paso4", "condition": "presionOk == false"},
    {"id": "Flow_7b", "source": "Gate2", "target": "Paso6", "condition": "presionOk == true"},
    {"id": "Flow_8", "source": "Paso6", "target": "EndEvent_1"}
]

p2_lanes = [{"id": "Lane_Cliente", "name": "Cliente"}, {"id": "Lane_Admin", "name": "Administración"}, {"id": "Lane_Tecnica", "name": "Técnica"}]
p2_steps = [
    {"id": "StartEvent_1", "type": "start", "lane": "Lane_Cliente", "name": "Inicio", "y": 120},
    {"id": "Paso1", "type": "task", "lane": "Lane_Cliente", "name": "Solicitud de Reconexión", "y": 220},
    {"id": "Paso2", "type": "task", "lane": "Lane_Admin", "name": "Validación Comercial", "y": 320},
    {"id": "Paso3", "type": "task", "lane": "Lane_Tecnica", "name": "Inspección y Colocación de Medidor", "y": 420},
    {"id": "EndEvent_1", "type": "end", "lane": "Lane_Tecnica", "name": "Fin", "y": 520}
]
p2_flows = [
    {"id": "Flow_0", "source": "StartEvent_1", "target": "Paso1"},
    {"id": "Flow_1", "source": "Paso1", "target": "Paso2"},
    {"id": "Flow_2", "source": "Paso2", "target": "Paso3"},
    {"id": "Flow_3", "source": "Paso3", "target": "EndEvent_1"}
]

p3_lanes = [{"id": "Lane_Cliente", "name": "Cliente"}, {"id": "Lane_Tecnica", "name": "Técnica"}, {"id": "Lane_Admin", "name": "Administración"}]
p3_steps = [
    {"id": "StartEvent_1", "type": "start", "lane": "Lane_Cliente", "name": "Inicio", "y": 120},
    {"id": "Paso1", "type": "task", "lane": "Lane_Cliente", "name": "Reserva de Turno de Inspección", "y": 220},
    {"id": "Paso2", "type": "task", "lane": "Lane_Tecnica", "name": "Inspección de Seguridad de Artefactos", "y": 320},
    {"id": "Gate1", "type": "gateway", "lane": "Lane_Tecnica", "name": "Cumple Norma?", "y": 420},
    {"id": "Paso3", "type": "task", "lane": "Lane_Admin", "name": "Certificación Regulatoria", "y": 520},
    {"id": "EndEvent_1", "type": "end", "lane": "Lane_Admin", "name": "Fin", "y": 620}
]
p3_flows = [
    {"id": "Flow_0", "source": "StartEvent_1", "target": "Paso1"},
    {"id": "Flow_1", "source": "Paso1", "target": "Paso2"},
    {"id": "Flow_2", "source": "Paso2", "target": "Gate1"},
    {"id": "Flow_2a", "source": "Gate1", "target": "Paso1", "condition": "aprobado == false"},
    {"id": "Flow_2b", "source": "Gate1", "target": "Paso3", "condition": "aprobado == true"},
    {"id": "Flow_3", "source": "Paso3", "target": "EndEvent_1"}
]

p4_lanes = [{"id": "Lane_Cliente", "name": "Cliente"}, {"id": "Lane_Ops", "name": "Operaciones"}, {"id": "Lane_Tecnica", "name": "Técnica"}]
p4_steps = [
    {"id": "StartEvent_1", "type": "start", "lane": "Lane_Cliente", "name": "Inicio", "y": 120},
    {"id": "Paso1", "type": "task", "lane": "Lane_Cliente", "name": "Solicitud de Prueba", "y": 220},
    {"id": "Paso2", "type": "task", "lane": "Lane_Ops", "name": "Prueba de Presión y Fugas", "y": 320},
    {"id": "Gate1", "type": "gateway", "lane": "Lane_Ops", "name": "Tiene Fuga?", "y": 420},
    {"id": "Paso3", "type": "task", "lane": "Lane_Tecnica", "name": "Auditoría y Certificado", "y": 520},
    {"id": "EndEvent_1", "type": "end", "lane": "Lane_Tecnica", "name": "Fin", "y": 620}
]
p4_flows = [
    {"id": "Flow_0", "source": "StartEvent_1", "target": "Paso1"},
    {"id": "Flow_1", "source": "Paso1", "target": "Paso2"},
    {"id": "Flow_2", "source": "Paso2", "target": "Gate1"},
    {"id": "Flow_2a", "source": "Gate1", "target": "Paso1", "condition": "fuga == true"},
    {"id": "Flow_2b", "source": "Gate1", "target": "Paso3", "condition": "fuga == false"},
    {"id": "Flow_3", "source": "Paso3", "target": "EndEvent_1"}
]

politicas_data = [
    ("Instalación Nueva (Doméstica/Comercial)", "Flujo de aprobación y tendido físico de gas residencial de ONBOL RUMGAS", p1_lanes, p1_steps, p1_flows),
    ("Reconexión y Cambio de Medidor", "Reactivación rápida de suministro por cambio de titular o medidor", p2_lanes, p2_steps, p2_flows),
    ("Inspección Quinquenal Obligatoria", "Revisión técnica de seguridad cada 5 años en el domicilio", p3_lanes, p3_steps, p3_flows),
    ("Prueba de Hermeticidad", "Ensayo de presión de cañería interna para descarte de pérdidas", p4_lanes, p4_steps, p4_flows)
]

politicas = []
pol_map = {}

for name, desc, lanes, steps, flows in politicas_data:
    xml = build_bpmn_xml("Process_1", "Collaboration_1", "Participant_1", lanes, steps, flows)
    
    # Map activities list for Politica model
    actividades = []
    for s in steps:
        if s["type"] == "task":
            # Map lane id back to lane name (e.g. Lane_Cliente -> Cliente)
            lane_obj = [l for l in lanes if l["id"] == s["lane"]][0]
            lane_name = lane_obj["name"]
            
            act_doc = {
                "actividad_id": s["id"],
                "nombre": s["name"],
                "lane_name": lane_name,
                "tipo_flujo": "SECUENCIAL" if s["id"] != "Paso3A" and s["id"] != "Paso3B" else "PARALELO",
                "formulario": []
            }
            # Add specific forms
            if name.startswith("Instalación"):
                if s["id"] == "Paso1":
                    act_doc["formulario"] = [{"id": "categoria", "nombre": "Categoría", "tipo": "SELECTOR", "opciones": ["Doméstica", "Comercial", "Multifamiliar"], "requerido": True}, {"id": "bocas", "nombre": "Bocas de gas", "tipo": "NUMERO", "requerido": True}]
                elif s["id"] == "Paso2":
                    act_doc["formulario"] = [{"id": "factible", "nombre": "Es Factible", "tipo": "SELECTOR", "opciones": ["true", "false"], "requerido": True}, {"id": "metros", "nombre": "Metros lineales estimados", "tipo": "NUMERO", "requerido": True}]
                elif s["id"] == "Paso3A":
                    act_doc["formulario"] = [{"id": "expediente", "nombre": "Nro. de Expediente ANH", "tipo": "TEXTO", "requerido": True}]
                elif s["id"] == "Paso3B":
                    act_doc["formulario"] = [{"id": "soldador", "nombre": "Nombre de Soldador asignado", "tipo": "TEXTO", "requerido": True}]
                elif s["id"] == "Paso4":
                    act_doc["formulario"] = [{"id": "diasObra", "nombre": "Días aplicados de obra", "tipo": "NUMERO", "requerido": True}]
                elif s["id"] == "Paso5":
                    act_doc["formulario"] = [{"id": "presionOk", "nombre": "Prueba Conforme", "tipo": "SELECTOR", "opciones": ["true", "false"], "requerido": True}, {"id": "psi", "nombre": "Presión obtenida (PSI)", "tipo": "NUMERO", "requerido": True}]
                elif s["id"] == "Paso6":
                    act_doc["formulario"] = [{"id": "medidor", "nombre": "Nro. de Medidor asignado", "tipo": "TEXTO", "requerido": True}]
            elif name.startswith("Reconexión"):
                if s["id"] == "Paso1":
                    act_doc["formulario"] = [{"id": "medidorAntiguo", "nombre": "Nro. Medidor Anterior", "tipo": "TEXTO", "requerido": True}]
                elif s["id"] == "Paso2":
                    act_doc["formulario"] = [{"id": "deuda", "nombre": "Registra Deudas", "tipo": "SELECTOR", "opciones": ["no", "si"], "requerido": True}]
                elif s["id"] == "Paso3":
                    act_doc["formulario"] = [{"id": "medidorNuevo", "nombre": "Nro. Nuevo Medidor", "tipo": "TEXTO", "requerido": True}]
            elif name.startswith("Inspección"):
                if s["id"] == "Paso1":
                    act_doc["formulario"] = [{"id": "fechaTurno", "nombre": "Fecha sugerida", "tipo": "FECHA", "requerido": True}]
                elif s["id"] == "Paso2":
                    act_doc["formulario"] = [{"id": "aprobado", "nombre": "Cumple Norma de Seguridad", "tipo": "SELECTOR", "opciones": ["true", "false"], "requerido": True}, {"id": "observacion", "nombre": "Observaciones", "tipo": "TEXTO", "requerido": False}]
                elif s["id"] == "Paso3":
                    act_doc["formulario"] = [{"id": "oblea", "nombre": "Nro. de Oblea Quinquenal", "tipo": "TEXTO", "requerido": True}]
            elif name.startswith("Prueba"):
                if s["id"] == "Paso1":
                    act_doc["formulario"] = [{"id": "motivo", "nombre": "Motivo de prueba", "tipo": "SELECTOR", "opciones": ["Fuga detectada", "Reconexión", "Ampliación interna"], "requerido": True}]
                elif s["id"] == "Paso2":
                    act_doc["formulario"] = [{"id": "fuga", "nombre": "Se detectó fuga", "tipo": "SELECTOR", "opciones": ["true", "false"], "requerido": True}, {"id": "presionPsi", "nombre": "Presión inyectada (PSI)", "tipo": "NUMERO", "requerido": True}]
                elif s["id"] == "Paso3":
                    act_doc["formulario"] = [{"id": "certificado", "nombre": "Nro. de Certificado Hermeticidad", "tipo": "TEXTO", "requerido": True}]
            
            # Set department role routing
            if lane_name in depto_map:
                act_doc["responsable_tipo"] = "DEPARTAMENTO"
                
            actividades.append(act_doc)

    res = db.politicas.insert_one({
        "nombre": name,
        "descripcion": desc,
        "estado": "ACTIVA",
        "diagrama_bpmn": xml,
        "creado_por": str(admin_id),
        "actividades": actividades,
        "created_at": datetime.now() - timedelta(days=60),
        "_class": "com.Miproyecto.ZFlow.workflow.domain.model.Politica"
    })
    pol_map[name] = res.inserted_id

# 5. Inyección masiva de 5000 trámites
print("Generando 5000 Trámites...")
tramites_to_insert = []
bitacoras_to_insert = []

fechas_posibles = [datetime.now() - timedelta(days=random.randint(1, 30), hours=random.randint(0, 23)) for _ in range(5000)]
fechas_posibles.sort()

# Acciones de bitácora
bitacoras_list = [
    "ver_documento", "subir_documento", "modificar_documento", 
    "completar_tarea", "crear_politica", "modificar_politica", 
    "activar_politica", "desactivar_politica"
]

for idx in range(5000):
    cliente = random.choice(clientes_ids)
    fecha_inicio = fechas_posibles[idx]
    
    # Elegir servicio
    pol_nombre = random.choice(list(pol_map.keys()))
    pol_id = pol_map[pol_nombre]
    
    # Decidir estado
    estado = random.choices(["COMPLETADO", "EN_PROCESO", "PAUSADO", "CANCELADO"], weights=[75, 15, 7, 3], k=1)[0]
    
    historial = []
    pasos_activos = []
    
    # Todos empiezan con Paso 1 del Cliente
    fecha_fin_1 = fecha_inicio + timedelta(minutes=random.randint(10, 120))
    
    if pol_nombre == "Instalación Nueva (Doméstica/Comercial)":
        historial.append({
            "actividad_id": "Paso1",
            "funcionario_id": str(cliente),
            "datos_formulario": {"categoria": random.choice(["Doméstica", "Comercial"]), "bocas": random.randint(1, 5)},
            "inicio": fecha_inicio,
            "fin": fecha_fin_1,
            "estado": "COMPLETADO"
        })
        
        if estado == "CANCELADO":
            pass
        elif estado == "COMPLETADO":
            func2 = random.choice(funcs_tecnica)
            f_ini2 = fecha_fin_1 + timedelta(minutes=10)
            f_fin2 = f_ini2 + timedelta(hours=random.randint(1, 24))
            historial.append({
                "actividad_id": "Paso2",
                "funcionario_id": str(func2),
                "departamento_id": str(depto_map["Técnica"]),
                "inicio": f_ini2,
                "fin": f_fin2,
                "estado": "COMPLETADO",
                "datos_formulario": {"factible": "true", "metros": random.randint(5, 50)}
            })
            
            f_ini3 = f_fin2 + timedelta(minutes=10)
            f_fin3 = f_ini3 + timedelta(hours=random.randint(5, 48))
            func3a = random.choice(funcs_admin)
            historial.append({
                "actividad_id": "Paso3A",
                "funcionario_id": str(func3a),
                "departamento_id": str(depto_map["Administración"]),
                "inicio": f_ini3,
                "fin": f_fin3,
                "estado": "COMPLETADO",
                "datos_formulario": {"expediente": f"EXP-{random.randint(1000, 9999)}"}
            })
            
            func3b = random.choice(funcs_ops)
            historial.append({
                "actividad_id": "Paso3B",
                "funcionario_id": str(func3b),
                "departamento_id": str(depto_map["Operaciones"]),
                "inicio": f_ini3,
                "fin": f_fin3,
                "estado": "COMPLETADO",
                "datos_formulario": {"soldador": f"Matriculado {random.randint(1, 10)}"}
            })
            
            f_ini4 = f_fin3 + timedelta(minutes=10)
            f_fin4 = f_ini4 + timedelta(hours=random.randint(24, 72))
            func4 = random.choice(funcs_ops)
            historial.append({
                "actividad_id": "Paso4",
                "funcionario_id": str(func4),
                "departamento_id": str(depto_map["Operaciones"]),
                "inicio": f_ini4,
                "fin": f_fin4,
                "estado": "COMPLETADO",
                "datos_formulario": {"diasObra": random.randint(2, 5)}
            })
            
            f_ini5 = f_fin4 + timedelta(minutes=10)
            f_fin5 = f_ini5 + timedelta(hours=random.randint(1, 6))
            func5 = random.choice(funcs_ops)
            historial.append({
                "actividad_id": "Paso5",
                "funcionario_id": str(func5),
                "departamento_id": str(depto_map["Operaciones"]),
                "inicio": f_ini5,
                "fin": f_fin5,
                "estado": "COMPLETADO",
                "datos_formulario": {"presionOk": "true", "psi": random.randint(10, 20)}
            })
            
            f_ini6 = f_fin5 + timedelta(minutes=10)
            f_fin6 = f_ini6 + timedelta(hours=random.randint(1, 12))
            func6 = random.choice(funcs_tecnica)
            historial.append({
                "actividad_id": "Paso6",
                "funcionario_id": str(func6),
                "departamento_id": str(depto_map["Técnica"]),
                "inicio": f_ini6,
                "fin": f_fin6,
                "estado": "COMPLETADO",
                "datos_formulario": {"medidor": f"MED-{random.randint(100000, 999999)}"}
            })
            
        elif estado == "EN_PROCESO":
            func2 = random.choice(funcs_tecnica)
            f_ini2 = fecha_fin_1 + timedelta(minutes=10)
            historial.append({
                "actividad_id": "Paso2",
                "funcionario_id": str(func2),
                "departamento_id": str(depto_map["Técnica"]),
                "inicio": f_ini2,
                "fin": None,
                "estado": "EN_PROCESO"
            })
            pasos_activos.append("Paso2")
            
        elif estado == "PAUSADO":
            func2 = random.choice(funcs_tecnica)
            f_ini2 = fecha_fin_1 - timedelta(hours=30)
            historial.append({
                "actividad_id": "Paso2",
                "funcionario_id": str(func2),
                "departamento_id": str(depto_map["Técnica"]),
                "inicio": f_ini2,
                "fin": None,
                "estado": "PAUSADO"
            })
            pasos_activos.append("Paso2")

    elif pol_nombre == "Reconexión y Cambio de Medidor":
        historial.append({
            "actividad_id": "Paso1",
            "funcionario_id": str(cliente),
            "datos_formulario": {"medidorAntiguo": f"MED-{random.randint(100000, 999999)}"},
            "inicio": fecha_inicio,
            "fin": fecha_fin_1,
            "estado": "COMPLETADO"
        })
        
        if estado == "COMPLETADO":
            func2 = random.choice(funcs_admin)
            f_ini2 = fecha_fin_1 + timedelta(minutes=10)
            f_fin2 = f_ini2 + timedelta(hours=random.randint(1, 8))
            historial.append({
                "actividad_id": "Paso2",
                "funcionario_id": str(func2),
                "departamento_id": str(depto_map["Administración"]),
                "inicio": f_ini2,
                "fin": f_fin2,
                "estado": "COMPLETADO",
                "datos_formulario": {"deuda": "no"}
            })
            
            func3 = random.choice(funcs_tecnica)
            f_ini3 = f_fin2 + timedelta(minutes=10)
            f_fin3 = f_ini3 + timedelta(hours=random.randint(1, 12))
            historial.append({
                "actividad_id": "Paso3",
                "funcionario_id": str(func3),
                "departamento_id": str(depto_map["Técnica"]),
                "inicio": f_ini3,
                "fin": f_fin3,
                "estado": "COMPLETADO",
                "datos_formulario": {"medidorNuevo": f"MED-{random.randint(100000, 999999)}"}
            })
        elif estado == "EN_PROCESO":
            func2 = random.choice(funcs_admin)
            f_ini2 = fecha_fin_1 + timedelta(minutes=10)
            historial.append({
                "actividad_id": "Paso2",
                "funcionario_id": str(func2),
                "departamento_id": str(depto_map["Administración"]),
                "inicio": f_ini2,
                "fin": None,
                "estado": "EN_PROCESO"
            })
            pasos_activos.append("Paso2")
        elif estado == "PAUSADO":
            func2 = random.choice(funcs_admin)
            f_ini2 = fecha_fin_1 - timedelta(hours=30)
            historial.append({
                "actividad_id": "Paso2",
                "funcionario_id": str(func2),
                "departamento_id": str(depto_map["Administración"]),
                "inicio": f_ini2,
                "fin": None,
                "estado": "PAUSADO"
            })
            pasos_activos.append("Paso2")

    else:
        historial.append({
            "actividad_id": "Paso1",
            "funcionario_id": str(cliente),
            "datos_formulario": {"motivo": "Reconexión", "fechaTurno": "2026-06-20"},
            "inicio": fecha_inicio,
            "fin": fecha_fin_1,
            "estado": "COMPLETADO"
        })
        if estado == "COMPLETADO":
            func2 = random.choice(funcs_tecnica if pol_nombre == "Inspección Quinquenal Obligatoria" else funcs_ops)
            f_ini2 = fecha_fin_1 + timedelta(minutes=10)
            f_fin2 = f_ini2 + timedelta(hours=random.randint(1, 8))
            historial.append({
                "actividad_id": "Paso2",
                "funcionario_id": str(func2),
                "departamento_id": str(depto_map["Técnica"] if pol_nombre == "Inspección Quinquenal Obligatoria" else depto_map["Operaciones"]),
                "inicio": f_ini2,
                "fin": f_fin2,
                "estado": "COMPLETADO",
                "datos_formulario": {"aprobado": "true", "fuga": "false", "presionPsi": 15}
            })
            
            func3 = random.choice(funcs_admin if pol_nombre == "Inspección Quinquenal Obligatoria" else funcs_tecnica)
            f_ini3 = f_fin2 + timedelta(minutes=10)
            f_fin3 = f_ini3 + timedelta(hours=random.randint(1, 12))
            historial.append({
                "actividad_id": "Paso3",
                "funcionario_id": str(func3),
                "departamento_id": str(depto_map["Administración"] if pol_nombre == "Inspección Quinquenal Obligatoria" else depto_map["Técnica"]),
                "inicio": f_ini3,
                "fin": f_fin3,
                "estado": "COMPLETADO",
                "datos_formulario": {"oblea": f"OBL-{random.randint(1000, 9999)}", "certificado": f"CERT-{random.randint(1000, 9999)}"}
            })
        elif estado == "EN_PROCESO":
            func2 = random.choice(funcs_tecnica if pol_nombre == "Inspección Quinquenal Obligatoria" else funcs_ops)
            f_ini2 = fecha_fin_1 + timedelta(minutes=10)
            historial.append({
                "actividad_id": "Paso2",
                "funcionario_id": str(func2),
                "departamento_id": str(depto_map["Técnica"] if pol_nombre == "Inspección Quinquenal Obligatoria" else depto_map["Operaciones"]),
                "inicio": f_ini2,
                "fin": None,
                "estado": "EN_PROCESO"
            })
            pasos_activos.append("Paso2")
        elif estado == "PAUSADO":
            func2 = random.choice(funcs_tecnica if pol_nombre == "Inspección Quinquenal Obligatoria" else funcs_ops)
            f_ini2 = fecha_fin_1 - timedelta(hours=30)
            historial.append({
                "actividad_id": "Paso2",
                "funcionario_id": str(func2),
                "departamento_id": str(depto_map["Técnica"] if pol_nombre == "Inspección Quinquenal Obligatoria" else depto_map["Operaciones"]),
                "inicio": f_ini2,
                "fin": None,
                "estado": "PAUSADO"
            })
            pasos_activos.append("Paso2")

    tramite_doc = {
        "politica_id": str(pol_id),
        "cliente_id": str(cliente),
        "estado": estado,
        "paso_actual": pasos_activos,
        "s3_bucket": f"zflow-tramite-seed-{idx}",
        "historial": historial,
        "created_at": fecha_inicio,
        "updated_at": datetime.now(),
        "_class": "com.Miproyecto.ZFlow.workflow.domain.model.Tramite"
    }
    tramites_to_insert.append(tramite_doc)

print("Insertando Trámites en MongoDB (Bulk)...")
result_tramites = db.tramites.insert_many(tramites_to_insert)

# 6. Crear registros de auditoría
print("Generando 10,000 registros de Bitácora...")
tramite_inserted_ids = result_tramites.inserted_ids

# Cargar todos los usuarios en memoria para evitar consultas recurrentes (10,000 queries lentas en la nube)
print("Cargando usuarios en memoria...")
todos_usuarios = list(db.usuarios.find({}, {"nombre": 1, "email": 1}))
usuarios_cache = {user["_id"]: user for user in todos_usuarios}

for aud_idx in range(10000):
    user_id = random.choice(funcionarios_ids + clientes_ids)
    accion = random.choice(bitacoras_list)
    entidad_tipo = random.choice(["documento", "tramite", "politica", "usuario"])
    
    entidad_id = random.choice(tramite_inserted_ids) if entidad_tipo == "tramite" else ObjectId()
    
    user_obj = usuarios_cache.get(user_id)
    user_nombre = user_obj["nombre"] if user_obj else "Sistema"
    user_email = user_obj["email"] if user_obj else "sistema@onbol.com"
    
    detalles = {
        "nombreUsuario": user_nombre,
        "emailUsuario": user_email,
        "descripcion": f"Simulación de la acción {accion} para el trámite {entidad_id}"
    }
    
    if entidad_tipo == "politica":
        detalles["politicaNombre"] = random.choice(list(pol_map.keys()))
    elif entidad_tipo == "documento":
        detalles["documentoNombre"] = f"documento_{aud_idx}.pdf"
    elif entidad_tipo == "tramite":
        detalles["politicaNombre"] = random.choice(list(pol_map.keys()))

    bitacoras_to_insert.append({
        "usuario_id": str(user_id),
        "accion": accion.upper(),
        "entidad_tipo": entidad_tipo.upper(),
        "entidad_id": str(entidad_id),
        "detalle": detalles,
        "ip": f"192.168.1.{random.randint(10, 250)}",
        "created_at": datetime.now() - timedelta(days=random.randint(1, 30), minutes=random.randint(1, 1440)),
        "_class": "com.Miproyecto.ZFlow.shared.model.Auditoria"
    })

print("Insertando Bitácora de Actividad en MongoDB (Bulk)...")
db.auditoria.insert_many(bitacoras_to_insert)

print("--- SEEDING COMPLETADO CON ÉXITO PARA COMBO RUMGAS ---")
