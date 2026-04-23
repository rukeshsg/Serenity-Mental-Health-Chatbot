<p align="center">
  <img src="./assets/logo_128.png" width="80"/>
</p>

<h1 align="center">Serenity – AI Mental Health Chatbot</h1>

<p align="center">

![Python](https://img.shields.io/badge/Python-3.10+-6C63FF?style=for-the-badge&logo=python&logoColor=white)
![Flask](https://img.shields.io/badge/Flask-Backend-1E1E2F?style=for-the-badge&logo=flask&logoColor=white)
![React](https://img.shields.io/badge/React-Frontend-8A7CFF?style=for-the-badge&logo=react&logoColor=white)
![ML](https://img.shields.io/badge/ML-BiLSTM-7F5AF0?style=for-the-badge)
![RAG](https://img.shields.io/badge/RAG-FAISS-9B5DE5?style=for-the-badge)
![Database](https://img.shields.io/badge/Database-SQLite-5A4FCF?style=for-the-badge)
![Deploy](https://img.shields.io/badge/Deploy-Render-6C63FF?style=for-the-badge)
![Status](https://img.shields.io/badge/Status-Production%20Ready-2CB67D?style=for-the-badge)
![License](https://img.shields.io/badge/License-Apache%202.0-4F46E5?style=for-the-badge)

</p>

## 🌐 Live Demo
https://serenity-ai-2yt3.onrender.com


---


## ✨ Features
- **Intelligent Chatbot Engine:** Context-aware conversations with emotional memory, tracking continuity and emotional trajectory over multiple turns.
- **Advanced Intent Detection:** Machine learning-based intent classification utilizing a custom BiLSTM model (with keyword fallback) to identify real underlying distress levels (e.g., anxiety, depression, stress, sadness).
- **Hybrid RAG Knowledge Retrieval:** Combines semantic search (FAISS + Sentence Transformers) with keyword search (BM25) to retrieve medically sound coping strategies and responses.
- **Multi-Stage Crisis Management:** Specialized crisis module detecting high-risk situations such as self-harm, abuse, or third-person emergencies. Features built-in cooldowns, crisis cards, and staged resource escalation.
- **Emergency Alert System:** Automated emergency SMS notifications (via Twilio) alerting designated contacts if crisis or safety thresholds are triggered.
- **Safety & Moderation Module:** Input sanitizer and abuse/harassment detection to protect the system and the user, generating safe fallback replies for uncertain inputs.
- **Secure Authentication & Onboarding:** Passwordless Email OTP login combined with a secure 4-6 digit PIN for private session data access.
- **Analytics & Feedback Monitoring:** Continuous tracking of conversation quality, circuit-breaker mechanisms for LLM limits, and UI dashboard visualization.


---

## 📸 Screenshots

### 🏠 Home

<p align="center">
  <img src="./assets/home1.png" width="48%"/>
  <img src="./assets/home.png" width="48%"/>
</p>

### 📊 Analytics Dashboard

<p align="center">
  <img src="./assets/dashboard1.png" width="48%"/>
  <img src="./assets/dashboard.png" width="48%"/>
</p>

### 💬 Chat Interface

<p align="center">
  <img src="./assets/chat.png" width="800"/>
</p>


### ⚙️ Settings

<p align="center">
  <img src="./assets/settings.png" width="800"/>
</p>

### 🚨 Crisis Support

<p align="center">
  <img src="./assets/crisis.png" width="800"/>
</p>

---

## 🧠 System Architecture
The application follows a robust, privacy-first data pipeline built for safe interactions:
1. **User Input & Sanitization:** Message is received via React frontend and passes through the backend input sanitizer.
2. **Intent & Crisis Analysis:** The `llm_analyzer` and `BiLSTM Intent Engine` classify the emotional state. `Crisis Module` immediately checks for high-risk signals (self-harm, abuse).
3. **Emergency Routing:** If a severe crisis is detected, the `notification_service` dispatches an SMS to emergency contacts, and the bot halts normal flow to present crisis intervention resources.
4. **Context & RAG Retrieval:** For normal distress, the context manager builds an emotional memory state. The `Hybrid RAG Engine` uses FAISS and BM25 to pull relevant therapeutic knowledge.
5. **LLM Generation & Safety:** The `LLM Circuit Breaker` queries Google Gemini to generate an empathetic response incorporating the RAG context. The `Safety Module` validates the response before delivery.
6. **Delivery & UI State:** The backend calculates the proper `ui_state` (e.g., `abuse_card`, `normal_chat`) and sends the final response to the user.


---


## 🛠️ Tech Stack 


### Frontend
- **React 18** (UI components and state management)
- **Vite** (Build tool and dev server)
- **Recharts** (Analytics and dashboard visualization)
- **Axios** (API communication)


### Backend
- **Python 3.10+** (Core language)
- **Flask & Flask-CORS** (REST API framework)
- **Werkzeug & Waitress** (WSGI serving and routing)


### Machine Learning & NLP
- **TensorFlow / Keras** (BiLSTM Intent Engine)
- **PyTorch** (Deep learning backend for embeddings)
- **Transformers & Sentence-Transformers** (`all-MiniLM-L6-v2` for embeddings)
- **Scikit-Learn & NumPy** (Data processing and thresholding)
- **Google Generative AI / Gemini API** (LLM conversational responses)


### Database
- **SQLite3** (`mental_health.db` for conversations, users, and session logs)
- **FAISS (faiss-cpu)** (Vector database for semantic similarity)


### APIs & Integrations
- **Twilio API** (Emergency SMS routing)
- **SMTP/Email Service** (OTP authentication)
- **BM25Okapi** (Lexical search integration)


### Tools
- **Python-dotenv** (Environment variable management)
- **Rich & Colorama** (Advanced console logging)


---


## ⚙️ Installation & Setup


### Prerequisites
- Node.js (v18+)
- Python (3.9 - 3.11)
- API Keys: Twilio, Google Gemini, and SMTP credentials.


### Backend Setup
1. Navigate to the project root and create a virtual environment:
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```
2. Install the backend dependencies:
   ```bash
   pip install -r requirements.txt
   ```
3. Set up your `.env` file based on `.env.example`:
   ```env
   SERENITY_DEBUG=True
   SERENITY_LOG_LEVEL=INFO
   GEMINI_API_KEY=your_google_genai_key
   TWILIO_ACCOUNT_SID=your_twilio_sid
   TWILIO_AUTH_TOKEN=your_twilio_token
   TWILIO_PHONE_NUMBER=your_twilio_phone
   SMTP_EMAIL=your_email@example.com
   SMTP_PASSWORD=your_email_password
   ```
4. Run the backend server:
   ```bash
   python backend/run_backend.py
   # Or use the provided batch file on Windows
   run_advancechatbot.bat
   ```


### Frontend Setup
1. Navigate to the `ui` directory:
   ```bash
   cd ui
   ```
2. Install Node dependencies:
   ```bash
   npm install
   ```
3. Start the Vite development server:
   ```bash
   npm run dev
   ```


---


## 📊 Features Breakdown


- **Intent Engine:** Uses a BiLSTM neural network trained on emotional datasets to categorize user text into distinct intents (anxiety, depression, anger, etc.). It acts as the brain guiding the response style.
- **Crisis Module:** A rigid, deterministic rule engine that bypasses AI generation to provide immediate, medically reviewed helpline resources when self-harm or abuse triggers are met.
- **Safety Module:** Filters both user inputs and LLM outputs to prevent adversarial attacks, explicit content, and hallucinated medical advice.
- **RAG Engine:** A hybrid search implementation retrieving data from `mental_health_knowledge.txt`. It normalizes FAISS dense embeddings and BM25 sparse lexical scores to find the most accurate therapeutic context.
- **Response Generator:** Connects to Gemini, injecting RAG context, emotional memory (e.g., "You mentioned feeling sad earlier..."), and conversational constraints to output highly empathetic text.
- **Logger / Analytics:** Tracks anonymized conversation trajectories, cache hit rates, circuit breaker health, and overall quality scores to populate the frontend dashboard via Recharts.


---


## 🚀 Usage
1. **Onboarding:** A user enters their email and receives an OTP. New users are prompted to set up a 4-6 digit PIN and assign an emergency contact.
2. **Chatting:** The user types their feelings into the chat interface. The system analyzes the text in real-time.
3. **Intervention:** If a user expresses severe distress, the UI state shifts to display a "Crisis Card" or "Safety Card" with immediate helpline buttons.
4. **Emergency Escalation:** If the user hits the crisis threshold (e.g., 2+ high-risk messages in 24 hours), the system silently dispatches an SMS to their emergency contact to check in on them.
5. **Private Stats:** The user can unlock their historical analytics and emotional trajectory by verifying their secure PIN in the dashboard.


---


## 📌 Status
🔄 Continuous improvements planned: Expanding offline LLM capabilities, refining the BiLSTM intent model, and enhancing UI accessibility features.


---


## 📄 License
This project is licensed under the Apache License 2.0.


---


## ⚠️ Disclaimer
This chatbot is intended for educational purposes only and is not a substitute for professional mental health care, diagnosis, or treatment. If you are experiencing serious distress, please seek help from a qualified professional or a local support service.
