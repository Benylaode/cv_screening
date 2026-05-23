# extractor.py
import io
import os
import numpy as np
from PIL import Image
import fitz  # pymupdf
import easyocr
from sentence_transformers import SentenceTransformer

reader = easyocr.Reader(['id', 'en'], gpu=False)
embed_model = SentenceTransformer("all-MiniLM-L6-v2")


def extract_text_from_pdf(pdf_path):
    """
    Ekstrak teks dari PDF.
    Jika halaman tidak memiliki teks, lakukan OCR.
    """
    if not os.path.exists(pdf_path):
        raise FileNotFoundError(f"File tidak ditemukan: {pdf_path}")

    text = ""

    with fitz.open(pdf_path) as doc:
        for page_num, page in enumerate(doc, start=1):

            # Ekstraksi teks langsung
            page_text = page.get_text("text").strip()

            if page_text:
                text += f"\n--- Halaman {page_num} ---\n{page_text}"
            else:
                # OCR fallback
                try:
                    pix = page.get_pixmap(alpha=False)  # hindari RGBA error
                    img_bytes = pix.tobytes("png")
                    img = Image.open(io.BytesIO(img_bytes))

                    img_np = np.array(img)
                    ocr_result = reader.readtext(img_np, detail=0)

                    ocr_text = "\n".join(ocr_result)

                except Exception as e:
                    ocr_text = f"[Gagal OCR halaman {page_num}: {e}]"

                text += f"\n--- Halaman {page_num} (OCR) ---\n{ocr_text}"

    return text.strip()


def chunk_text(text, chunk_size=500, overlap=50):
    """
    Membagi teks menjadi potongan kecil untuk RAG.
    """
    if not text or len(text.strip()) == 0:
        return []

    chunks = []
    L = len(text)
    start = 0

    while start < L:
        end = start + chunk_size
        chunk = text[start:end].strip()

        if chunk:
            chunks.append(chunk)

        start += chunk_size - overlap

    return chunks

def embed_chunks(chunks):
    """
    Embedding untuk list of chunks.
    Mengembalikan numpy array shape (n_chunks, dim).
    """
    if not chunks:
        return np.zeros((0, embed_model.get_sentence_embedding_dimension()), dtype="float32")

    embeddings = embed_model.encode(
        chunks,
        convert_to_numpy=True,
        show_progress_bar=False,
        normalize_embeddings=True  # NORMALIZASI OTOMATIS — LEBIH AMAN
    )

    return embeddings.astype("float32")

def embed_query(text):
    """
    Embedding untuk query pencarian FAISS.
    """
    emb = embed_model.encode(
        [text],
        convert_to_numpy=True,
        normalize_embeddings=True  # normalisasi otomatis
    )

    return emb.astype("float32")
