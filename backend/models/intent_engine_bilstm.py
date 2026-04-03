import numpy as np
import tensorflow as tf
import pandas as pd
import os
import pickle
import json
import gdown

# -------- Configuration --------
MODEL_PATH = "backend/models/intent_model_bilstm.keras"
MODEL_URL = "https://drive.google.com/uc?id=1-OTfF6LfoUxegxF3I_SLU7YsQFz0dybs"

def download_model():
    if not os.path.exists(MODEL_PATH):
        try:
            print("Downloading model from Google Drive using gdown...")
            os.makedirs(os.path.dirname(MODEL_PATH), exist_ok=True)
            gdown.download(MODEL_URL, MODEL_PATH, quiet=False)
            print("Model downloaded successfully.")
        except Exception as e:
            print(f"Model download failed: {e}")
vocab_size = 20000
max_len = 30
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(os.path.dirname(BASE_DIR))


def _resolve_path(*candidates):
    """Return first existing path from candidate relative paths."""
    for rel in candidates:
        path = os.path.join(PROJECT_ROOT, rel)
        if os.path.exists(path):
            return path
    return os.path.join(PROJECT_ROOT, candidates[0])

# -------- Load vectorizer from saved vocab --------
vectorizer = None
model = None
classes = None

def _load_vectorizer():
    """Load or recreate the text vectorizer."""
    global vectorizer
    
    # Try to load saved vocabulary
    vocab_path = _resolve_path("backend/models/vectorizer_vocab.pkl", "vectorizer_vocab.pkl")
    config_path = _resolve_path("backend/models/vectorizer_config.json", "vectorizer_config.json")
    
    if os.path.exists(vocab_path) and os.path.exists(config_path):
        try:
            with open(vocab_path, 'rb') as f:
                vocab = pickle.load(f)
            
            with open(config_path, 'r') as f:
                config = json.load(f)
            
            vectorizer = tf.keras.layers.TextVectorization(
                max_tokens=config.get('max_tokens', vocab_size),
                output_sequence_length=config.get('output_sequence_length', max_len),
                output_mode='int',
                vocabulary=vocab
            )
            return
        except Exception as e:
            print(f"Warning: Could not load saved vocab: {e}")
    
    # Fallback: try to load from training data
    train_data_path = _resolve_path("dataset/train_balanced.csv")
    if os.path.exists(train_data_path):
        try:
            train_df = pd.read_csv(train_data_path)
            train_texts = train_df["text"].astype(str).tolist()
            
            vectorizer = tf.keras.layers.TextVectorization(
                max_tokens=vocab_size,
                output_sequence_length=max_len,
                output_mode='int'
            )
            
            text_ds = tf.data.Dataset.from_tensor_slices(train_texts).batch(128)
            vectorizer.adapt(text_ds)
            return
        except Exception as e:
            print(f"Warning: Could not load training data: {e}")
    
    # Last resort: create with empty vocab (will be updated on first use)
    vectorizer = tf.keras.layers.TextVectorization(
        max_tokens=vocab_size,
        output_sequence_length=max_len,
        output_mode='int'
    )
    print("Warning: Using uninitialized vectorizer. Predictions may be inaccurate.")

def _load_model():
    """Load the trained model."""
    global model, classes
    
    download_model()
    
    model_path = MODEL_PATH
    print(f"Loading model from: {model_path}")
    if os.path.exists(model_path):
        try:
            model = tf.keras.models.load_model(model_path)
            print("Model loaded successfully.")
        except Exception as e:
            print(f"Error: Could not load model: {e}")
            model = None
    else:
        print("Error: Model file not found: intent_model_bilstm.keras")
        model = None
    
    classes_path = _resolve_path("backend/models/label_classes_bilstm.npy", "label_classes_bilstm.npy")
    if os.path.exists(classes_path):
        try:
            classes = np.load(classes_path, allow_pickle=True)
        except Exception as e:
            print(f"Error: Could not load classes: {e}")
            classes = None
    else:
        print("Error: Classes file not found: label_classes_bilstm.npy")
        classes = None

# Initialize on module load
_load_vectorizer()
_load_model()

# -------- Prediction --------
def predict_intent(text):
    """Predict intent from text."""
    if vectorizer is None or model is None or classes is None:
        return "normal", 0.5  # Safe fallback
    
    try:
        vec = vectorizer(np.array([text]))
        pred = model.predict(vec, verbose=0)
        intent = classes[np.argmax(pred)]
        confidence = float(np.max(pred))
        return intent, confidence
    except Exception as e:
        print(f"Warning: Prediction failed: {e}")
        return "normal", 0.5  # Safe fallback
