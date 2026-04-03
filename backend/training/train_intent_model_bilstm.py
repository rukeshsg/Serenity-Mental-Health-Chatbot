import pandas as pd
import numpy as np
import tensorflow as tf
import json, pickle, re

from sklearn.preprocessing import LabelEncoder
from sklearn.metrics import classification_report


# -------------------- Load Data --------------------
import os

# Get the dataset directory (project root)
script_dir = os.path.dirname(os.path.abspath(__file__))
# Go up two levels: from backend/training to project root
project_dir = os.path.dirname(os.path.dirname(script_dir))
dataset_dir = os.path.join(project_dir, "dataset")

print(f"📂 Loading datasets from: {dataset_dir}")

train_df = pd.read_csv(os.path.join(dataset_dir, "train_balanced.csv"))
val_df   = pd.read_csv(os.path.join(dataset_dir, "val.csv"))
test_df  = pd.read_csv(os.path.join(dataset_dir, "test.csv"))


def clean_text(t):
    return re.sub(r'[^\x00-\x7F]+', '', str(t))


train_texts = [clean_text(t) for t in train_df["text"]]
val_texts   = [clean_text(t) for t in val_df["text"]]
test_texts  = [clean_text(t) for t in test_df["text"]]

train_labels = train_df["intent"].astype(str).str.strip().str.lower().tolist()
val_labels   = val_df["intent"].astype(str).str.strip().str.lower().tolist()
test_labels  = test_df["intent"].astype(str).str.strip().str.lower().tolist()


# -------------------- Encode Labels --------------------
le = LabelEncoder()
le.fit(train_labels)

y_train = le.transform(train_labels)
y_val   = le.transform(val_labels)
y_test  = le.transform(test_labels)

# Label classes saved at the end with other files


# -------------------- Text Vectorization --------------------
vocab_size = 20000
max_len = 30   # ✅ important (was 40)

vectorizer = tf.keras.layers.TextVectorization(
    max_tokens=vocab_size,
    output_sequence_length=max_len,
    output_mode='int'
)

print("🔹 Adapting text vectorizer on TRAIN only...")
text_ds = tf.data.Dataset.from_tensor_slices(train_texts).batch(128)
vectorizer.adapt(text_ds)

X_train = vectorizer(np.array(train_texts))
X_val   = vectorizer(np.array(val_texts))
X_test  = vectorizer(np.array(test_texts))


# -------------------- Correct BiLSTM Model --------------------
model = tf.keras.Sequential([
    tf.keras.layers.Embedding(vocab_size, 128),

    tf.keras.layers.Bidirectional(tf.keras.layers.LSTM(64)),

    tf.keras.layers.Dense(128, activation='relu'),
    tf.keras.layers.Dropout(0.5),

    tf.keras.layers.Dense(len(le.classes_), activation='softmax')
])

model.compile(
    optimizer=tf.keras.optimizers.Adam(0.0005),  # ✅ important
    loss='sparse_categorical_crossentropy',
    metrics=['accuracy']
)

model.build(input_shape=(None, max_len))
model.summary()


# -------------------- Train --------------------
early_stop = tf.keras.callbacks.EarlyStopping(
    monitor='val_loss',
    patience=3,
    restore_best_weights=True
)

print("🚀 Training BiLSTM model...")
model.fit(
    X_train, y_train,
    epochs=15,
    batch_size=128,
    validation_data=(X_val, y_val),
    callbacks=[early_stop]
)


# -------------------- Final Evaluation on TEST --------------------
print("\n📊 Evaluating on TEST set...")
y_pred = np.argmax(model.predict(X_test), axis=1)
print(classification_report(y_test, y_pred, target_names=le.classes_))


# -------------------- Save Model --------------------
# Save to project root
model.save(os.path.join(project_dir, "intent_model_bilstm.keras"))

with open(os.path.join(project_dir, "vectorizer_config.json"), "w", encoding="utf-8") as f:
    json.dump(vectorizer.get_config(), f, ensure_ascii=False)

with open(os.path.join(project_dir, "vectorizer_vocab.pkl"), "wb") as f:
    pickle.dump(vectorizer.get_vocabulary(), f)

# Save label classes to project root
np.save(os.path.join(project_dir, "label_classes_bilstm.npy"), le.classes_)

print(f"✅ Model and vectorizer saved to: {project_dir}")
