/* ------------------------------------------------------------------
   TETAPAN SISTEM
   Letak URL Web App Apps Script di sini selepas deploy.
   Biarkan kosong untuk MOD DEMO (data dalam pelayar sahaja).
   ------------------------------------------------------------------ */
var API_URL = 'https://script.google.com/macros/s/AKfycbyc_BpqHSQ0yiuj4jfEKc6NgqVuugMZjfrBEz9_js_CVBP78oze0WdVHsG7qiSNo8q6lA/exec';

/* Tetapan paparan. Nilai sebenar diambil dari pelayan bila API_URL diisi. */
var CFG = {
  prefix: 'BK',
  hadPusinganPembetulan: 3,
  tempohPembetulanHari: 14,
  slaSemakanHari: 5,
  slaKelulusanHari: 3,
  maxSaizFailMB: 4,
  jenisBantuan: [
    'Bantuan Kewangan Bulanan',
    'Bantuan Sara Hidup',
    'Bantuan Perubatan',
    'Bantuan Pendidikan Anak',
    'Bantuan Bencana'
  ],
  dokumenWajib: [
    'Salinan Kad Pengenalan',
    'Slip Gaji / Surat Pengesahan Pendapatan',
    'Salinan Bil Utiliti (alamat)',
    'Penyata Bank 3 Bulan'
  ],
  checklistSemakan: [
    'Identiti pemohon sah dan sepadan dengan KP',
    'Semua dokumen wajib lengkap dan boleh dibaca',
    'Maklumat pendapatan konsisten dengan dokumen',
    'Pemohon tiada permohonan aktif lain yang bertindih',
    'Pemohon memenuhi kriteria kelayakan bantuan'
  ],
  pegawai: [
    { id: 'PS01', nama: 'Aminah Yusof',     peranan: 'penyemak' },
    { id: 'PS02', nama: 'Rahim Abdullah',   peranan: 'penyemak' },
    { id: 'PL01', nama: 'Dr. Faridah Omar', peranan: 'pelulus' },
    { id: 'AU01', nama: 'Unit Audit Dalam', peranan: 'auditor' }
  ]
};

var STATUS = {
  BARU:       { label: 'Baru Diterima',        cls: 'b-baru' },
  SEMAKAN:    { label: 'Dalam Semakan',        cls: 'b-semakan' },
  PEMBETULAN: { label: 'Perlu Pembetulan',     cls: 'b-pembetulan' },
  KELULUSAN:  { label: 'Menunggu Kelulusan',   cls: 'b-kelulusan' },
  LULUS:      { label: 'Lulus',                cls: 'b-lulus' },
  TOLAK:      { label: 'Tidak Lulus',          cls: 'b-tolak' },
  DITARIK:    { label: 'Ditarik Oleh Pemohon', cls: 'b-tutup' },
  TAMAT:      { label: 'Tutup - Tamat Tempoh', cls: 'b-tutup' }
};
