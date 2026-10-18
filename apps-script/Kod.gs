/**
 * Sistem Permohonan Bantuan — backend Google Apps Script
 * Pangkalan data: Google Sheets. Storan dokumen: Google Drive.
 *
 * LANGKAH PEMASANGAN (ringkas):
 *   1. Buat Google Sheet baharu → Extensions → Apps Script.
 *   2. Tampal fail ini, simpan.
 *   3. Jalankan fungsi setup() sekali (beri kebenaran bila diminta).
 *   4. Lihat Execution log untuk kod akses pegawai.
 *   5. Deploy → New deployment → Web app
 *        Execute as: Me
 *        Who has access: Anyone
 *      Salin URL /exec dan letak dalam docs/config.js
 */

/* ======================= TETAPAN ======================= */
var CFG = {
  prefix: 'BK',
  slaSemakanHari: 5,
  slaKelulusanHari: 3,
  hadPusinganPembetulan: 3,
  tempohPembetulanHari: 14,
  maxSaizFailMB: 4,
  hantarEmel: true,            // tukar false untuk matikan e-mel
  namaFolderDrive: 'Dokumen Permohonan Bantuan',
  tempohSesiJam: 6,
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
  ]
};

var PEGAWAI_AWAL = [
  { id: 'PS01', nama: 'Aminah Yusof',     peranan: 'penyemak', emel: '' },
  { id: 'PS02', nama: 'Rahim Abdullah',   peranan: 'penyemak', emel: '' },
  { id: 'PL01', nama: 'Dr. Faridah Omar', peranan: 'pelulus',  emel: '' },
  { id: 'AU01', nama: 'Unit Audit Dalam', peranan: 'auditor',  emel: '' }
];

var LJR = {
  permohonan: ['id','ref','dibukaPada','dihantarPada','status','nama','ic','tel','emel','alamat',
    'jenis','pendapatan','tanggungan','sebab','penyemakId','pelulusId','pusinganPembetulan',
    'catatanPembetulan','checklist','dueAt','deadlinePemohon','keputusanStatus','keputusanJumlah',
    'keputusanTempoh','keputusanSebab','keputusanOleh','keputusanPada','kemaskiniPada'],
  dokumen: ['id','permohonanId','jenis','nama','saiz','versi','pada','fileId','fileUrl'],
  audit: ['ts','permohonanId','ref','pelakuId','pelakuNama','peranan','tindakan','butiran'],
  notis: ['ts','permohonanId','ref','kepada','mesej','dibaca'],
  pengguna: ['id','nama','peranan','emel','kodAkses','aktif'],
  tetapan: ['kunci','nilai']
};

/* ======================= PEMASANGAN ======================= */
function setup() {
  var ss = SpreadsheetApp.getActiveSpreadsheet();
  Object.keys(LJR).forEach(function (nama) {
    var sh = ss.getSheetByName(nama);
    if (!sh) sh = ss.insertSheet(nama);
    if (sh.getLastRow() === 0) {
      sh.appendRow(LJR[nama]);
      sh.setFrozenRows(1);
      sh.getRange(1, 1, 1, LJR[nama].length).setFontWeight('bold');
    }
  });

  var shP = ss.getSheetByName('pengguna');
  if (shP.getLastRow() <= 1) {
    PEGAWAI_AWAL.forEach(function (p) {
      var kod = String(Math.floor(100000 + Math.random() * 900000));
      shP.appendRow([p.id, p.nama, p.peranan, p.emel, kod, 'YA']);
      Logger.log('Pegawai ' + p.id + ' (' + p.nama + ') — kod akses: ' + kod);
    });
  } else {
    Logger.log('Jadual pengguna sudah ada. Kod akses sedia ada dikekalkan.');
  }

  setTetapan('kaunterRujukan', String(getTetapan('kaunterRujukan') || '0'));
  folderDrive();

  var kosong = ss.getSheetByName('Sheet1') || ss.getSheetByName('Helaian1');
  if (kosong && kosong.getLastRow() === 0 && ss.getSheets().length > 1) ss.deleteSheet(kosong);

  pasangPencetus();
  Logger.log('Setup selesai. Seterusnya: Deploy → New deployment → Web app (Execute as: Me, Access: Anyone).');
}

function pasangPencetus() {
  ScriptApp.getProjectTriggers().forEach(function (t) {
    if (t.getHandlerFunction() === 'tugasHarian') ScriptApp.deleteTrigger(t);
  });
  ScriptApp.newTrigger('tugasHarian').timeBased().atHour(8).everyDays(1).create();
}

/** Dijalankan setiap hari: tutup kes tamat tempoh + peringatan SLA. */
function tugasHarian() {
  prosesTamatTempoh();
  peringatanSla();
}

/* ======================= UTILITI SHEET ======================= */
function ss_() { return SpreadsheetApp.getActiveSpreadsheet(); }
function sheet_(nama) {
  var sh = ss_().getSheetByName(nama);
  if (!sh) throw new Error('Jadual "' + nama + '" tiada. Sila jalankan setup() dahulu.');
  return sh;
}
function baca_(nama) {
  var sh = sheet_(nama);
  var nilai = sh.getDataRange().getValues();
  if (nilai.length < 2) return [];
  var kepala = nilai[0];
  return nilai.slice(1).map(function (baris, i) {
    var o = { _baris: i + 2 };
    kepala.forEach(function (k, j) { o[k] = baris[j]; });
    return o;
  });
}
function tambah_(nama, obj) {
  var sh = sheet_(nama);
  sh.appendRow(LJR[nama].map(function (k) { return obj[k] === undefined ? '' : obj[k]; }));
}
function kemas_(nama, baris, obj) {
  var sh = sheet_(nama);
  var sedia = sh.getRange(baris, 1, 1, LJR[nama].length).getValues()[0];
  var nilai = LJR[nama].map(function (k, i) {
    return obj[k] === undefined ? sedia[i] : obj[k];
  });
  sh.getRange(baris, 1, 1, LJR[nama].length).setValues([nilai]);
}
function getTetapan(kunci) {
  var r = baca_('tetapan').filter(function (x) { return x.kunci === kunci; })[0];
  return r ? r.nilai : null;
}
function setTetapan(kunci, nilai) {
  var r = baca_('tetapan').filter(function (x) { return x.kunci === kunci; })[0];
  if (r) kemas_('tetapan', r._baris, { kunci: kunci, nilai: nilai });
  else tambah_('tetapan', { kunci: kunci, nilai: nilai });
}

/* ======================= UTILITI AM ======================= */
function kini_() { return new Date().toISOString(); }
function iso_(v) {
  if (!v) return '';
  if (v instanceof Date) return v.toISOString();
  return String(v);
}
function tambahHariBekerja_(hari) {
  var d = new Date(), baki = hari;
  while (baki > 0) {
    d.setDate(d.getDate() + 1);
    var h = d.getDay();
    if (h !== 0 && h !== 6) baki--;
  }
  return d.toISOString();
}
function tambahHari_(hari) {
  var d = new Date();
  d.setDate(d.getDate() + hari);
  return d.toISOString();
}
function tarikhMy_(iso) {
  if (!iso) return '-';
  var d = new Date(iso);
  return Utilities.formatDate(d, 'Asia/Kuala_Lumpur', 'dd/MM/yyyy');
}
function nextRef_() {
  var lock = LockService.getScriptLock();
  lock.waitLock(20000);
  try {
    var n = parseInt(getTetapan('kaunterRujukan') || '0', 10) + 1;
    setTetapan('kaunterRujukan', String(n));
    return CFG.prefix + '/' + new Date().getFullYear() + '/' + ('00000' + n).slice(-5);
  } finally {
    lock.releaseLock();
  }
}
function folderDrive() {
  var id = getTetapan('folderId');
  if (id) {
    try { return DriveApp.getFolderById(id); } catch (e) { /* dicipta semula di bawah */ }
  }
  var f = DriveApp.createFolder(CFG.namaFolderDrive);
  setTetapan('folderId', f.getId());
  return f;
}
function emel_(kepada, tajuk, mesej) {
  if (!CFG.hantarEmel || !kepada) return;
  try { MailApp.sendEmail(kepada, tajuk, mesej); } catch (e) { Logger.log('Emel gagal: ' + e); }
}

/* ======================= SESI ======================= */
function buatSesi_(sesi) {
  var token = Utilities.getUuid();
  CacheService.getScriptCache().put('sesi:' + token,
    JSON.stringify(sesi), CFG.tempohSesiJam * 3600);
  sesi.token = token;
  return sesi;
}
function dapatSesi_(token) {
  if (!token) return null;
  var s = CacheService.getScriptCache().get('sesi:' + token);
  if (!s) return null;
  var o = JSON.parse(s);
  CacheService.getScriptCache().put('sesi:' + token, s, CFG.tempohSesiJam * 3600);
  return o;
}

/* ======================= TITIK MASUK ======================= */
function doGet(e) {
  return keluaran_({ ok: true, mesej: 'Sistem Permohonan Bantuan — API aktif', versi: 1 });
}
function doPost(e) {
  var req = {};
  try { req = JSON.parse(e.postData.contents); }
  catch (err) { return keluaran_({ ok: false, ralat: 'Permintaan tidak sah.' }); }
  try {
    return keluaran_(kendali_(req));
  } catch (err) {
    return keluaran_({ ok: false, ralat: String(err && err.message ? err.message : err) });
  }
}
function keluaran_(obj) {
  return ContentService.createTextOutput(JSON.stringify(obj))
    .setMimeType(ContentService.MimeType.JSON);
}

function kendali_(req) {
  var aksi = req.aksi;
  if (aksi === 'konfig') return { ok: true, cfg: konfigAwam_() };
  if (aksi === 'login') return login_(req);

  var sesi = dapatSesi_(req.token);
  if (!sesi) return { ok: false, kodRalat: 'SESI_TAMAT', ralat: 'Sesi tamat. Sila log masuk semula.' };

  switch (aksi) {
    case 'senarai':          return senarai_(sesi);
    case 'butiran':          return butiran_(sesi, req.id);
    case 'hantar':           return hantar_(sesi, req);
    case 'pembetulan':       return pembetulan_(sesi, req);
    case 'tarikBalik':       return tarikBalik_(sesi, req.id);
    case 'simpanCatatan':    return tindakanPenyemak_(sesi, req, 'simpan');
    case 'kembaliPembetulan':return tindakanPenyemak_(sesi, req, 'pembetulan');
    case 'hantarKelulusan':  return tindakanPenyemak_(sesi, req, 'kelulusan');
    case 'keputusan':        return keputusan_(sesi, req);
    case 'pulangPenyemak':   return pulangPenyemak_(sesi, req);
    default: return { ok: false, ralat: 'Aksi tidak dikenali: ' + aksi };
  }
}

function konfigAwam_() {
  return {
    jenisBantuan: CFG.jenisBantuan,
    dokumenWajib: CFG.dokumenWajib,
    checklistSemakan: CFG.checklistSemakan,
    hadPusinganPembetulan: CFG.hadPusinganPembetulan,
    tempohPembetulanHari: CFG.tempohPembetulanHari,
    maxSaizFailMB: CFG.maxSaizFailMB,
    pegawai: baca_('pengguna')
      .filter(function (p) { return String(p.aktif).toUpperCase() === 'YA'; })
      .map(function (p) { return { id: p.id, nama: p.nama, peranan: p.peranan }; })
  };
}

/* ======================= LOGIN ======================= */
function login_(req) {
  if (req.peranan === 'pemohon') {
    var nama = String(req.nama || '').trim();
    var ic = String(req.ic || '').trim();
    if (!nama || !ic) return { ok: false, ralat: 'Nama dan no. kad pengenalan diperlukan.' };
    return { ok: true, sesi: buatSesi_({ peranan: 'pemohon', nama: nama, ic: ic, emel: String(req.emel || '').trim() }) };
  }
  var p = baca_('pengguna').filter(function (x) {
    return String(x.id).trim() === String(req.pegawaiId || '').trim();
  })[0];
  if (!p || String(p.aktif).toUpperCase() !== 'YA') return { ok: false, ralat: 'Pegawai tidak dijumpai atau tidak aktif.' };
  if (String(p.kodAkses).trim() !== String(req.kod || '').trim()) return { ok: false, ralat: 'Kod akses salah.' };
  return { ok: true, sesi: buatSesi_({ peranan: p.peranan, nama: p.nama, pegawaiId: p.id, emel: p.emel }) };
}

/* ======================= BACA ======================= */
function hidrat_(r, dok, aud) {
  return {
    id: r.id, ref: r.ref,
    dibukaPada: iso_(r.dibukaPada), dihantarPada: iso_(r.dihantarPada),
    status: r.status,
    pemohon: { nama: r.nama, ic: r.ic, tel: r.tel, emel: r.emel, alamat: r.alamat },
    butiran: { jenis: r.jenis, pendapatan: r.pendapatan, tanggungan: r.tanggungan, sebab: r.sebab },
    penyemakId: r.penyemakId, pelulusId: r.pelulusId,
    pusinganPembetulan: Number(r.pusinganPembetulan || 0),
    catatanPembetulan: r.catatanPembetulan,
    checklist: r.checklist ? JSON.parse(r.checklist) : [],
    dueAt: iso_(r.dueAt), deadlinePemohon: iso_(r.deadlinePemohon),
    keputusan: r.keputusanStatus ? {
      status: r.keputusanStatus, jumlah: Number(r.keputusanJumlah || 0),
      tempoh: r.keputusanTempoh, sebab: r.keputusanSebab,
      oleh: r.keputusanOleh, pada: iso_(r.keputusanPada)
    } : null,
    dokumen: (dok || []).map(function (d) {
      return { jenis: d.jenis, nama: d.nama, saiz: d.saiz, versi: Number(d.versi || 1), pada: iso_(d.pada), fileUrl: d.fileUrl };
    }),
    audit: (aud || []).map(function (a) {
      return { ts: iso_(a.ts), pelakuNama: a.pelakuNama, peranan: a.peranan, tindakan: a.tindakan, butiran: a.butiran };
    })
  };
}

function bolehLihat_(sesi, r) {
  if (sesi.peranan === 'auditor') return true;
  if (sesi.peranan === 'pemohon') return String(r.ic).trim() === String(sesi.ic).trim();
  if (sesi.peranan === 'penyemak') return r.penyemakId === sesi.pegawaiId;
  if (sesi.peranan === 'pelulus') return ['KELULUSAN', 'LULUS', 'TOLAK'].indexOf(r.status) >= 0;
  return false;
}

function senarai_(sesi) {
  prosesTamatTempoh();
  var semua = baca_('permohonan').filter(function (r) { return r.id && bolehLihat_(sesi, r); });
  var ringkas = semua.map(function (r) {
    return {
      id: r.id, ref: r.ref, status: r.status, dihantarPada: iso_(r.dihantarPada),
      dueAt: iso_(r.dueAt), deadlinePemohon: iso_(r.deadlinePemohon),
      pemohon: { nama: r.nama, ic: r.ic },
      butiran: { jenis: r.jenis }
    };
  }).sort(function (a, b) { return String(b.dihantarPada).localeCompare(String(a.dihantarPada)); });

  var kepada = sesi.peranan === 'pemohon' ? sesi.ic : sesi.pegawaiId;
  var notis = baca_('notis').filter(function (n) { return String(n.kepada).trim() === String(kepada).trim(); })
    .map(function (n) { return { ts: iso_(n.ts), ref: n.ref, mesej: n.mesej }; })
    .slice(-10).reverse();

  var hasil = { ok: true, senarai: ringkas, notis: notis };
  if (sesi.peranan === 'auditor') hasil.csv = csvSemua_();
  return hasil;
}

function butiran_(sesi, id) {
  var r = baca_('permohonan').filter(function (x) { return x.id === id; })[0];
  if (!r) return { ok: false, ralat: 'Permohonan tidak dijumpai.' };
  if (!bolehLihat_(sesi, r)) return { ok: false, ralat: 'Anda tiada kebenaran melihat permohonan ini.' };
  var dok = baca_('dokumen').filter(function (d) { return d.permohonanId === id; });
  var aud = baca_('audit').filter(function (a) { return a.permohonanId === id; });
  return { ok: true, permohonan: hidrat_(r, dok, aud) };
}

/* ======================= AUDIT & NOTIS ======================= */
function audit_(r, sesi, tindakan, butiran) {
  tambah_('audit', {
    ts: kini_(), permohonanId: r.id, ref: r.ref,
    pelakuId: sesi ? (sesi.pegawaiId || sesi.ic) : 'SISTEM',
    pelakuNama: sesi ? sesi.nama : 'Sistem',
    peranan: sesi ? sesi.peranan : 'sistem',
    tindakan: tindakan, butiran: butiran || ''
  });
}
function notis_(r, kepada, mesej, emelKepada) {
  tambah_('notis', { ts: kini_(), permohonanId: r.id, ref: r.ref, kepada: kepada, mesej: mesej, dibaca: 'TIDAK' });
  emel_(emelKepada, '[' + r.ref + '] Sistem Permohonan Bantuan', mesej);
}
function emelPegawai_(id) {
  var p = baca_('pengguna').filter(function (x) { return x.id === id; })[0];
  return p ? p.emel : '';
}
function namaPegawai_(id) {
  var p = baca_('pengguna').filter(function (x) { return x.id === id; })[0];
  return p ? p.nama + ' (' + p.id + ')' : (id || '-');
}
function penyemakSeterusnya_() {
  var senarai = baca_('pengguna').filter(function (p) {
    return p.peranan === 'penyemak' && String(p.aktif).toUpperCase() === 'YA';
  });
  if (!senarai.length) throw new Error('Tiada pegawai penyemak aktif.');
  var n = parseInt(getTetapan('kaunterAgih') || '0', 10);
  setTetapan('kaunterAgih', String(n + 1));
  return senarai[n % senarai.length].id;
}

/* ======================= DOKUMEN ======================= */
function simpanFail_(permohonanId, ref, jenis, fail, versi) {
  var had = CFG.maxSaizFailMB * 1024 * 1024;
  var data = Utilities.base64Decode(fail.data);
  if (data.length > had) throw new Error('Fail "' + fail.nama + '" melebihi ' + CFG.maxSaizFailMB + 'MB.');
  var folder = folderDrive();
  var namaFail = ref.replace(/\//g, '-') + ' - ' + jenis + ' - v' + versi + ' - ' + fail.nama;
  var blob = Utilities.newBlob(data, fail.jenisMime || 'application/octet-stream', namaFail);
  var f = folder.createFile(blob);
  return { fileId: f.getId(), fileUrl: f.getUrl(), saiz: data.length };
}

/* ======================= PEMOHON: HANTAR ======================= */
function sahkanBorang_(req) {
  var p = req.pemohon || {}, b = req.butiran || {};
  var kosong = [];
  if (!String(p.nama || '').trim()) kosong.push('Nama');
  if (!String(p.ic || '').trim()) kosong.push('No. kad pengenalan');
  if (!String(p.tel || '').trim()) kosong.push('No. telefon');
  if (!String(p.alamat || '').trim()) kosong.push('Alamat');
  if (String(b.pendapatan || '') === '') kosong.push('Pendapatan');
  if (String(b.tanggungan || '') === '') kosong.push('Bilangan tanggungan');
  if (!String(b.sebab || '').trim()) kosong.push('Sebab permohonan');
  if (CFG.jenisBantuan.indexOf(b.jenis) < 0) kosong.push('Jenis bantuan');
  return kosong;
}

function hantar_(sesi, req) {
  if (sesi.peranan !== 'pemohon') return { ok: false, ralat: 'Hanya pemohon boleh menghantar permohonan.' };
  var kosong = sahkanBorang_(req);
  var fail = req.fail || [];
  CFG.dokumenWajib.forEach(function (d, i) {
    if (!fail[i] || !fail[i].data) kosong.push(d);
  });
  if (kosong.length) return { ok: false, ralat: 'Maklumat belum lengkap: ' + kosong.join(', ') };

  var lock = LockService.getScriptLock();
  lock.waitLock(20000);
  try {
    var id = 'A' + new Date().getTime() + Math.floor(Math.random() * 1000);
    var ref = nextRef_();
    var penyemakId = penyemakSeterusnya_();
    var rec = {
      id: id, ref: ref, dibukaPada: kini_(), dihantarPada: kini_(), status: 'BARU',
      nama: req.pemohon.nama, ic: req.pemohon.ic, tel: req.pemohon.tel,
      emel: req.pemohon.emel || '', alamat: req.pemohon.alamat,
      jenis: req.butiran.jenis, pendapatan: req.butiran.pendapatan,
      tanggungan: req.butiran.tanggungan, sebab: req.butiran.sebab,
      penyemakId: penyemakId, pelulusId: '', pusinganPembetulan: 0,
      catatanPembetulan: '', checklist: '[]',
      dueAt: tambahHariBekerja_(CFG.slaSemakanHari), deadlinePemohon: '',
      keputusanStatus: '', kemaskiniPada: kini_()
    };
    tambah_('permohonan', rec);

    CFG.dokumenWajib.forEach(function (jenis, i) {
      var fs = simpanFail_(id, ref, jenis, fail[i], 1);
      tambah_('dokumen', {
        id: Utilities.getUuid(), permohonanId: id, jenis: jenis, nama: fail[i].nama,
        saiz: fs.saiz, versi: 1, pada: kini_(), fileId: fs.fileId, fileUrl: fs.fileUrl
      });
    });

    audit_(rec, sesi, 'HANTAR_PERMOHONAN', 'Permohonan dihantar oleh pemohon');
    audit_(rec, null, 'AGIH_TUGASAN', 'Diagih secara automatik kepada ' + namaPegawai_(penyemakId));
    notis_(rec, rec.ic, 'Permohonan anda diterima. No. rujukan: ' + ref, rec.emel);
    notis_(rec, penyemakId, 'Tugasan semakan baharu: ' + ref + ' (' + rec.jenis + ')', emelPegawai_(penyemakId));
    return { ok: true, id: id, ref: ref, mesej: 'Permohonan berjaya dihantar. No. rujukan anda: ' + ref };
  } finally {
    lock.releaseLock();
  }
}

function pembetulan_(sesi, req) {
  var r = baca_('permohonan').filter(function (x) { return x.id === req.id; })[0];
  if (!r) return { ok: false, ralat: 'Permohonan tidak dijumpai.' };
  if (sesi.peranan !== 'pemohon' || String(r.ic).trim() !== String(sesi.ic).trim())
    return { ok: false, ralat: 'Anda tiada kebenaran ke atas permohonan ini.' };
  if (r.status !== 'PEMBETULAN') return { ok: false, ralat: 'Permohonan ini tidak dalam status pembetulan.' };
  if (r.deadlinePemohon && new Date(iso_(r.deadlinePemohon)) < new Date())
    return { ok: false, ralat: 'Tempoh pembetulan telah tamat.' };

  var kosong = sahkanBorang_(req);
  if (kosong.length) return { ok: false, ralat: 'Maklumat belum lengkap: ' + kosong.join(', ') };

  var dokSedia = baca_('dokumen').filter(function (d) { return d.permohonanId === r.id; });
  var fail = req.fail || [];
  CFG.dokumenWajib.forEach(function (jenis, i) {
    if (fail[i] && fail[i].data) {
      var versiLama = dokSedia.filter(function (d) { return d.jenis === jenis; })
        .reduce(function (m, d) { return Math.max(m, Number(d.versi || 0)); }, 0);
      var fs = simpanFail_(r.id, r.ref, jenis, fail[i], versiLama + 1);
      tambah_('dokumen', {
        id: Utilities.getUuid(), permohonanId: r.id, jenis: jenis, nama: fail[i].nama,
        saiz: fs.saiz, versi: versiLama + 1, pada: kini_(), fileId: fs.fileId, fileUrl: fs.fileUrl
      });
    }
  });

  kemas_('permohonan', r._baris, {
    nama: req.pemohon.nama, tel: req.pemohon.tel, emel: req.pemohon.emel || '',
    alamat: req.pemohon.alamat, jenis: req.butiran.jenis, pendapatan: req.butiran.pendapatan,
    tanggungan: req.butiran.tanggungan, sebab: req.butiran.sebab,
    status: 'SEMAKAN', catatanPembetulan: '', deadlinePemohon: '',
    dueAt: tambahHariBekerja_(CFG.slaSemakanHari), kemaskiniPada: kini_()
  });
  audit_(r, sesi, 'HANTAR_PEMBETULAN', 'Pembetulan pusingan ' + r.pusinganPembetulan + ' dihantar');
  notis_(r, r.penyemakId, 'Pembetulan diterima untuk ' + r.ref + '. Sila semak semula.', emelPegawai_(r.penyemakId));
  return { ok: true, mesej: 'Pembetulan berjaya dihantar. Permohonan kembali kepada pegawai penyemak.' };
}

function tarikBalik_(sesi, id) {
  var r = baca_('permohonan').filter(function (x) { return x.id === id; })[0];
  if (!r) return { ok: false, ralat: 'Permohonan tidak dijumpai.' };
  if (sesi.peranan !== 'pemohon' || String(r.ic).trim() !== String(sesi.ic).trim())
    return { ok: false, ralat: 'Anda tiada kebenaran ke atas permohonan ini.' };
  if (['BARU', 'SEMAKAN', 'PEMBETULAN', 'KELULUSAN'].indexOf(r.status) < 0)
    return { ok: false, ralat: 'Permohonan ini tidak boleh ditarik balik lagi.' };

  kemas_('permohonan', r._baris, { status: 'DITARIK', dueAt: '', deadlinePemohon: '', kemaskiniPada: kini_() });
  audit_(r, sesi, 'TARIK_BALIK', 'Ditarik balik oleh pemohon');
  if (r.penyemakId) notis_(r, r.penyemakId, r.ref + ' ditarik balik oleh pemohon.', emelPegawai_(r.penyemakId));
  return { ok: true, mesej: 'Permohonan telah ditarik balik.' };
}

/* ======================= PENYEMAK ======================= */
function tindakanPenyemak_(sesi, req, mod) {
  var r = baca_('permohonan').filter(function (x) { return x.id === req.id; })[0];
  if (!r) return { ok: false, ralat: 'Permohonan tidak dijumpai.' };
  if (sesi.peranan !== 'penyemak' || r.penyemakId !== sesi.pegawaiId)
    return { ok: false, ralat: 'Permohonan ini bukan tugasan anda.' };
  if (['BARU', 'SEMAKAN'].indexOf(r.status) < 0)
    return { ok: false, ralat: 'Permohonan ini tiada dalam peringkat semakan.' };

  var checklist = JSON.stringify(req.checklist || []);
  var catatan = String(req.catatan || '').trim();

  if (mod === 'simpan') {
    kemas_('permohonan', r._baris, {
      status: 'SEMAKAN', checklist: checklist, catatanPembetulan: catatan, kemaskiniPada: kini_()
    });
    if (r.status === 'BARU') audit_(r, sesi, 'MULA_SEMAKAN', 'Semakan dimulakan');
    audit_(r, sesi, 'SIMPAN_CATATAN', 'Checklist: ' + (req.checklist || []).length + '/' + CFG.checklistSemakan.length);
    return { ok: true, mesej: 'Catatan semakan disimpan.' };
  }

  if (mod === 'pembetulan') {
    if (!catatan) return { ok: false, ralat: 'Catatan wajib diisi — pemohon perlu tahu apa yang perlu dibetulkan.' };
    var pusingan = Number(r.pusinganPembetulan || 0);
    if (pusingan >= CFG.hadPusinganPembetulan)
      return { ok: false, ralat: 'Had ' + CFG.hadPusinganPembetulan + ' pusingan pembetulan telah dicapai.' };
    var deadline = tambahHari_(CFG.tempohPembetulanHari);
    kemas_('permohonan', r._baris, {
      status: 'PEMBETULAN', checklist: checklist, catatanPembetulan: catatan,
      pusinganPembetulan: pusingan + 1, deadlinePemohon: deadline, dueAt: '', kemaskiniPada: kini_()
    });
    audit_(r, sesi, 'KEMBALI_PEMBETULAN', 'Pusingan ' + (pusingan + 1) + ': ' + catatan);
    notis_(r, r.ic, r.ref + ' dikembalikan untuk pembetulan. Tarikh akhir: ' + tarikhMy_(deadline) +
      '. Catatan: ' + catatan, r.emel);
    return { ok: true, mesej: 'Permohonan dikembalikan kepada pemohon.' };
  }

  // mod === 'kelulusan'
  var pelulus = baca_('pengguna').filter(function (p) {
    return p.peranan === 'pelulus' && String(p.aktif).toUpperCase() === 'YA';
  })[0];
  if (!pelulus) return { ok: false, ralat: 'Tiada pegawai pelulus aktif.' };
  kemas_('permohonan', r._baris, {
    status: 'KELULUSAN', checklist: checklist, catatanPembetulan: catatan,
    pelulusId: pelulus.id, dueAt: tambahHariBekerja_(CFG.slaKelulusanHari), kemaskiniPada: kini_()
  });
  audit_(r, sesi, 'HANTAR_KELULUSAN', 'Disyorkan kepada ' + namaPegawai_(pelulus.id) +
    (catatan ? ' — catatan: ' + catatan : ''));
  notis_(r, pelulus.id, 'Permohonan ' + r.ref + ' menunggu keputusan anda.', pelulus.emel);
  notis_(r, r.ic, r.ref + ': semakan selesai, menunggu keputusan pegawai pelulus.', r.emel);
  return { ok: true, mesej: 'Permohonan dihantar kepada pegawai pelulus.' };
}

/* ======================= PELULUS ======================= */
function keputusan_(sesi, req) {
  var r = baca_('permohonan').filter(function (x) { return x.id === req.id; })[0];
  if (!r) return { ok: false, ralat: 'Permohonan tidak dijumpai.' };
  if (sesi.peranan !== 'pelulus') return { ok: false, ralat: 'Hanya pegawai pelulus boleh membuat keputusan.' };
  if (r.status !== 'KELULUSAN') return { ok: false, ralat: 'Permohonan ini tidak menunggu kelulusan.' };

  var sebab = String(req.sebab || '').trim();
  if (!sebab) return { ok: false, ralat: 'Ulasan/sebab keputusan wajib diisi untuk tujuan audit.' };
  var lulus = !!req.lulus;
  var jumlah = lulus ? Number(req.jumlah || 0) : 0;
  if (lulus && !(jumlah > 0)) return { ok: false, ralat: 'Jumlah diluluskan perlu lebih daripada sifar.' };

  var status = lulus ? 'LULUS' : 'TOLAK';
  kemas_('permohonan', r._baris, {
    status: status, dueAt: '', keputusanStatus: status, keputusanJumlah: jumlah,
    keputusanTempoh: lulus ? (req.tempoh || '') : '', keputusanSebab: sebab,
    keputusanOleh: sesi.pegawaiId, keputusanPada: kini_(), kemaskiniPada: kini_()
  });
  audit_(r, sesi, status, (lulus ? 'RM ' + jumlah + ' / ' + (req.tempoh || '-') + ' — ' : '') + sebab);
  notis_(r, r.ic, r.ref + ': permohonan anda ' +
    (lulus ? 'DILULUSKAN (RM ' + jumlah + ')' : 'TIDAK DILULUSKAN') + '. Ulasan: ' + sebab, r.emel);
  notis_(r, r.penyemakId, r.ref + ': keputusan ' + status + ' telah dibuat.', emelPegawai_(r.penyemakId));
  return { ok: true, mesej: 'Keputusan direkodkan dan pemohon dimaklumkan.' };
}

function pulangPenyemak_(sesi, req) {
  var r = baca_('permohonan').filter(function (x) { return x.id === req.id; })[0];
  if (!r) return { ok: false, ralat: 'Permohonan tidak dijumpai.' };
  if (sesi.peranan !== 'pelulus') return { ok: false, ralat: 'Hanya pegawai pelulus boleh memulangkan permohonan.' };
  if (r.status !== 'KELULUSAN') return { ok: false, ralat: 'Permohonan ini tidak menunggu kelulusan.' };
  var sebab = String(req.sebab || '').trim();
  if (!sebab) return { ok: false, ralat: 'Nyatakan sebab pemulangan kepada penyemak.' };

  kemas_('permohonan', r._baris, {
    status: 'SEMAKAN', dueAt: tambahHariBekerja_(CFG.slaSemakanHari), kemaskiniPada: kini_()
  });
  audit_(r, sesi, 'PULANG_KE_PENYEMAK', sebab);
  notis_(r, r.penyemakId, r.ref + ' dipulangkan oleh pelulus: ' + sebab, emelPegawai_(r.penyemakId));
  return { ok: true, mesej: 'Permohonan dipulangkan kepada pegawai penyemak.' };
}

/* ======================= TUGAS AUTOMATIK ======================= */
function prosesTamatTempoh() {
  baca_('permohonan').forEach(function (r) {
    if (r.status !== 'PEMBETULAN' || !r.deadlinePemohon) return;
    if (new Date(iso_(r.deadlinePemohon)) >= new Date()) return;
    kemas_('permohonan', r._baris, { status: 'TAMAT', dueAt: '', kemaskiniPada: kini_() });
    audit_(r, null, 'TUTUP_AUTO', 'Pemohon tidak hantar pembetulan dalam tempoh ' + CFG.tempohPembetulanHari + ' hari');
    notis_(r, r.ic, 'Permohonan ' + r.ref + ' ditutup kerana tiada pembetulan dalam tempoh ditetapkan.', r.emel);
  });
}

function peringatanSla() {
  var esok = new Date();
  esok.setDate(esok.getDate() + 1);
  baca_('permohonan').forEach(function (r) {
    if (['BARU', 'SEMAKAN', 'KELULUSAN'].indexOf(r.status) < 0 || !r.dueAt) return;
    var due = new Date(iso_(r.dueAt));
    if (due > esok) return;
    var pegawai = r.status === 'KELULUSAN' ? r.pelulusId : r.penyemakId;
    var lewat = due < new Date();
    notis_(r, pegawai, r.ref + (lewat ? ' SUDAH LEWAT SLA' : ' hampir tamat tempoh SLA') +
      ' (' + tarikhMy_(iso_(r.dueAt)) + '). Sila ambil tindakan.', emelPegawai_(pegawai));
  });
}

/* ======================= CSV UNTUK AUDITOR ======================= */
function csvSemua_() {
  var q = function (s) { return '"' + String(s === null || s === undefined ? '' : s).replace(/"/g, '""') + '"'; };
  var audit = baca_('audit');
  var baris = [['No. Rujukan', 'Tarikh Hantar', 'Nama', 'No. KP', 'Jenis Bantuan', 'Pendapatan',
    'Status', 'Penyemak', 'Pelulus', 'Pusingan Pembetulan', 'Jumlah Lulus', 'Sebab Keputusan',
    'Bilangan Rekod Audit'].map(q).join(',')];
  baca_('permohonan').forEach(function (r) {
    if (!r.id) return;
    var n = audit.filter(function (a) { return a.permohonanId === r.id; }).length;
    baris.push([r.ref, tarikhMy_(iso_(r.dihantarPada)), r.nama, r.ic, r.jenis, r.pendapatan,
      r.status, namaPegawai_(r.penyemakId), r.pelulusId ? namaPegawai_(r.pelulusId) : '',
      r.pusinganPembetulan, r.keputusanJumlah, r.keputusanSebab, n].map(q).join(','));
  });
  return baris.join('\r\n');
}
