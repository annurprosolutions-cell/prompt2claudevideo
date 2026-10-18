/* Enjin demo: melaksanakan API yang sama seperti Apps Script,
   tetapi data disimpan dalam localStorage pelayar.
   Digunakan hanya apabila API_URL kosong. */
var Demo = (function () {
  var KEY = 'sbantuan.demo.v2';
  var db = muat();

  function muat() {
    try { return JSON.parse(localStorage.getItem(KEY)) || kosong(); }
    catch (e) { return kosong(); }
  }
  function kosong() { return { seq: 0, rr: 0, apps: [], notis: [], sesi: {} }; }
  function simpan() { try { localStorage.setItem(KEY, JSON.stringify(db)); } catch (e) {} }

  var kini = function () { return new Date().toISOString(); };
  function tambahHariBekerja(h) {
    var d = new Date(), baki = h;
    while (baki > 0) { d.setDate(d.getDate() + 1); var x = d.getDay(); if (x !== 0 && x !== 6) baki--; }
    return d.toISOString();
  }
  function tambahHari(h) { var d = new Date(); d.setDate(d.getDate() + h); return d.toISOString(); }
  function tarikh(iso) {
    var d = new Date(iso);
    return ('0' + d.getDate()).slice(-2) + '/' + ('0' + (d.getMonth() + 1)).slice(-2) + '/' + d.getFullYear();
  }
  function namaPegawai(id) {
    var p = CFG.pegawai.filter(function (x) { return x.id === id; })[0];
    return p ? p.nama + ' (' + p.id + ')' : (id || '-');
  }
  function audit(app, sesi, tindakan, butiran) {
    app.audit.push({
      ts: kini(), pelakuNama: sesi ? sesi.nama : 'Sistem',
      peranan: sesi ? sesi.peranan : 'sistem', tindakan: tindakan, butiran: butiran || ''
    });
  }
  function notis(app, kepada, mesej) {
    db.notis.push({ ts: kini(), ref: app.ref, kepada: kepada, mesej: mesej });
  }
  function cari(id) { return db.apps.filter(function (a) { return a.id === id; })[0]; }

  function tamatTempoh() {
    db.apps.forEach(function (a) {
      if (a.status === 'PEMBETULAN' && a.deadlinePemohon && new Date(a.deadlinePemohon) < new Date()) {
        a.status = 'TAMAT'; a.dueAt = '';
        audit(a, null, 'TUTUP_AUTO', 'Pemohon tidak hantar pembetulan dalam tempoh ' + CFG.tempohPembetulanHari + ' hari');
        notis(a, a.pemohon.ic, 'Permohonan ' + a.ref + ' ditutup kerana tiada pembetulan dalam tempoh ditetapkan.');
      }
    });
  }
  function bolehLihat(sesi, a) {
    if (sesi.peranan === 'auditor') return true;
    if (sesi.peranan === 'pemohon') return a.pemohon.ic === sesi.ic;
    if (sesi.peranan === 'penyemak') return a.penyemakId === sesi.pegawaiId;
    if (sesi.peranan === 'pelulus') return ['KELULUSAN', 'LULUS', 'TOLAK'].indexOf(a.status) >= 0;
    return false;
  }
  function sahkan(req) {
    var p = req.pemohon || {}, b = req.butiran || {}, kosong = [];
    if (!p.nama) kosong.push('Nama');
    if (!p.ic) kosong.push('No. kad pengenalan');
    if (!p.tel) kosong.push('No. telefon');
    if (!p.alamat) kosong.push('Alamat');
    if (b.pendapatan === '' || b.pendapatan == null) kosong.push('Pendapatan');
    if (b.tanggungan === '' || b.tanggungan == null) kosong.push('Bilangan tanggungan');
    if (!b.sebab) kosong.push('Sebab permohonan');
    return kosong;
  }
  function csv() {
    var q = function (s) { return '"' + String(s == null ? '' : s).replace(/"/g, '""') + '"'; };
    var baris = [['No. Rujukan', 'Tarikh Hantar', 'Nama', 'No. KP', 'Jenis Bantuan', 'Pendapatan',
      'Status', 'Penyemak', 'Pelulus', 'Pusingan Pembetulan', 'Jumlah Lulus', 'Sebab Keputusan',
      'Bilangan Rekod Audit'].map(q).join(',')];
    db.apps.forEach(function (a) {
      baris.push([a.ref, tarikh(a.dihantarPada), a.pemohon.nama, a.pemohon.ic, a.butiran.jenis,
        a.butiran.pendapatan, STATUS[a.status].label, namaPegawai(a.penyemakId),
        a.pelulusId ? namaPegawai(a.pelulusId) : '', a.pusinganPembetulan,
        a.keputusan ? a.keputusan.jumlah : '', a.keputusan ? a.keputusan.sebab : '',
        a.audit.length].map(q).join(','));
    });
    return baris.join('\r\n');
  }

  function kendali(req) {
    var sesi = req.token ? db.sesi[req.token] : null;

    if (req.aksi === 'konfig') return { ok: true, cfg: null };
    if (req.aksi === 'login') {
      var s;
      if (req.peranan === 'pemohon') {
        if (!req.nama || !req.ic) return { ok: false, ralat: 'Nama dan no. kad pengenalan diperlukan.' };
        s = { peranan: 'pemohon', nama: req.nama, ic: req.ic, emel: req.emel || '' };
      } else {
        var p = CFG.pegawai.filter(function (x) { return x.id === req.pegawaiId; })[0];
        if (!p) return { ok: false, ralat: 'Pegawai tidak dijumpai.' };
        s = { peranan: p.peranan, nama: p.nama, pegawaiId: p.id };
      }
      s.token = 'demo-' + Date.now() + Math.random().toString(36).slice(2);
      db.sesi[s.token] = s; simpan();
      return { ok: true, sesi: s };
    }
    if (!sesi) return { ok: false, kodRalat: 'SESI_TAMAT', ralat: 'Sesi tamat. Sila log masuk semula.' };

    tamatTempoh();

    if (req.aksi === 'senarai') {
      var senarai = db.apps.filter(function (a) { return bolehLihat(sesi, a); })
        .map(function (a) {
          return {
            id: a.id, ref: a.ref, status: a.status, dihantarPada: a.dihantarPada,
            dueAt: a.dueAt, deadlinePemohon: a.deadlinePemohon,
            pemohon: { nama: a.pemohon.nama, ic: a.pemohon.ic },
            butiran: { jenis: a.butiran.jenis }
          };
        }).sort(function (x, y) { return String(y.dihantarPada).localeCompare(String(x.dihantarPada)); });
      var kepada = sesi.peranan === 'pemohon' ? sesi.ic : sesi.pegawaiId;
      var n = db.notis.filter(function (x) { return x.kepada === kepada; }).slice(-10).reverse();
      simpan();
      var hasil = { ok: true, senarai: senarai, notis: n };
      if (sesi.peranan === 'auditor') hasil.csv = csv();
      return hasil;
    }

    if (req.aksi === 'butiran') {
      var a1 = cari(req.id);
      if (!a1) return { ok: false, ralat: 'Permohonan tidak dijumpai.' };
      if (!bolehLihat(sesi, a1)) return { ok: false, ralat: 'Anda tiada kebenaran melihat permohonan ini.' };
      return { ok: true, permohonan: JSON.parse(JSON.stringify(a1)) };
    }

    if (req.aksi === 'hantar') {
      if (sesi.peranan !== 'pemohon') return { ok: false, ralat: 'Hanya pemohon boleh menghantar permohonan.' };
      var tiada = sahkan(req);
      CFG.dokumenWajib.forEach(function (d, i) {
        if (!req.fail || !req.fail[i]) tiada.push(d);
      });
      if (tiada.length) return { ok: false, ralat: 'Maklumat belum lengkap: ' + tiada.join(', ') };
      db.seq += 1;
      var penyemakList = CFG.pegawai.filter(function (p) { return p.peranan === 'penyemak'; });
      var penyemakId = penyemakList[db.rr % penyemakList.length].id;
      db.rr += 1;
      var baru = {
        id: 'A' + Date.now() + Math.floor(Math.random() * 1000),
        ref: CFG.prefix + '/' + new Date().getFullYear() + '/' + ('00000' + db.seq).slice(-5),
        dibukaPada: kini(), dihantarPada: kini(), status: 'BARU',
        pemohon: req.pemohon, butiran: req.butiran,
        dokumen: CFG.dokumenWajib.map(function (jenis, i) {
          return { jenis: jenis, nama: req.fail[i].nama, saiz: req.fail[i].saiz, versi: 1, pada: kini() };
        }),
        penyemakId: penyemakId, pelulusId: '', pusinganPembetulan: 0,
        catatanPembetulan: '', checklist: [], keputusan: null,
        dueAt: tambahHariBekerja(CFG.slaSemakanHari), deadlinePemohon: '', audit: []
      };
      db.apps.push(baru);
      audit(baru, sesi, 'HANTAR_PERMOHONAN', 'Permohonan dihantar oleh pemohon');
      audit(baru, null, 'AGIH_TUGASAN', 'Diagih secara automatik kepada ' + namaPegawai(penyemakId));
      notis(baru, baru.pemohon.ic, 'Permohonan anda diterima. No. rujukan: ' + baru.ref);
      notis(baru, penyemakId, 'Tugasan semakan baharu: ' + baru.ref + ' (' + baru.butiran.jenis + ')');
      simpan();
      return { ok: true, id: baru.id, ref: baru.ref, mesej: 'Permohonan berjaya dihantar. No. rujukan anda: ' + baru.ref };
    }

    if (req.aksi === 'pembetulan') {
      var a2 = cari(req.id);
      if (!a2) return { ok: false, ralat: 'Permohonan tidak dijumpai.' };
      if (sesi.peranan !== 'pemohon' || a2.pemohon.ic !== sesi.ic)
        return { ok: false, ralat: 'Anda tiada kebenaran ke atas permohonan ini.' };
      if (a2.status !== 'PEMBETULAN') return { ok: false, ralat: 'Permohonan ini tidak dalam status pembetulan.' };
      var tiada2 = sahkan(req);
      if (tiada2.length) return { ok: false, ralat: 'Maklumat belum lengkap: ' + tiada2.join(', ') };
      a2.pemohon = req.pemohon; a2.butiran = req.butiran;
      (req.fail || []).forEach(function (f, i) {
        if (!f) return;
        a2.dokumen[i] = { jenis: CFG.dokumenWajib[i], nama: f.nama, saiz: f.saiz,
          versi: (a2.dokumen[i] ? a2.dokumen[i].versi : 0) + 1, pada: kini() };
      });
      a2.status = 'SEMAKAN'; a2.catatanPembetulan = ''; a2.deadlinePemohon = '';
      a2.dueAt = tambahHariBekerja(CFG.slaSemakanHari);
      audit(a2, sesi, 'HANTAR_PEMBETULAN', 'Pembetulan pusingan ' + a2.pusinganPembetulan + ' dihantar');
      notis(a2, a2.penyemakId, 'Pembetulan diterima untuk ' + a2.ref + '. Sila semak semula.');
      simpan();
      return { ok: true, mesej: 'Pembetulan berjaya dihantar. Permohonan kembali kepada pegawai penyemak.' };
    }

    if (req.aksi === 'tarikBalik') {
      var a3 = cari(req.id);
      if (!a3 || a3.pemohon.ic !== sesi.ic) return { ok: false, ralat: 'Anda tiada kebenaran ke atas permohonan ini.' };
      if (['BARU', 'SEMAKAN', 'PEMBETULAN', 'KELULUSAN'].indexOf(a3.status) < 0)
        return { ok: false, ralat: 'Permohonan ini tidak boleh ditarik balik lagi.' };
      a3.status = 'DITARIK'; a3.dueAt = ''; a3.deadlinePemohon = '';
      audit(a3, sesi, 'TARIK_BALIK', 'Ditarik balik oleh pemohon');
      notis(a3, a3.penyemakId, a3.ref + ' ditarik balik oleh pemohon.');
      simpan();
      return { ok: true, mesej: 'Permohonan telah ditarik balik.' };
    }

    if (['simpanCatatan', 'kembaliPembetulan', 'hantarKelulusan'].indexOf(req.aksi) >= 0) {
      var a4 = cari(req.id);
      if (!a4) return { ok: false, ralat: 'Permohonan tidak dijumpai.' };
      if (sesi.peranan !== 'penyemak' || a4.penyemakId !== sesi.pegawaiId)
        return { ok: false, ralat: 'Permohonan ini bukan tugasan anda.' };
      if (['BARU', 'SEMAKAN'].indexOf(a4.status) < 0)
        return { ok: false, ralat: 'Permohonan ini tiada dalam peringkat semakan.' };
      var catatan = (req.catatan || '').trim();
      a4.checklist = req.checklist || [];

      if (req.aksi === 'simpanCatatan') {
        if (a4.status === 'BARU') { a4.status = 'SEMAKAN'; audit(a4, sesi, 'MULA_SEMAKAN', 'Semakan dimulakan'); }
        a4.catatanPembetulan = catatan;
        audit(a4, sesi, 'SIMPAN_CATATAN', 'Checklist: ' + a4.checklist.length + '/' + CFG.checklistSemakan.length);
        simpan();
        return { ok: true, mesej: 'Catatan semakan disimpan.' };
      }
      if (req.aksi === 'kembaliPembetulan') {
        if (!catatan) return { ok: false, ralat: 'Catatan wajib diisi — pemohon perlu tahu apa yang perlu dibetulkan.' };
        if (a4.pusinganPembetulan >= CFG.hadPusinganPembetulan)
          return { ok: false, ralat: 'Had ' + CFG.hadPusinganPembetulan + ' pusingan pembetulan telah dicapai.' };
        a4.pusinganPembetulan += 1; a4.status = 'PEMBETULAN'; a4.catatanPembetulan = catatan;
        a4.deadlinePemohon = tambahHari(CFG.tempohPembetulanHari); a4.dueAt = '';
        audit(a4, sesi, 'KEMBALI_PEMBETULAN', 'Pusingan ' + a4.pusinganPembetulan + ': ' + catatan);
        notis(a4, a4.pemohon.ic, a4.ref + ' dikembalikan untuk pembetulan. Tarikh akhir: ' +
          tarikh(a4.deadlinePemohon) + '. Catatan: ' + catatan);
        simpan();
        return { ok: true, mesej: 'Permohonan dikembalikan kepada pemohon.' };
      }
      var pelulus = CFG.pegawai.filter(function (p) { return p.peranan === 'pelulus'; })[0];
      a4.status = 'KELULUSAN'; a4.pelulusId = pelulus.id; a4.catatanPembetulan = catatan;
      a4.dueAt = tambahHariBekerja(CFG.slaKelulusanHari);
      audit(a4, sesi, 'HANTAR_KELULUSAN', 'Disyorkan kepada ' + namaPegawai(pelulus.id) +
        (catatan ? ' — catatan: ' + catatan : ''));
      notis(a4, pelulus.id, 'Permohonan ' + a4.ref + ' menunggu keputusan anda.');
      notis(a4, a4.pemohon.ic, a4.ref + ': semakan selesai, menunggu keputusan pegawai pelulus.');
      simpan();
      return { ok: true, mesej: 'Permohonan dihantar kepada pegawai pelulus.' };
    }

    if (req.aksi === 'keputusan') {
      var a5 = cari(req.id);
      if (!a5) return { ok: false, ralat: 'Permohonan tidak dijumpai.' };
      if (sesi.peranan !== 'pelulus') return { ok: false, ralat: 'Hanya pegawai pelulus boleh membuat keputusan.' };
      if (a5.status !== 'KELULUSAN') return { ok: false, ralat: 'Permohonan ini tidak menunggu kelulusan.' };
      var sebab = (req.sebab || '').trim();
      if (!sebab) return { ok: false, ralat: 'Ulasan/sebab keputusan wajib diisi untuk tujuan audit.' };
      var jumlah = req.lulus ? Number(req.jumlah || 0) : 0;
      if (req.lulus && !(jumlah > 0)) return { ok: false, ralat: 'Jumlah diluluskan perlu lebih daripada sifar.' };
      a5.status = req.lulus ? 'LULUS' : 'TOLAK'; a5.dueAt = '';
      a5.keputusan = { status: a5.status, jumlah: jumlah, tempoh: req.tempoh || '',
        sebab: sebab, oleh: sesi.pegawaiId, pada: kini() };
      audit(a5, sesi, a5.status, (req.lulus ? 'RM ' + jumlah + ' / ' + (req.tempoh || '-') + ' — ' : '') + sebab);
      notis(a5, a5.pemohon.ic, a5.ref + ': permohonan anda ' +
        (req.lulus ? 'DILULUSKAN (RM ' + jumlah + ')' : 'TIDAK DILULUSKAN') + '. Ulasan: ' + sebab);
      notis(a5, a5.penyemakId, a5.ref + ': keputusan ' + a5.status + ' telah dibuat.');
      simpan();
      return { ok: true, mesej: 'Keputusan direkodkan dan pemohon dimaklumkan.' };
    }

    if (req.aksi === 'pulangPenyemak') {
      var a6 = cari(req.id);
      if (!a6) return { ok: false, ralat: 'Permohonan tidak dijumpai.' };
      if (sesi.peranan !== 'pelulus') return { ok: false, ralat: 'Hanya pegawai pelulus boleh memulangkan permohonan.' };
      if (a6.status !== 'KELULUSAN') return { ok: false, ralat: 'Permohonan ini tidak menunggu kelulusan.' };
      var s6 = (req.sebab || '').trim();
      if (!s6) return { ok: false, ralat: 'Nyatakan sebab pemulangan kepada penyemak.' };
      a6.status = 'SEMAKAN'; a6.dueAt = tambahHariBekerja(CFG.slaSemakanHari);
      audit(a6, sesi, 'PULANG_KE_PENYEMAK', s6);
      notis(a6, a6.penyemakId, a6.ref + ' dipulangkan oleh pelulus: ' + s6);
      simpan();
      return { ok: true, mesej: 'Permohonan dipulangkan kepada pegawai penyemak.' };
    }

    return { ok: false, ralat: 'Aksi tidak dikenali: ' + req.aksi };
  }

  return { kendali: kendali };
})();
