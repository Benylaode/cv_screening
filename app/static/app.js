// ==========================================
// 1. UPLOAD FILES (Single atau Folder)
// ==========================================
async function uploadSelectedFiles() {
    const fileInputFiles = document.getElementById('resumeFilesOnly');
    const folderInput = document.getElementById('resumeFolder');
    const statusBox = document.getElementById('uploadStatus');
    
    let selectedFiles = [];
    if (folderInput.files.length > 0) {
        selectedFiles = folderInput.files;
    } else if (fileInputFiles.files.length > 0) {
        selectedFiles = fileInputFiles.files;
    }

    if (selectedFiles.length === 0) {
        statusBox.innerText = "Please select a file or a folder first.";
        return;
    }

    const formData = new FormData();
    for (let i = 0; i < selectedFiles.length; i++) {
        formData.append("files", selectedFiles[i]);
    }

    try {
        statusBox.innerText = `Uploading ${selectedFiles.length} file(s)... Please wait.`;
        
        const response = await fetch('/screening/upload_resumes', { 
            method: 'POST',
            body: formData
        });
        
        const result = await response.json();
        statusBox.innerText = JSON.stringify(result, null, 2);
        
        if (response.ok) {
            fileInputFiles.value = "";
            folderInput.value = "";
            loadResumes(); 
        }
    } catch (error) {
        statusBox.innerText = "Error: " + error.message;
    }
}

// ==========================================
// 2. TAMPILKAN DAFTAR SEMUA RESUME
// ==========================================
async function loadResumes() {
    let res = await fetch("/screening/resumes");
    let data = await res.json();

    let list = document.getElementById("resumeList");
    list.innerHTML = "";
    data.forEach(r => {
        let li = document.createElement("li");
        li.innerText = `${r.id} — ${r.filename} (${r.uploaded_at})`;
        list.appendChild(li);
    });
}

// ==========================================
// 3. TAHAP 1: RANKING MASSAL (FAISS SCREENING)
// ==========================================
async function rankCandidates() {
    let jobId = document.getElementById("jobId").value;
    let jobDesc = document.getElementById("jobDesc").value;
    let leaderboardBox = document.getElementById("leaderboardBox");

    if (!jobDesc) {
        alert("Job Description tidak boleh kosong!");
        return;
    }

    leaderboardBox.innerText = "⏳ Memproses ranking semua kandidat...\nPlease wait...";

    let body = {
        job_id: jobId,
        job_description: jobDesc
    };

    try {
        let res = await fetch("/screening/rank_candidates", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(body)
        });

        let data = await res.json();
        
        if (res.ok) {
            // Isi otomatis Job ID jika sebelumnya dikosongkan (auto-generated dari server)
            document.getElementById("jobId").value = data.job_id;
            loadLeaderboard(); // Langsung tampilkan hasilnya
        } else {
            leaderboardBox.innerText = "❌ Error: " + data.error;
        }
    } catch (err) {
        leaderboardBox.innerText = "❌ Error: " + err;
    }
}

// ==========================================
// 4. TAMPILKAN LEADERBOARD (Berdasarkan Job ID)
// ==========================================
async function loadLeaderboard() {
    let jobId = document.getElementById("jobId").value;
    let box = document.getElementById("leaderboardBox");

    if (!jobId) {
        box.innerText = "⚠️ Masukkan Job ID terlebih dahulu untuk melihat leaderboard.";
        return;
    }

    box.innerText = "⏳ Loading leaderboard...";

    try {
        let res = await fetch(`/screening/leaderboard/${jobId}`);
        let data = await res.json();
        
        if (data.length === 0) {
            box.innerText = "Belum ada kandidat yang dirangking untuk Job ID ini.";
            return;
        }

        let output = `🏆 Leaderboard Pekerjaan: ${jobId}\n\n`;
        data.forEach((rank, index) => {
            let scorePercent = Math.round(rank.score * 100); 
            output += `#${index + 1} | Kecocokan FAISS: ${scorePercent}% | Nama: ${rank.candidate_name}\n`;
            output += `    Resume ID: ${rank.resume_id}\n\n`;
        });

        box.innerText = output;
    } catch (err) {
        box.innerText = "❌ Error: " + err;
    }
}

// ==========================================
// 5. TAHAP 2: DEEP MATCHING UNTUK TOP 20 KANDIDAT
// ==========================================
async function matchTopCandidates() {
    // Ambil Job ID dari input Tahap 2, jika kosong ambil dari input Tahap 1
    let jobId = document.getElementById("tahap2JobId").value || document.getElementById("jobId").value;
    let jobDesc = document.getElementById("jobDesc").value;
    let resultBox = document.getElementById("result-box");

    if (!jobId || !jobDesc) {
        alert("Job ID dan Job Description tidak boleh kosong!");
        return;
    }

    resultBox.innerText = "⏳ Memuat data dari Leaderboard...\n";

    try {
        // A. Ambil daftar peringkat
        let resLeaderboard = await fetch(`/screening/leaderboard/${jobId}`);
        let leaderboard = await resLeaderboard.json();

        if (leaderboard.length === 0) {
            resultBox.innerText = "❌ Tidak ada kandidat di leaderboard. Harap jalankan Tahap 1 terlebih dahulu.";
            return;
        }

        // B. Batasi hanya 20 kandidat teratas
        let topCandidates = leaderboard.slice(0, 5);
        resultBox.innerText = `✅ Ditemukan ${topCandidates.length} kandidat teratas. Memulai analisis DeepSeek AI...\n\n`;

        // C. Looping pemanggilan LLM satu per satu
        for (let i = 0; i < topCandidates.length; i++) {
            let cand = topCandidates[i];
            
            // Tampilkan progres
            let progressText = `🔄 [${i + 1}/${topCandidates.length}] AI sedang membaca CV: ${cand.candidate_name}...\n`;
            resultBox.innerText += progressText;
            resultBox.scrollTop = resultBox.scrollHeight;

            let body = {
                resume_id: cand.resume_id,
                job_description: jobDesc
            };

            // Panggil API Python
            let resMatch = await fetch("/screening/match_resume", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify(body)
            });

            let matchData = await resMatch.json();

            // Hapus tulisan progres "sedang membaca..."
            resultBox.innerText = resultBox.innerText.replace(progressText, "");

            // D. Cetak hasil
            if (matchData.verdict && matchData.verdict.result) {
                let formatResult = typeof matchData.verdict.result === 'object' 
                    ? JSON.stringify(matchData.verdict.result, null, 2) 
                    : matchData.verdict.result;
                
                let scorePercent = Math.round(cand.score * 100);
                let output = `====================================\n`;
                output += `🏆 Rank #${i + 1} - ${cand.candidate_name}\n`;
                output += `Skor FAISS: ${scorePercent}% | Resume ID: ${cand.resume_id}\n`;
                output += `====================================\n`;
                output += `${formatResult}\n\n`;

                resultBox.innerText += output;
            } else {
                resultBox.innerText += `❌ Gagal mendapatkan analisis untuk ${cand.candidate_name}.\n\n`;
            }
            
            // Auto-scroll ke bawah agar progres selalu terlihat
            resultBox.scrollTop = resultBox.scrollHeight;
        }
        
        resultBox.innerText += `\n🎉 PROSES SELESAI! Seluruh ${topCandidates.length} kandidat teratas telah dianalisis.`;

    } catch (err) {
        resultBox.innerText += "\n❌ Error: " + err;
    }
}

// ==========================================
// 6. EKSTRAK NAMA (Fungsi Tambahan)
// ==========================================
async function extractName() {
    let id = document.getElementById("extractResumeId").value;
    let box = document.getElementById("extractResult");

    if (!id) {
        box.innerText = "⚠️ Masukkan Resume ID.";
        return;
    }

    box.innerText = "⏳ Extracting name...";
    try {
        let res = await fetch(`/screening/extract_name/${id}`);
        let data = await res.json();
        box.innerText = JSON.stringify(data, null, 2);
    } catch (err) {
        box.innerText = "❌ Error: " + err;
    }
}