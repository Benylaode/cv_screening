# AI-Powered CV Screening System

Sistem otomatisasi rekrutmen cerdas berbasis Artificial Intelligence untuk mengekstraksi informasi dan menganalisis CV pelamar secara mendalam. Proyek ini memadukan kekuatan pemrosesan dokumen lokal dengan kecerdasan model bahasa besar via OpenRouter API.

---

## 🚀 Fitur & Alur Penggunaan

### Penggunaan Saat Ini

1. **Penerimaan Dokumen (Upload):** Recruiter mengunggah berkas CV pelamar dalam format PDF atau DOCX melalui antarmuka web.
2. **Ekstraksi Otomatis:** Sistem membaca berkas untuk memisahkan informasi profil, keahlian (*skills*), dan riwayat pekerjaan.
3. **Penilaian AI (Skoring):** Menilai kecocokan kandidat secara objektif dengan membandingkan teks CV terhadap deskripsi pekerjaan (*job description*) menggunakan AI.

### Visi & Pengembangan Masa Depan

* **Integrasi HRIS:** Sinkronisasi data kandidat yang lolos *screening* ke platform manajemen HR perusahaan.
* **Analitik Dashboard:** Visualisasi tren keahlian pelamar dan distribusi skor rekrutmen.
* **Notifikasi Otomatis:** Pengiriman email tindak lanjut atau undangan wawancara berdasarkan ambang batas skor (*threshold*).

---

## 🛠️ Dependensi & Stack Teknologi

Aplikasi ini dibangun menggunakan arsitektur yang ringan namun optimal untuk pemrosesan AI, dan mendukung kompabilitas secara penuh pada lingkungan berbasis Apple Silicon (ARM64) maupun arsitektur x86:

* **Backend Framework:** `Python 3.x` dengan `Flask` — Menangani *routing* API, manajemen sesi, dan proses unggahan file.
* **AI Inference Gateway:** `OpenRouter API` — Menghubungkan aplikasi dengan LLM mutakhir untuk analisis semantik dan penalaran kontekstual.
* **Document Parser:** `PyPDF2` — Melakukan ekstraksi teks mentah (*raw text*) dari berkas PDF kandidat.
* **Database Terminus:** `SQLite` (`storage.db`) — Penyimpanan relasional lokal untuk mencatat data kandidat beserta skor hasil *screening*.
* **Deployment:** `Docker` — Membungkus aplikasi ke dalam kontainer untuk konsistensi *environment*.

---

## ⚙️ Logika Arsitektur & Alur Berjalannya Aplikasi

Aplikasi berjalan secara sekuensial melalui empat tahapan utama:

[ Upload CV (PDF) ] ──> ( extractor.py ) ──> [ Kirim Teks ke OpenRouter ] ──> [ Simpan storage.db & Tampil ]

1. **Ingestion (`run.py` / Routes):**
File PDF dikirimkan melalui formulir web. Aplikasi memvalidasi tipe file dan menyimpannya sementara di direktori server.
2. **Parsing (`extractor.py`):**
Modul ekstraktor membaca file PDF baris demi baris menggunakan `PyPDF2`. Teks dibersihkan dari karakter *corrupt* untuk menghasilkan string teks mentah.
3. **Reasoning (OpenRouter Service):**
Teks mentah dibungkus ke dalam *structured prompt* bersama dengan kriteria posisi yang dicari. Data ini dikirim ke **OpenRouter API**. Model AI melakukan penalaran semantik untuk mencocokkan kualifikasi pelamar dan mengembalikan *output* terstruktur (JSON).
4. **Finalize (Database & Dashboard):**
Respon JSON dari OpenRouter diurai (Nama, Email, Keahlian Utama, Skor), lalu dimasukkan ke dalam tabel database `storage.db`. Data terbaru dimuat ulang pada antarmuka *dashboard* secara *real-time*.

---

## 📂 Struktur Direktori

```text
cv-screening-ai/
│
├── app/
│   ├── __init__.py
│   ├── routes/
│   │   └── screening.py      # Endpoint untuk upload & proses
│   ├── services/
│   │   ├── extractor.py      # Logika PyPDF2
│   │   └── ai_engine.py      # Integrasi OpenRouter API
│   ├── models/
│   │   └── database.py       # Interaksi SQLite
│   └── templates/
│       └── index.html        # Antarmuka web
│
├── storage.db                # Database SQLite lokal
├── requirements.txt          # Dependensi Python
├── Dockerfile                # Konfigurasi Docker
├── .env.example              # Contoh environment variables
└── run.py                    # Entry point aplikasi

```

---

## 💻 Panduan Instalasi Lokal

### 1. Kloning Repositori

```bash
git clone https://github.com/username/cv-screening-ai.git
cd cv-screening-ai

```

### 2. Siapkan Virtual Environment & Dependensi

```bash
python3 -m venv venv
source venv/bin/activate  # Untuk macOS / Linux
# venv\Scripts\activate   # Untuk Windows

pip install --upgrade pip
pip install -r requirements.txt

```

### 3. Pengaturan Environment Variables

Salin file konfigurasi dan sesuaikan isinya:

```bash
cp .env.example .env

```

Isi `.env` dengan kredensial berikut:

```env
OPENROUTER_API_KEY=isi_dengan_api_key_openrouter_anda
FLASK_APP=run.py
FLASK_ENV=development

```

### 4. Inisialisasi Database

```bash
python -c "from app.models.database import init_db; init_db()"

```

### 5. Menjalankan Aplikasi

```bash
flask run

```

Akses aplikasi melalui `http://localhost:5000`.
