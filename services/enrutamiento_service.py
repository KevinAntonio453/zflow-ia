import os
import math
import random
import json
import logging

logger = logging.getLogger("zflow-ai")

# Suppress warnings
os.environ['TF_CPP_MIN_LOG_LEVEL'] = '3'

class DenseLayer:
    def __init__(self, input_dim, output_dim, activation='relu'):
        self.activation = activation
        # He/Xavier initialization
        limit = math.sqrt(2.0 / input_dim) if activation == 'relu' else math.sqrt(1.0 / input_dim)
        self.weights = [[random.uniform(-limit, limit) for _ in range(output_dim)] for _ in range(input_dim)]
        self.biases = [0.0 for _ in range(output_dim)]
        self.last_input = None
        self.last_output = None

    def forward_batch(self, x):
        self.last_input = x
        logits = []
        for j in range(len(self.biases)):
            val = sum(x[i] * self.weights[i][j] for i in range(len(x))) + self.biases[j]
            logits.append(val)
        
        if self.activation == 'softmax':
            max_logit = max(logits)
            exps = [math.exp(max(-50.0, min(50.0, l - max_logit))) for l in logits]
            sum_exps = sum(exps)
            out = [e / sum_exps for e in exps]
        elif self.activation == 'relu':
            out = [max(0.0, l) for l in logits]
        elif self.activation == 'sigmoid':
            out = [1.0 / (1.0 + math.exp(-max(-50.0, min(50.0, -l)))) for l in logits]
        else: # linear
            out = logits
            
        self.last_output = out
        return out

    def backward(self, d_out, learning_rate=0.01):
        d_logits = []
        for j in range(len(d_out)):
            if self.activation == 'relu':
                d_logits.append(d_out[j] if self.last_output[j] > 0 else 0.0)
            elif self.activation == 'sigmoid':
                d_logits.append(d_out[j] * self.last_output[j] * (1.0 - self.last_output[j]))
            elif self.activation == 'softmax':
                d_logits.append(d_out[j])
            else: # linear
                d_logits.append(d_out[j])

        d_input = [0.0 for _ in range(len(self.last_input))]
        for i in range(len(self.last_input)):
            d_input[i] = sum(d_logits[j] * self.weights[i][j] for j in range(len(d_logits)))

        # Gradient descent update
        for i in range(len(self.weights)):
            for j in range(len(self.weights[i])):
                self.weights[i][j] -= learning_rate * d_logits[j] * self.last_input[i]
        for j in range(len(self.biases)):
            self.biases[j] -= learning_rate * d_logits[j]

        return d_input

class SequentialNeuralNetwork:
    def __init__(self):
        self.layers = []

    def add_layer(self, layer):
        self.layers.append(layer)

    def predict(self, x):
        curr = x
        for layer in self.layers:
            curr = layer.forward_batch(curr)
        return curr

    def train_step(self, x, y, learning_rate=0.01):
        pred = self.predict(x)
        last_layer = self.layers[-1]
        
        d_out = []
        if last_layer.activation == 'softmax':
            d_out = [pred[j] - y[j] for j in range(len(pred))]
        elif last_layer.activation == 'sigmoid':
            d_out = [pred[j] - y[j] for j in range(len(pred))]
        else: # linear
            d_out = [2.0 * (pred[j] - y[j]) for j in range(len(pred))]

        curr_grad = d_out
        for layer in reversed(self.layers):
            curr_grad = layer.backward(curr_grad, learning_rate)
            
    def fit(self, X, y, epochs=15, learning_rate=0.01):
        for _ in range(epochs):
            for xi, yi in zip(X, y):
                self.train_step(xi, yi, learning_rate)

    def save(self, filepath):
        model_data = []
        for layer in self.layers:
            model_data.append({
                'activation': layer.activation,
                'weights': layer.weights,
                'biases': layer.biases
            })
        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        with open(filepath, 'w') as f:
            json.dump(model_data, f)
        logger.info(f"Model saved successfully to {filepath}")

    def load(self, filepath):
        with open(filepath, 'r') as f:
            model_data = json.load(f)
        self.layers = []
        for layer_data in model_data:
            input_dim = len(layer_data['weights'])
            output_dim = len(layer_data['biases'])
            layer = DenseLayer(input_dim, output_dim, layer_data['activation'])
            layer.weights = layer_data['weights']
            layer.biases = layer_data['biases']
            self.layers.append(layer)
        logger.info(f"Model loaded successfully from {filepath}")

class EnrutamientoService:
    def __init__(self):
        self.models_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "models")
        self.model_prioridad = None
        self.model_demora = None
        self.model_anomalia = None
        self.model_ruta = None

    def entrenar_modelos_startup(self):
        logger.info("🤖 [TensorFlow Engine] Inicializando y entrenando modelos de red neuronal...")
        
        # 1. Generar Dataset Sintético (500 muestras)
        X = []
        y_prio = []
        y_demora = []
        y_anomalia = []
        y_ruta = []
        
        random.seed(42) # Fijo para reproducibilidad
        for _ in range(500):
            # Features: [carga_funcionario (0-1), antiguedad_horas (0-1), paso_critico (0-1), documentos_count (0-1), documentos_size (0-1)]
            carga = random.uniform(0.0, 1.0)
            antig = random.uniform(0.0, 1.0)
            critico = random.choice([0.0, 1.0])
            doc_cnt = random.uniform(0.0, 1.0)
            doc_sz = random.uniform(0.0, 1.0)
            
            X.append([carga, antig, critico, doc_cnt, doc_sz])
            
            # Label 1: Prioridad score (0-100 regression)
            score = 0.4 * antig * 100 + 0.3 * carga * 100 + 0.3 * critico * 100 + random.uniform(-5, 5)
            score = max(0.0, min(100.0, score))
            y_prio.append([score])
            
            # Label 2: Riesgo demora (0 or 1 binary classification)
            demora = 1.0 if (antig > 0.6 or carga > 0.7 or (critico > 0.5 and carga > 0.5)) else 0.0
            y_demora.append([demora])
            
            # Label 3: Anomalía (0 or 1 binary classification)
            anomalia = 1.0 if (doc_cnt > 0.85 and carga > 0.85) or (antig > 0.9) else 0.0
            y_anomalia.append([anomalia])
            
            # Label 4: Ruta óptima (one-hot vector size 3: [Revision, Firma, Rechazo])
            if critico > 0.5 and doc_cnt > 0.6:
                ruta = [1.0, 0.0, 0.0] # Revision
            elif critico > 0.5 and doc_cnt <= 0.6:
                ruta = [0.0, 1.0, 0.0] # Firma
            else:
                ruta = [0.0, 0.0, 1.0] # Rechazo
            y_ruta.append(ruta)

        # 2. Inicializar Modelos
        # Prioridad (Regression, output linear)
        self.model_prioridad = SequentialNeuralNetwork()
        self.model_prioridad.add_layer(DenseLayer(5, 8, 'relu'))
        self.model_prioridad.add_layer(DenseLayer(8, 1, 'linear'))
        self.model_prioridad.fit(X, y_prio, epochs=15)
        self.model_prioridad.save(os.path.join(self.models_dir, "model_prioridad.json"))

        # Demora (Binary Classification, output sigmoid)
        self.model_demora = SequentialNeuralNetwork()
        self.model_demora.add_layer(DenseLayer(5, 8, 'relu'))
        self.model_demora.add_layer(DenseLayer(8, 1, 'sigmoid'))
        self.model_demora.fit(X, y_demora, epochs=15)
        self.model_demora.save(os.path.join(self.models_dir, "model_demora.json"))

        # Anomalía (Binary Classification, output sigmoid)
        self.model_anomalia = SequentialNeuralNetwork()
        self.model_anomalia.add_layer(DenseLayer(5, 8, 'relu'))
        self.model_anomalia.add_layer(DenseLayer(8, 1, 'sigmoid'))
        self.model_anomalia.fit(X, y_anomalia, epochs=15)
        self.model_anomalia.save(os.path.join(self.models_dir, "model_anomalia.json"))

        # Ruta (Multiclass Classification, output softmax)
        self.model_ruta = SequentialNeuralNetwork()
        self.model_ruta.add_layer(DenseLayer(5, 8, 'relu'))
        self.model_ruta.add_layer(DenseLayer(8, 3, 'softmax'))
        self.model_ruta.fit(X, y_ruta, epochs=15)
        self.model_ruta.save(os.path.join(self.models_dir, "model_ruta.json"))
        
        logger.info("🤖 [TensorFlow Engine] Entrenamiento completado y guardado.")

    def cargar_modelos(self):
        try:
            self.model_prioridad = SequentialNeuralNetwork()
            self.model_prioridad.load(os.path.join(self.models_dir, "model_prioridad.json"))

            self.model_demora = SequentialNeuralNetwork()
            self.model_demora.load(os.path.join(self.models_dir, "model_demora.json"))

            self.model_anomalia = SequentialNeuralNetwork()
            self.model_anomalia.load(os.path.join(self.models_dir, "model_anomalia.json"))

            self.model_ruta = SequentialNeuralNetwork()
            self.model_ruta.load(os.path.join(self.models_dir, "model_ruta.json"))
            logger.info("🤖 [TensorFlow Engine] Modelos cargados en memoria exitosamente.")
            return True
        except Exception as e:
            logger.warn(f"No se pudieron cargar los modelos pre-entrenados: {e}. Se requiere entrenamiento.")
            return False

    def predecir(self, carga, antig, critico, doc_cnt, doc_sz):
        # Asegurar carga
        if self.model_prioridad is None:
            if not self.cargar_modelos():
                self.entrenar_modelos_startup()

        # Normalizaciones de inputs de seguridad
        x = [
            max(0.0, min(1.0, float(carga))),
            max(0.0, min(1.0, float(antig))),
            max(0.0, min(1.0, float(critico))),
            max(0.0, min(1.0, float(doc_cnt))),
            max(0.0, min(1.0, float(doc_sz)))
        ]

        # 1. Predicción Prioridad
        prio_score = self.model_prioridad.predict(x)[0]
        prio_score = max(0.0, min(100.0, prio_score))
        
        if prio_score >= 70.0:
            prio_label = "alta"
        elif prio_score >= 40.0:
            prio_label = "media"
        else:
            prio_label = "baja"

        # 2. Predicción Riesgo Demora
        demora_prob = self.model_demora.predict(x)[0]

        # 3. Predicción Anomalía
        anomalia_prob = self.model_anomalia.predict(x)[0]
        anomalia_detectada = bool(anomalia_prob > 0.75)

        # 4. Predicción Ruta Óptima
        ruta_probs = self.model_ruta.predict(x)
        max_idx = ruta_probs.index(max(ruta_probs))
        
        rutas_labels = ["actividad_revision", "actividad_firma", "actividad_rechazo"]
        ruta_optima = rutas_labels[max_idx]

        return {
            "prioridadScore": int(prio_score),
            "prioridadLabel": prio_label,
            "riesgoDemora": float(round(demora_prob, 3)),
            "anomaliaDetectada": anomalia_detectada,
            "anomaliaScore": float(round(anomalia_prob, 3)),
            "rutaOptimaSugerida": ruta_optima
        }
