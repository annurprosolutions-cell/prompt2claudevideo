# Sistem Permohonan Bantuan

Aliran kerja permohonan bantuan untuk agensi kerajaan:
**Pemohon → Pegawai Penyemak → Pegawai Pelulus**, dengan nombor rujukan, SLA,
pemberitahuan, versi dokumen dan jejak audit.

- **Frontend**: HTML/CSS/JS biasa, tiada build step — dihoskan percuma di GitHub Pages.
- **Backend + pangkalan data**: Google Sheets melalui Google Apps Script Web App.
- **Storan dokumen**: Google Drive (folder yang dicipta automatik).
- **Kos**: RM 0. Semuanya dalam kuota percuma Google dan GitHub.

---

## Bahagian 1 — Pasang backend (Google Sheets + Apps Script)

1. Buka [sheets.new](https://sheets.new) untuk buat Google Sheet baharu. Namakannya
   contohnya `Pangkalan Data Bantuan`.
2. Menu **Extensions → Apps Script**.
3. Padam kod contoh, tampal keseluruhan isi fail `apps-script/Kod.gs` dari repo ini. Simpan.
4. Pilih fungsi **`setup`** di bar atas, klik **Run**. Google akan minta kebenaran —
   terima (Advanced → Go to project → Allow).
5. Buka **Execution log**. Catat **kod akses 6 digit** untuk setiap pegawai:
   ```
   Pegawai PS01 (Aminah Yusof) — kod akses: 123456
   ```
   Kod ini juga tersimpan dalam jadual `pengguna` di Sheet.
6. **Deploy → New deployment → Web app**
   - Description: apa-apa sahaja
   - **Execute as: Me**
   - **Who has access: Anyone**
   - Klik **Deploy**, salin **Web app URL** (berakhir dengan `/exec`).

> Setiap kali kod Apps Script diubah, kena **Deploy → Manage deployments → Edit → New version**,
> jika tidak perubahan tidak akan aktif.

## Bahagian 2 — Sambung frontend

Edit `docs/config.js`, isikan URL tadi:

```js
var API_URL = 'https://script.google.com/macros/s/XXXXXXXX/exec';
```

Commit dan push. Jika `API_URL` dibiarkan kosong, sistem jalan dalam **mod demo**
(data dalam pelayar sahaja) — berguna untuk tunjuk demo sebelum backend siap.

## Bahagian 3 — Publish ke GitHub Pages

1. Repo GitHub → **Settings → Pages**
2. **Source**: Deploy from a branch
3. **Branch**: `claude/loving-mccarthy-640b76` (atau `main` selepas merge) — **Folder: `/docs`**
4. Save. Dalam 1–2 minit laman akan hidup di:
   `https://<nama-pengguna>.github.io/<nama-repo>/`

---

## Peranan dan kebenaran

| Peranan | Boleh buat | Boleh lihat |
|---|---|---|
| Pemohon | Hantar permohonan, buat pembetulan, tarik balik | Permohonan sendiri sahaja (padan no. KP) |
| Pegawai Penyemak | Checklist semakan, kembalikan untuk pembetulan, hantar ke pelulus | Tugasan yang diagih kepadanya sahaja |
| Pegawai Pelulus | Lulus / tidak lulus / pulangkan kepada penyemak | Permohonan di peringkat kelulusan dan ke atas |
| Auditor | Lihat sahaja, muat turun CSV | Semua permohonan dan jejak audit |

Kebenaran dikuatkuasakan di **pelayan** (Apps Script), bukan di pelayar.

## Peraturan sistem

- **Nombor rujukan**: `BK/<tahun>/<5 digit>`, dijana guna `LockService` supaya tidak bertindih.
- **Agihan tugasan**: round-robin automatik antara pegawai penyemak aktif.
- **SLA**: semakan 5 hari bekerja, kelulusan 3 hari bekerja. Paparan tunjuk baki hari
  dan tandakan kes lewat. Peringatan automatik dihantar setiap pagi.
- **Pembetulan**: had 3 pusingan, 14 hari kalendar setiap pusingan. Tamat tempoh → tutup automatik.
- **Dokumen**: setiap muat naik semula = versi baharu; versi lama kekal dalam rekod dan dalam Drive.
- **Catatan wajib**: pengembalian untuk pembetulan dan setiap keputusan mesti ada sebab bertulis.
- **Jejak audit**: hanya `appendRow` — tiada fungsi edit atau padam dalam kod.

## Jadual dalam Google Sheet

| Jadual | Isi |
|---|---|
| `permohonan` | Satu baris setiap permohonan, termasuk status dan keputusan |
| `dokumen` | Setiap versi dokumen + pautan Google Drive |
| `audit` | Jejak audit, tambah sahaja |
| `notis` | Log pemberitahuan kepada pemohon dan pegawai |
| `pengguna` | Pegawai, peranan, e-mel, kod akses, status aktif |
| `tetapan` | Kaunter rujukan, kaunter agihan, ID folder Drive |

## Mengubah tetapan

- **Jenis bantuan, dokumen wajib, checklist, SLA, had pembetulan**: objek `CFG` di atas `Kod.gs`.
  Selepas ubah, deploy versi baharu.
- **Tambah / buang pegawai**: edit terus jadual `pengguna` dalam Sheet.
  Set lajur `aktif` kepada `TIDAK` untuk pegawai yang bercuti atau berhenti.
- **E-mel pemberitahuan**: isi lajur `emel` dalam jadual `pengguna`.
  Matikan sepenuhnya dengan `CFG.hantarEmel = false`.

## Had yang perlu diketahui

- **Kuota Google (akaun Gmail biasa)**: 100 e-mel/hari, 90 minit masa larian skrip/hari,
  50MB saiz Sheet. Pada 30 permohonan/minggu, jauh di bawah had.
- **Pengesahan pemohon** ialah nama + no. KP sahaja — cukup untuk ujian, tidak cukup untuk
  pengeluaran. Untuk produksi, ganti dengan log masuk disahkan (MyDigital ID atau e-mel OTP).
- **Kod akses pegawai** disimpan sebagai teks biasa dalam Sheet. Jangan kongsi Sheet
  kepada sesiapa yang tidak sepatutnya ada akses pentadbir.
- **Jejak audit** tidak boleh diubah melalui aplikasi, tetapi sesiapa yang ada akses edit
  kepada Sheet itu sendiri boleh mengubahnya. Untuk audit rasmi, hadkan perkongsian Sheet
  kepada pemilik sistem sahaja dan hidupkan Google Vault atau eksport berkala.
- Apps Script Web App jalan sebagai **pemilik Sheet**, jadi semua fail Drive dimiliki akaun itu.

## Menguji secara tempatan

```bash
cd docs
python3 -m http.server 8000
# buka http://localhost:8000
```

Biarkan `API_URL` kosong untuk mod demo, atau isikan untuk uji terus ke Google Sheets.
