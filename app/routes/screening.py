import os
import uuid
import json
import re
import sqlite3
from flask import Blueprint, request, jsonify, send_from_directory, render_template, current_app
from werkzeug.utils import secure_filename
from dotenv import load_dotenv
import faiss
import numpy as np
from datetime import datetime
from openai import OpenAI

# Import untuk TF-IDF
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

# Pastikan path import extractor ini sudah sesuai
from extractor import extract_text_from_pdf, chunk_text, embed_chunks, embed_query

# Murni deklarasi Blueprint
screening_bp = Blueprint("screening", __name__)

load_dotenv()

# Konfigurasi OpenRouter
client = OpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=os.environ.get("OPENROUTER_API_KEY"), 
)

# Sesuaikan BASE_DIR agar selaras dengan file struktur di luar folder routes/
BASE_DIR = os.path.abspath(os.path.dirname(__file__))
DB_PATH = os.path.join(BASE_DIR, "..", "..", "storage.db")

BASE = "../../"
UPLOAD_FOLDER = os.path.join(BASE, "uploads")
INDEX_FOLDER = os.path.join(BASE, "indexes")
CHUNKS_FOLDER = os.path.join(BASE, "chunks")

os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(INDEX_FOLDER, exist_ok=True)
os.makedirs(CHUNKS_FOLDER, exist_ok=True)

# Mendukung PDF (Bisa ditambahkan "docx" jika diperlukan)
ALLOWED_EXT = {"pdf"}

# ==========================================
# HELPER SQLITE
# ==========================================
def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
    CREATE TABLE IF NOT EXISTS resumes (
        id TEXT PRIMARY KEY,
        filename TEXT,
        uploaded_at TEXT,
        index_path TEXT,
        chunks_path TEXT
    )
    """)
    c.execute("""
    CREATE TABLE IF NOT EXISTS leaderboard (
        id TEXT PRIMARY KEY,
        job_id TEXT,
        job_description TEXT,
        resume_id TEXT,
        candidate_name TEXT,
        score REAL,
        created_at TEXT
    )
    """)
    conn.commit()
    conn.close()

# Inisialisasi tabel saat blueprint dimuat
init_db()

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXT

@screening_bp.route("/")
def home():
    return render_template("index.html")

def extract_candidate_name(filename):
    base = filename.rsplit(".", 1)[0]
    base = base.replace("_", " ").replace("-", " ").strip()
    return base.title()

# ==========================================
# FUNGSI PENGHITUNG TF-IDF (KEYWORD MATCHING)
# ==========================================
def calculate_tfidf_score(job_desc, cv_text):
    try:
        # Menggunakan stop_words bahasa inggris
        vectorizer = TfidfVectorizer(stop_words='english')
        tfidf_matrix = vectorizer.fit_transform([job_desc, cv_text])
        
        # Menghitung Cosine Similarity dari vektor TF-IDF
        similarity = cosine_similarity(tfidf_matrix[0:1], tfidf_matrix[1:2])[0][0]
        
        # Kembalikan dalam bentuk persentase (0 - 100)
        return round(similarity * 100, 2)
    except Exception as e:
        print("TF-IDF Error:", e)
        return 0.0

# ==========================================
# FUNGSI LLM DENGAN STRUKTUR OUTPUT UNTUK TEST HR
# ==========================================
def generate_verdict_via_llm(cv_text, job_description):
    system_instruction = """
    Anda adalah seorang AI HR Specialist Senior. Tugas Anda adalah menganalisis CV Kandidat terhadap Deskripsi Pekerjaan (Job Description) yang diberikan.
    Anda HARUS memberikan output murni dalam format JSON. Jangan tambahkan teks apapun di luar JSON.

    ### STRUKTUR JSON YANG WAJIB DIGUNAKAN:
    {
        "candidate_info": {
            "name": "Nama Lengkap Kandidat",
            "education": "Pendidikan Terakhir & Jurusan",
            "recent_experience": "Pekerjaan/Pengalaman Terakhir"
        },
        "evaluation": {
            "match_score": 85, // Berikan integer 0-100 seberapa cocok kandidat ini dengan kriteria
            "selection_reason": "Jelaskan dengan detail dan objektif dalam Bahasa Indonesia MENGAPA kandidat ini cocok diwawancarai. (Sebutkan skill/pengalaman yang relevan).",
            "rejection_reason": "Jelaskan kekurangan kandidat ini dibandingkan Job Description. Apa yang mungkin membuatnya tidak lolos? (Jika sangat sempurna, tulis 'Minim kekurangan')."
        },
        "final_recommendation": "HIRE / INTERVIEW / REJECT"
    }

    ### ATURAN:
    - Bersikaplah sangat objektif. Jangan beri nilai tinggi jika skill di CV tidak ada di Job Description.
    - OUTPUT HANYA JSON.
    """

    user_prompt = f"=== JOB DESCRIPTION ===\n{job_description}\n\n=== CANDIDATE RESUME ===\n{cv_text}"

    try:
        response = client.chat.completions.create(
            model="meta-llama/llama-3.1-8b-instruct", 
            messages=[
                {"role": "system", "content": system_instruction},
                {"role": "user", "content": user_prompt}
            ],
            max_tokens=3000,
            temperature=0.1
        )

        content = response.choices[0].message.content.strip()
        
        # Pembersihan output agar murni JSON
        content = re.sub(r'<think>.*?</think>', '', content, flags=re.DOTALL)
        content = content.replace("```json", "").replace("```", "").strip()
        
        json_match = re.search(r'\{.*\}', content, re.DOTALL)
        
        if json_match:
            json_str = json_match.group(0)
            return json.loads(json_str)
        else:
            return {"error": "Format JSON tidak ditemukan pada response LLM", "raw": content}

    except Exception as e:
        print("LLM call failed:", e)
        return {"error": str(e)}

def load_resume_meta(resume_id=None):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    if resume_id:
        c.execute("SELECT id, filename, uploaded_at, index_path, chunks_path FROM resumes WHERE id = ?", (resume_id,))
        row = c.fetchone()
        conn.close()
        if not row:
            return None
        return {
            "id": row[0],
            "filename": row[1],
            "uploaded_at": row[2],
            "index_path": row[3],
            "chunks_path": row[4],
        }
    else:
        # Ambil semua jika resume_id tidak disertakan
        c.execute("SELECT id, filename, uploaded_at, index_path, chunks_path FROM resumes")
        rows = c.fetchall()
        conn.close()
        return [{"id": r[0], "filename": r[1], "uploaded_at": r[2], "index_path": r[3], "chunks_path": r[4]} for r in rows]


# ==========================================
# UPLOAD RESUMES (Mendukung Batch dari Frontend)
# ==========================================
@screening_bp.route("/upload_resumes", methods=["POST"])
def upload_resumes():
    if 'files' not in request.files:
        return jsonify({"error": "files part missing"}), 400
    
    uploaded_files = request.files.getlist('files')
    if not uploaded_files or uploaded_files[0].filename == "":
        return jsonify({"error": "no selected files"}), 400

    chunk_size = int(request.form.get("chunk_size", 800))
    overlap = int(request.form.get("overlap", 100))
    
    results = []
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    # Membaca config dari aplikasi utama (current_app)
    upload_dir = current_app.config.get('UPLOAD_FOLDER', UPLOAD_FOLDER)

    for f in uploaded_files:
        if f.filename == "" or not allowed_file(f.filename):
            continue

        filename = secure_filename(f.filename)
        uid = str(uuid.uuid4())
        saved_path = os.path.join(upload_dir, f"{uid}_{filename}")
        
        try:
            f.save(saved_path)
            
            text = extract_text_from_pdf(saved_path)
            # Membersihkan noise teks sebelum disimpan
            text = re.sub(r'[^\x00-\x7F]+', ' ', text)
            text = re.sub(r'\s+', ' ', text).strip()

            chunks = chunk_text(text, chunk_size=chunk_size, overlap=overlap)
            embeddings = embed_chunks(chunks)
            
            if embeddings.shape[0] == 0:
                continue

            dim = embeddings.shape[1]
            index = faiss.IndexFlatIP(dim)  
            index.add(embeddings)

            index_path = os.path.join(INDEX_FOLDER, f"{uid}.faiss")
            faiss.write_index(index, index_path)

            chunks_path = os.path.join(CHUNKS_FOLDER, f"{uid}.json")
            with open(chunks_path, "w", encoding="utf-8") as fh:
                json.dump(chunks, fh, ensure_ascii=False, indent=2)

            c.execute("INSERT INTO resumes (id, filename, uploaded_at, index_path, chunks_path) VALUES (?, ?, ?, ?, ?)",
                      (uid, filename, datetime.utcnow().isoformat(), index_path, chunks_path))
            
            results.append({"filename": filename, "id": uid, "status": "success"})
            
        except Exception as e:
            results.append({"filename": filename, "status": "error", "message": str(e)})

    conn.commit()
    conn.close()

    return jsonify({
        "message": "Folder processing completed",
        "total_processed": len(results),
        "results": results
    }), 201

# ==========================================
# TAHAP 1 - RANKING MASSAL (FAISS ONLY)
# ==========================================
@screening_bp.route("/rank_candidates", methods=["POST"])
def rank_candidates():
    data = request.get_json(force=True)
    job_id = data.get("job_id") or f"JOB-{str(uuid.uuid4())[:8].upper()}"
    job_description = data.get("job_description", "")
    top_k = int(data.get("top_k", 20)) # Sesuaikan dengan kebutuhan Top 20 Anda

    if not job_description:
        return jsonify({"error": "job_description missing"}), 400

    q_emb = embed_query(job_description)

    all_resumes = load_resume_meta()
    rankings = []

    for row in all_resumes:
        if not os.path.exists(row["index_path"]):
            continue

        index = faiss.read_index(row["index_path"])
        D, _ = index.search(q_emb, k=min(top_k, index.ntotal))
        avg_score = float(np.mean(D[0])) if len(D[0]) > 0 else 0.0

        rankings.append({
            "resume_id": row["id"],
            "candidate_name": extract_candidate_name(row["filename"]),
            "score": avg_score
        })

    rankings = sorted(rankings, key=lambda x: x["score"], reverse=True)

    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("DELETE FROM leaderboard WHERE job_id = ?", (job_id,))
    for rank in rankings:
        lid = str(uuid.uuid4())
        c.execute("""
        INSERT INTO leaderboard (id, job_id, job_description, resume_id, candidate_name, score, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (lid, job_id, job_description, rank["resume_id"], rank["candidate_name"], rank["score"], datetime.utcnow().isoformat()))
        
    conn.commit()
    conn.close()

    return jsonify({
        "job_id": job_id,
        "message": f"Successfully ranked {len(rankings)} candidates using Vector Screening.",
        "rankings": rankings
    })

# ==========================================
# TAHAP 2 - AI VERDICT + TF-IDF SCORING
# ==========================================
@screening_bp.route("/match_resume", methods=["POST"])
def match_resume():
    data = request.get_json(force=True)
    resume_id = data.get("resume_id")
    job_description = data.get("job_description", "")

    meta = load_resume_meta(resume_id)
    if not meta:
        return jsonify({"error": "resume_id not found"}), 404

    if not os.path.exists(meta["chunks_path"]):
        return jsonify({"error": "chunks not found on disk"}), 500

    # Ambil SEMUA pecahan teks CV agar tidak ada yang terpotong
    with open(meta["chunks_path"], "r", encoding="utf-8") as fh:
        chunks = json.load(fh)

    if not job_description:
        return jsonify({"error": "job_description missing"}), 400

    # Gabungkan semua chunk menjadi teks penuh
    full_cv_text = "\n\n".join(chunks)

    # 1. HITUNG SKOR TF-IDF (KEYWORD MATCH) SEBELUM LLM
    tfidf_score = calculate_tfidf_score(job_description, full_cv_text)

    # 2. KIRIM FULL TEXT KE LLM UNTUK REASONING MENDALAM
    llm_result = generate_verdict_via_llm(full_cv_text, job_description)
    verdict = {"method": "llm", "result": llm_result}

    # 3. KEMBALIKAN SEMUA SKOR KE FRONTEND
    return jsonify({
        "resume_id": resume_id,
        "filename": meta["filename"],
        "candidate_name": extract_candidate_name(meta["filename"]),
        "tfidf_score": tfidf_score,
        "verdict": verdict
    })


@screening_bp.route("/resumes", methods=["GET"])
def list_resumes():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT id, filename, uploaded_at FROM resumes ORDER BY uploaded_at DESC")
    rows = c.fetchall()
    conn.close()
    items = [{"id":r[0],"filename":r[1],"uploaded_at":r[2]} for r in rows]
    return jsonify(items)

@screening_bp.route("/download/<resume_id>", methods=["GET"])
def download_resume(resume_id):
    meta = load_resume_meta(resume_id)
    if not meta:
        return jsonify({"error":"not found"}), 404

    upload_dir = current_app.config.get('UPLOAD_FOLDER', UPLOAD_FOLDER)
    for fname in os.listdir(upload_dir):
        if fname.startswith(resume_id + "_"):
            return send_from_directory(upload_dir, fname, as_attachment=True)
    return jsonify({"error":"file missing"}), 404

@screening_bp.route("/leaderboard/<job_id>", methods=["GET"])
def leaderboard(job_id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
    SELECT resume_id, candidate_name, score, created_at
    FROM leaderboard
    WHERE job_id = ?
    ORDER BY score DESC
    """, (job_id,))
    rows = c.fetchall()
    conn.close()

    items = [{
        "resume_id": r[0],
        "candidate_name": r[1],
        "score": r[2],
        "created_at": r[3]
    } for r in rows]

    return jsonify(items)