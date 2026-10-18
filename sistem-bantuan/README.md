# Sistem Permohonan Bantuan (Prototaip)

Prototaip aliran kerja permohonan bantuan untuk agensi kerajaan:
**Pemohon → Pegawai Penyemak → Pegawai Pelulus**, lengkap dengan nombor rujukan,
SLA, pemberitahuan, versi dokumen dan jejak audit.

## Cara guna

Buka `index.html` dalam pelayar, atau lawati tapak Netlify yang di-deploy.
Pilih peranan untuk mencuba aliran kerja:

| Peranan | Boleh buat |
|---|---|
| Pemohon | Hantar permohonan, buat pembetulan, tarik balik, semak status |
| Pegawai Penyemak (PS01/PS02) | Semak checklist, kembalikan untuk pembetulan, hantar ke pelulus |
| Pegawai Pelulus (PL01) | Lulus / tidak lulus / pulangkan kepada penyemak |
| Auditor (AU01) | Lihat semua permohonan + jejak audit, muat turun CSV |

## Keputusan reka bentuk

- **Nombor rujukan**: `BK/<tahun>/<5 digit berjujukan>` dijana semasa penghantaran.
- **Agihan tugasan**: automatik round-robin antara pegawai penyemak.
- **SLA**: 5 hari bekerja untuk semakan, 3 hari bekerja untuk kelulusan. Papan pemuka
  menunjukkan baki hari dan menandakan kes yang lewat.
- **Pembetulan**: had 3 pusingan; pemohon diberi 14 hari kalendar setiap pusingan.
  Permohonan ditutup secara automatik jika tempoh tamat.
- **Dokumen**: setiap muat naik semula menyimpan nombor versi, versi lama kekal dalam rekod.
- **Jejak audit**: hanya ditambah (append-only) — tiada fungsi edit atau padam dalam aplikasi.
- **Catatan wajib**: pengembalian untuk pembetulan dan semua keputusan memerlukan sebab bertulis.

## Konfigurasi

Semua parameter ada di bahagian atas `app.js` dalam objek `CFG`:
jenis bantuan, senarai dokumen wajib, checklist semakan, tempoh SLA,
had pusingan pembetulan, dan senarai pegawai.

## Had prototaip ini

Versi ini **client-side sahaja** (tiada kos hosting). Data disimpan dalam
`localStorage` pelayar — tiada pangkalan data berkongsi, tiada pengesahan identiti
sebenar, dan fail dokumen tidak dimuat naik ke mana-mana pelayan.

Untuk pengeluaran, yang perlu ditambah:

1. **Backend + pangkalan data** — Supabase atau Firebase (ada pelan percuma) untuk
   data berkongsi, storan dokumen dan kawalan akses baris (RLS).
2. **Pengesahan identiti** — log masuk pegawai, dan MyDigital ID / e-mel disahkan untuk pemohon.
3. **Jejak audit tidak boleh ubah** — tulis ke jadual append-only dengan `INSERT` sahaja,
   tanpa kebenaran `UPDATE`/`DELETE` walaupun untuk admin.
4. **Notifikasi sebenar** — e-mel/SMS; peringatan automatik sebelum SLA tamat.
5. **Delegasi & eskalasi** — ganti pegawai yang bercuti, eskalasi kes lewat kepada ketua.
6. **PDPA** — notis privasi, persetujuan, dasar pengekalan rekod.
