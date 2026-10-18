/* Antara muka pengguna. Semua data melalui Api (Apps Script atau mod demo). */

var el = document.getElementById('app');
var sesi = null;
try { sesi = JSON.parse(sessionStorage.getItem('sbantuan.sesi') || 'null'); } catch (e) {}
var view = { nama: 'senarai', id: null };
var mesejSeterusnya = null;

function setSesi(s) {
  sesi = s;
  Api.setToken(s ? s.token : null);
  try {
    s ? sessionStorage.setItem('sbantuan.sesi', JSON.stringify(s))
      : sessionStorage.removeItem('sbantuan.sesi');
  } catch (e) {}
}

/* ---------- utiliti paparan ---------- */
function esc(s) {
  return String(s == null ? '' : s).replace(/&/g, '&amp;').replace(/</g, '&lt;')
    .replace(/>/g, '&gt;').replace(/"/g, '&quot;').replace(/'/g, '&#39;');
}
function tarikh(iso, denganMasa) {
  if (!iso) return '-';
  var d = new Date(iso);
  if (isNaN(d)) return '-';
  var s = ('0' + d.getDate()).slice(-2) + '/' + ('0' + (d.getMonth() + 1)).slice(-2) + '/' + d.getFullYear();
  return denganMasa ? s + ' ' + ('0' + d.getHours()).slice(-2) + ':' + ('0' + d.getMinutes()).slice(-2) : s;
}
function rm(n) {
  return 'RM ' + Number(n || 0).toLocaleString('en-MY', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}
function bakiHari(iso) { return Math.ceil((new Date(iso) - new Date()) / 86400000); }
function slaHtml(a) {
  if (['BARU', 'SEMAKAN', 'KELULUSAN'].indexOf(a.status) < 0 || !a.dueAt) return '';
  var b = bakiHari(a.dueAt);
  if (b < 0) return '<span class="sla-late">Lewat ' + Math.abs(b) + ' hari</span>';
  if (b <= 1) return '<span class="sla-warn">Tempoh tamat ' + tarikh(a.dueAt) + '</span>';
  return '<span class="sla-ok">Baki ' + b + ' hari</span>';
}
function namaPegawai(id) {
  var p = (CFG.pegawai || []).filter(function (x) { return x.id === id; })[0];
  return p ? p.nama + ' (' + p.id + ')' : (id || '-');
}
function peranLabel(p) {
  return { pemohon: 'Pemohon', penyemak: 'Pegawai Penyemak', pelulus: 'Pegawai Pelulus', auditor: 'Auditor' }[p] || p;
}
function stat(s) { return STATUS[s] || { label: s, cls: 'b-tutup' }; }
function memuatkan(teks) {
  el.innerHTML = '<div class="card"><p class="muted">' + esc(teks || 'Sedang memuatkan…') + '</p></div>';
}
function mesejHtml() {
  if (!mesejSeterusnya) return '';
  var m = mesejSeterusnya; mesejSeterusnya = null;
  return '<div class="notice ' + (m.jenis === 'err' ? 'err' : 'ok') + '">' + esc(m.teks) + '</div>';
}
function banner() {
  if (Api.modSheet) return '';
  return '<div class="notice">Mod demo — data disimpan dalam pelayar ini sahaja. ' +
    'Isi <code>API_URL</code> dalam <code>config.js</code> untuk sambung ke Google Sheets.</div>';
}
function kendaliRalat(r) {
  if (r.kodRalat === 'SESI_TAMAT') {
    setSesi(null);
    mesejSeterusnya = { teks: 'Sesi tamat. Sila log masuk semula.', jenis: 'err' };
    render();
    return true;
  }
  return false;
}
function go(nama, id) { view = { nama: nama, id: id || null }; render(); }

/* ---------- kerangka ---------- */
function render() {
  var who = document.getElementById('who');
  var btnOut = document.getElementById('btnLogout');
  if (!sesi) { who.textContent = ''; btnOut.hidden = true; return renderLogin(); }
  who.textContent = sesi.nama + ' — ' + peranLabel(sesi.peranan);
  btnOut.hidden = false;
  if (view.nama === 'butiran') return renderButiran();
  if (view.nama === 'borang') return renderBorang();
  return renderSenarai();
}
document.getElementById('btnLogout').onclick = function () { setSesi(null); go('senarai'); };

/* ---------- log masuk ---------- */
function renderLogin() {
  el.innerHTML = banner() + mesejHtml() + '\
  <div class="card login">\
    <h2>Masuk ke sistem</h2>\
    <label>Peranan</label>\
    <select id="peranan">\
      <option value="pemohon">Pemohon</option>\
      <option value="penyemak">Pegawai Penyemak</option>\
      <option value="pelulus">Pegawai Pelulus</option>\
      <option value="auditor">Auditor (lihat sahaja)</option>\
    </select>\
    <div id="medanPemohon">\
      <label>Nama penuh</label><input id="lNama" placeholder="Siti Nurhaliza binti Ahmad">\
      <label>No. Kad Pengenalan</label><input id="lIc" placeholder="900101-10-5566">\
      <label>E-mel (untuk pemberitahuan)</label><input id="lEmel" type="email" placeholder="nama@contoh.com">\
    </div>\
    <div id="medanPegawai" hidden>\
      <label>Pegawai</label><select id="lPegawai"></select>\
      <label>Kod akses</label><input id="lKod" type="password" placeholder="6 digit" autocomplete="off">\
      ' + (Api.modSheet ? '' : '<div class="muted">Mod demo: kod akses tidak diperlukan.</div>') + '\
    </div>\
    <div class="actions"><button id="btnMasuk">Masuk</button></div>\
  </div>';

  var sel = document.getElementById('peranan');
  var selP = document.getElementById('lPegawai');
  function segar() {
    var p = sel.value;
    document.getElementById('medanPemohon').hidden = p !== 'pemohon';
    document.getElementById('medanPegawai').hidden = p === 'pemohon';
    selP.innerHTML = (CFG.pegawai || []).filter(function (x) { return x.peranan === p; })
      .map(function (x) { return '<option value="' + esc(x.id) + '">' + esc(x.nama) + ' (' + esc(x.id) + ')</option>'; })
      .join('');
  }
  sel.onchange = segar; segar();

  document.getElementById('btnMasuk').onclick = function () {
    var p = sel.value, data;
    if (p === 'pemohon') {
      data = { peranan: 'pemohon', nama: document.getElementById('lNama').value.trim(),
               ic: document.getElementById('lIc').value.trim(),
               emel: document.getElementById('lEmel').value.trim() };
      if (!data.nama || !data.ic) return alert('Sila isi nama dan nombor kad pengenalan.');
    } else {
      data = { peranan: p, pegawaiId: selP.value, kod: document.getElementById('lKod').value.trim() };
      if (Api.modSheet && !data.kod) return alert('Sila masukkan kod akses.');
    }
    memuatkan('Mengesahkan…');
    Api.panggil('login', data).then(function (r) {
      if (!r.ok) { mesejSeterusnya = { teks: r.ralat, jenis: 'err' }; return render(); }
      setSesi(r.sesi);
      go('senarai');
    });
  };
}

/* ---------- senarai ---------- */
function renderSenarai() {
  memuatkan();
  Api.panggil('senarai').then(function (r) {
    if (!r.ok) { if (kendaliRalat(r)) return; el.innerHTML = '<div class="card"><div class="notice err">' + esc(r.ralat) + '</div></div>'; return; }
    var list = r.senarai || [];
    var kira = function (s) { return list.filter(function (a) { return a.status === s; }).length; };

    var statHtml = sesi.peranan === 'pemohon' ? '' :
      '<div class="stats">' +
      '<div class="stat"><div class="n">' + list.length + '</div><div class="l">Jumlah</div></div>' +
      '<div class="stat"><div class="n">' + (kira('BARU') + kira('SEMAKAN')) + '</div><div class="l">Dalam semakan</div></div>' +
      '<div class="stat"><div class="n">' + kira('KELULUSAN') + '</div><div class="l">Menunggu kelulusan</div></div>' +
      '<div class="stat"><div class="n">' + list.filter(function (a) {
        return ['BARU', 'SEMAKAN', 'KELULUSAN'].indexOf(a.status) >= 0 && a.dueAt && bakiHari(a.dueAt) < 0;
      }).length + '</div><div class="l">Lewat SLA</div></div>' +
      '<div class="stat"><div class="n">' + kira('LULUS') + '</div><div class="l">Lulus</div></div></div>';

    var tindakan = sesi.peranan === 'pemohon'
      ? '<div class="actions"><button id="btnBaru">Permohonan Baru</button></div>'
      : (sesi.peranan === 'auditor' ? '<div class="actions"><button class="ghost" id="btnCsv">Muat Turun CSV</button></div>' : '');

    var baris = list.map(function (a) {
      return '<tr class="clickable" data-id="' + esc(a.id) + '">' +
        '<td class="ref">' + esc(a.ref) + '</td>' +
        (sesi.peranan === 'pemohon' ? '' : '<td>' + esc(a.pemohon.nama) + '<div class="muted">' + esc(a.pemohon.ic) + '</div></td>') +
        '<td>' + esc(a.butiran.jenis) + '</td>' +
        '<td><span class="badge ' + stat(a.status).cls + '">' + stat(a.status).label + '</span><div>' + slaHtml(a) + '</div></td>' +
        '<td>' + tarikh(a.dihantarPada) + '</td></tr>';
    }).join('');

    var tajuk = { pemohon: 'Permohonan Saya', penyemak: 'Tugasan Semakan',
                  pelulus: 'Permohonan Untuk Kelulusan', auditor: 'Semua Permohonan' }[sesi.peranan];

    el.innerHTML = banner() + mesejHtml() + statHtml +
      '<div class="card"><h2>' + tajuk + '</h2>' + tindakan +
      (list.length ? '<table><thead><tr><th>No. Rujukan</th>' +
        (sesi.peranan === 'pemohon' ? '' : '<th>Pemohon</th>') +
        '<th>Jenis Bantuan</th><th>Status</th><th>Tarikh</th></tr></thead><tbody>' + baris + '</tbody></table>'
        : '<p class="muted">Tiada rekod.</p>') + '</div>' + notisHtml(r.notis);

    Array.prototype.forEach.call(el.querySelectorAll('tr.clickable'), function (tr) {
      tr.onclick = function () { go('butiran', tr.dataset.id); };
    });
    var b1 = document.getElementById('btnBaru');
    if (b1) b1.onclick = function () { go('borang'); };
    var b2 = document.getElementById('btnCsv');
    if (b2) b2.onclick = function () { muatTurunCsv(r.csv); };
  });
}

function notisHtml(notis) {
  if (!notis || !notis.length) return '';
  return '<div class="card"><h2>Pemberitahuan</h2><ul class="timeline">' +
    notis.map(function (n) {
      return '<li><div class="ts">' + tarikh(n.ts, true) + '</div>' + esc(n.mesej) + '</li>';
    }).join('') + '</ul>' +
    (Api.modSheet ? '<p class="muted">Pemberitahuan e-mel turut dihantar oleh pelayan.</p>'
                  : '<p class="muted">Dalam sistem sebenar, mesej ini juga dihantar melalui e-mel.</p>') +
    '</div>';
}

function muatTurunCsv(csv) {
  if (!csv) return alert('Tiada data untuk dieksport.');
  var blob = new Blob(['﻿' + csv], { type: 'text/csv;charset=utf-8' });
  var url = URL.createObjectURL(blob);
  var a = document.createElement('a');
  a.href = url;
  a.download = 'permohonan-bantuan-' + new Date().toISOString().slice(0, 10) + '.csv';
  a.click();
  URL.revokeObjectURL(url);
}

/* ---------- borang permohonan / pembetulan ---------- */
function renderBorang() {
  if (!view.id) return lukisBorang(null);
  memuatkan();
  Api.panggil('butiran', { id: view.id }).then(function (r) {
    if (!r.ok) { if (kendaliRalat(r)) return; mesejSeterusnya = { teks: r.ralat, jenis: 'err' }; return go('senarai'); }
    lukisBorang(r.permohonan);
  });
}

function lukisBorang(app) {
  var pembetulan = !!app;
  var p = app ? app.pemohon : { nama: sesi.nama, ic: sesi.ic, tel: '', emel: sesi.emel || '', alamat: '' };
  var b = app ? app.butiran : { jenis: CFG.jenisBantuan[0], pendapatan: '', tanggungan: '', sebab: '' };

  el.innerHTML = banner() + mesejHtml() + '\
  <div class="card">\
    <h2>' + (pembetulan ? 'Pembetulan Permohonan ' + esc(app.ref) : 'Borang Permohonan Bantuan') + '</h2>' +
    (pembetulan ? '<div class="notice"><strong>Catatan pegawai penyemak:</strong><br>' +
      esc(app.catatanPembetulan || '-') + '<br><br>Tarikh akhir hantar semula: <strong>' +
      tarikh(app.deadlinePemohon) + '</strong> &middot; Pusingan ' + app.pusinganPembetulan +
      ' daripada ' + CFG.hadPusinganPembetulan + '</div>' : '') + '\
    <h3>Maklumat Pemohon</h3>\
    <div class="row">\
      <div><label>Nama penuh *</label><input id="fNama" value="' + esc(p.nama) + '"></div>\
      <div><label>No. Kad Pengenalan *</label><input id="fIc" value="' + esc(p.ic) + '" ' + (pembetulan ? 'readonly' : '') + '></div>\
    </div>\
    <div class="row">\
      <div><label>No. telefon *</label><input id="fTel" value="' + esc(p.tel) + '" placeholder="012-3456789"></div>\
      <div><label>E-mel</label><input id="fEmel" type="email" value="' + esc(p.emel) + '"></div>\
    </div>\
    <label>Alamat surat-menyurat *</label><textarea id="fAlamat">' + esc(p.alamat) + '</textarea>\
    <h3>Butiran Bantuan</h3>\
    <label>Jenis bantuan *</label>\
    <select id="fJenis">' + CFG.jenisBantuan.map(function (j) {
      return '<option ' + (j === b.jenis ? 'selected' : '') + '>' + esc(j) + '</option>';
    }).join('') + '</select>\
    <div class="row">\
      <div><label>Pendapatan kasar sebulan (RM) *</label><input id="fPendapatan" type="number" min="0" step="1" value="' + esc(b.pendapatan) + '"></div>\
      <div><label>Bilangan tanggungan *</label><input id="fTanggungan" type="number" min="0" step="1" value="' + esc(b.tanggungan) + '"></div>\
    </div>\
    <label>Sebab permohonan *</label><textarea id="fSebab">' + esc(b.sebab) + '</textarea>\
    <h3>Dokumen Sokongan</h3>\
    <p class="muted">Had saiz ' + CFG.maxSaizFailMB + 'MB setiap fail.' +
      (Api.modSheet ? ' Fail disimpan dalam Google Drive agensi.' : ' Mod demo: nama fail sahaja direkodkan.') + '</p>' +
    CFG.dokumenWajib.map(function (d, i) {
      var sedia = app && app.dokumen && app.dokumen.filter(function (x) { return x.jenis === d; })
        .sort(function (x, y) { return y.versi - x.versi; })[0];
      return '<label>' + esc(d) + ' *</label><input type="file" id="fDok' + i + '">' +
        (sedia ? '<div class="muted">Sedia ada: ' + esc(sedia.nama) + ' (versi ' + sedia.versi +
          ') — biar kosong jika tiada perubahan</div>' : '');
    }).join('') + '\
    <div class="actions">\
      <button id="btnHantar">' + (pembetulan ? 'Hantar Semula' : 'Hantar Permohonan') + '</button>\
      <button class="ghost" id="btnBatal">Kembali</button>\
    </div>\
  </div>';

  document.getElementById('btnBatal').onclick = function () { go(app ? 'butiran' : 'senarai', app ? app.id : null); };
  document.getElementById('btnHantar').onclick = function () { hantarBorang(app); };
}

function hantarBorang(app) {
  var v = function (id) { return (document.getElementById(id).value || '').trim(); };
  var pemohon = { nama: v('fNama'), ic: v('fIc'), tel: v('fTel'), emel: v('fEmel'), alamat: v('fAlamat') };
  var butiran = { jenis: v('fJenis'), pendapatan: v('fPendapatan'), tanggungan: v('fTanggungan'), sebab: v('fSebab') };

  var btn = document.getElementById('btnHantar');
  btn.disabled = true;
  btn.textContent = 'Menghantar…';

  Promise.all(CFG.dokumenWajib.map(function (d, i) {
    return Api.bacaFail(document.getElementById('fDok' + i));
  })).then(function (fail) {
    var aksi = app ? 'pembetulan' : 'hantar';
    var data = { pemohon: pemohon, butiran: butiran, fail: fail };
    if (app) data.id = app.id;
    return Api.panggil(aksi, data);
  }).then(function (r) {
    if (!r.ok) {
      if (kendaliRalat(r)) return;
      btn.disabled = false;
      btn.textContent = app ? 'Hantar Semula' : 'Hantar Permohonan';
      alert(r.ralat);
      return;
    }
    mesejSeterusnya = { teks: r.mesej, jenis: 'ok' };
    go('butiran', app ? app.id : r.id);
  }).catch(function (e) {
    btn.disabled = false;
    btn.textContent = app ? 'Hantar Semula' : 'Hantar Permohonan';
    alert(e.message);
  });
}

/* ---------- butiran permohonan ---------- */
function renderButiran() {
  memuatkan();
  Api.panggil('butiran', { id: view.id }).then(function (r) {
    if (!r.ok) {
      if (kendaliRalat(r)) return;
      el.innerHTML = '<div class="card"><div class="notice err">' + esc(r.ralat) + '</div>' +
        '<div class="actions"><button class="ghost" id="bk">Kembali</button></div></div>';
      document.getElementById('bk').onclick = function () { go('senarai'); };
      return;
    }
    lukisButiran(r.permohonan);
  });
}

function lukisButiran(app) {
  var dok = (app.dokumen || []).slice().sort(function (a, b) {
    return a.jenis === b.jenis ? b.versi - a.versi : String(a.jenis).localeCompare(String(b.jenis));
  });

  el.innerHTML = banner() + mesejHtml() + '\
  <div class="card">\
    <h2><span class="ref">' + esc(app.ref) + '</span> &middot; <span class="badge ' + stat(app.status).cls + '">' +
      stat(app.status).label + '</span> ' + slaHtml(app) + '</h2>\
    <div class="row">\
      <div><strong>Pemohon</strong><div>' + esc(app.pemohon.nama) + '</div><div class="muted">' + esc(app.pemohon.ic) + '</div></div>\
      <div><strong>Hubungi</strong><div>' + esc(app.pemohon.tel) + '</div><div class="muted">' + esc(app.pemohon.emel || '-') + '</div></div>\
      <div><strong>Jenis bantuan</strong><div>' + esc(app.butiran.jenis) + '</div></div>\
      <div><strong>Pendapatan / tanggungan</strong><div>' + rm(app.butiran.pendapatan) + ' &middot; ' + esc(app.butiran.tanggungan) + ' orang</div></div>\
    </div>\
    <h3>Alamat</h3><div>' + esc(app.pemohon.alamat) + '</div>\
    <h3>Sebab permohonan</h3><div>' + esc(app.butiran.sebab) + '</div>\
    <h3>Dokumen</h3>\
    <ul class="doclist">' + dok.map(function (d) {
      var nama = d.fileUrl
        ? '<a href="' + esc(d.fileUrl) + '" target="_blank" rel="noopener">' + esc(d.nama) + '</a>'
        : esc(d.nama);
      return '<li><span>' + esc(d.jenis) + '<div class="muted">' + nama + '</div></span>' +
        '<span class="v">versi ' + d.versi + ' &middot; ' + tarikh(d.pada) + '</span></li>';
    }).join('') + '</ul>\
    <h3>Pengendalian</h3>\
    <div class="row">\
      <div><strong>Penyemak</strong><div>' + esc(namaPegawai(app.penyemakId)) + '</div></div>\
      <div><strong>Pelulus</strong><div>' + esc(app.pelulusId ? namaPegawai(app.pelulusId) : '-') + '</div></div>\
      <div><strong>Pusingan pembetulan</strong><div>' + app.pusinganPembetulan + ' / ' + CFG.hadPusinganPembetulan + '</div></div>\
    </div>' +
    (app.keputusan ? '<h3>Keputusan</h3><div>' + (app.keputusan.status === 'LULUS'
        ? 'Lulus — jumlah diluluskan <strong>' + rm(app.keputusan.jumlah) + '</strong>' +
          (app.keputusan.tempoh ? ' untuk ' + esc(app.keputusan.tempoh) : '')
        : 'Tidak lulus') + '</div>' +
      '<div class="muted">Sebab/ulasan: ' + esc(app.keputusan.sebab || '-') + '</div>' +
      '<div class="muted">Diputuskan oleh ' + esc(namaPegawai(app.keputusan.oleh)) + ' pada ' +
      tarikh(app.keputusan.pada, true) + '</div>' : '') + '\
  </div>' + panelTindakan(app) + '\
  <div class="card">\
    <h2>Jejak Audit</h2>\
    <ul class="timeline">' + (app.audit || []).slice().reverse().map(function (a) {
      return '<li><div class="ts">' + tarikh(a.ts, true) + ' &middot; ' + esc(a.pelakuNama) + ' (' + esc(a.peranan) + ')</div>' +
        '<strong>' + esc(a.tindakan) + '</strong>' + (a.butiran ? ' — ' + esc(a.butiran) : '') + '</li>';
    }).join('') + '</ul>\
    <p class="muted">Rekod audit hanya boleh ditambah, tidak boleh diubah atau dibuang.</p>\
  </div>\
  <div class="actions"><button class="ghost" id="bkList">Kembali ke senarai</button></div>';

  document.getElementById('bkList').onclick = function () { go('senarai'); };
  pasangTindakan(app);
}

function panelTindakan(app) {
  if (sesi.peranan === 'pemohon') {
    var h = '';
    if (app.status === 'PEMBETULAN') {
      h += '<div class="card"><h2>Tindakan Anda</h2>' +
        '<div class="notice"><strong>Catatan penyemak:</strong><br>' + esc(app.catatanPembetulan) + '</div>' +
        '<p class="muted">Tarikh akhir hantar semula: <strong>' + tarikh(app.deadlinePemohon) + '</strong></p>' +
        '<div class="actions"><button id="aBetul">Buat Pembetulan</button></div></div>';
    }
    if (['BARU', 'SEMAKAN', 'PEMBETULAN', 'KELULUSAN'].indexOf(app.status) >= 0) {
      h += '<div class="card"><h2>Tarik Balik</h2>' +
        '<p class="muted">Anda boleh menarik balik permohonan selagi keputusan belum dibuat.</p>' +
        '<div class="actions"><button class="danger" id="aTarik">Tarik Balik Permohonan</button></div></div>';
    }
    return h;
  }

  if (sesi.peranan === 'penyemak' && ['BARU', 'SEMAKAN'].indexOf(app.status) >= 0) {
    var hadPenuh = app.pusinganPembetulan >= CFG.hadPusinganPembetulan;
    return '<div class="card"><h2>Semakan</h2><div class="checklist">' +
      CFG.checklistSemakan.map(function (c, i) {
        return '<label><input type="checkbox" class="cl" data-i="' + i + '" ' +
          ((app.checklist || []).indexOf(i) >= 0 ? 'checked' : '') + '><span>' + esc(c) + '</span></label>';
      }).join('') + '</div>' +
      '<label>Catatan semakan</label><textarea id="sCatatan">' + esc(app.catatanPembetulan || '') + '</textarea>' +
      (hadPenuh ? '<div class="notice">Had ' + CFG.hadPusinganPembetulan +
        ' pusingan pembetulan telah dicapai. Permohonan perlu dibawa ke pelulus untuk keputusan.</div>' : '') +
      '<div class="actions">' +
      '<button class="ok" id="aLulusSemak">Lengkap — Hantar ke Pelulus</button>' +
      '<button class="ghost" id="aPembetulan" ' + (hadPenuh ? 'disabled' : '') + '>Kembalikan untuk Pembetulan</button>' +
      '<button class="ghost" id="aSimpan">Simpan Catatan</button></div></div>';
  }

  if (sesi.peranan === 'pelulus' && app.status === 'KELULUSAN') {
    return '<div class="card"><h2>Keputusan</h2><div class="row">' +
      '<div><label>Jumlah diluluskan (RM)</label><input id="kJumlah" type="number" min="0" step="10" value="300"></div>' +
      '<div><label>Tempoh bantuan</label><select id="kTempoh">' +
      '<option>Sekali sahaja</option><option>3 bulan</option><option>6 bulan</option><option>12 bulan</option>' +
      '</select></div></div>' +
      '<label>Ulasan / sebab keputusan *</label><textarea id="kSebab"></textarea>' +
      '<div class="actions"><button class="ok" id="aLulus">Lulus</button>' +
      '<button class="danger" id="aTolak">Tidak Lulus</button>' +
      '<button class="ghost" id="aPulang">Pulangkan kepada Penyemak</button></div></div>';
  }
  return '';
}

function pasangTindakan(app) {
  var on = function (id, fn) { var b = document.getElementById(id); if (b) b.onclick = fn; };
  var hantar = function (aksi, data, teksButang, btnId) {
    var btn = document.getElementById(btnId);
    if (btn) { btn.disabled = true; btn.textContent = 'Memproses…'; }
    data.id = app.id;
    Api.panggil(aksi, data).then(function (r) {
      if (!r.ok) {
        if (kendaliRalat(r)) return;
        if (btn) { btn.disabled = false; btn.textContent = teksButang; }
        return alert(r.ralat);
      }
      mesejSeterusnya = { teks: r.mesej, jenis: 'ok' };
      go('senarai');
    });
  };
  var ambilChecklist = function () {
    return Array.prototype.slice.call(document.querySelectorAll('input.cl'))
      .filter(function (c) { return c.checked; })
      .map(function (c) { return Number(c.dataset.i); });
  };

  on('aBetul', function () { go('borang', app.id); });

  on('aTarik', function () {
    if (!confirm('Tarik balik permohonan ' + app.ref + '? Tindakan ini tidak boleh dibatalkan.')) return;
    hantar('tarikBalik', {}, 'Tarik Balik Permohonan', 'aTarik');
  });

  on('aSimpan', function () {
    hantar('simpanCatatan', { checklist: ambilChecklist(), catatan: document.getElementById('sCatatan').value.trim() },
      'Simpan Catatan', 'aSimpan');
  });

  on('aPembetulan', function () {
    var catatan = document.getElementById('sCatatan').value.trim();
    if (!catatan) return alert('Catatan wajib diisi — pemohon perlu tahu apa yang perlu dibetulkan.');
    hantar('kembaliPembetulan', { checklist: ambilChecklist(), catatan: catatan },
      'Kembalikan untuk Pembetulan', 'aPembetulan');
  });

  on('aLulusSemak', function () {
    var cl = ambilChecklist();
    if (cl.length < CFG.checklistSemakan.length &&
        !confirm('Checklist belum lengkap sepenuhnya. Teruskan hantar ke pelulus?')) return;
    hantar('hantarKelulusan', { checklist: cl, catatan: document.getElementById('sCatatan').value.trim() },
      'Lengkap — Hantar ke Pelulus', 'aLulusSemak');
  });

  var keputusan = function (lulus) {
    var sebab = document.getElementById('kSebab').value.trim();
    if (!sebab) return alert('Ulasan/sebab keputusan wajib diisi untuk tujuan audit.');
    var jumlah = lulus ? Number(document.getElementById('kJumlah').value || 0) : 0;
    if (lulus && !(jumlah > 0)) return alert('Jumlah diluluskan perlu lebih daripada sifar.');
    if (!confirm((lulus ? 'Luluskan' : 'Tolak') + ' permohonan ' + app.ref + '? Keputusan ini kekal dalam rekod audit.')) return;
    hantar('keputusan', { lulus: lulus, jumlah: jumlah, tempoh: lulus ? document.getElementById('kTempoh').value : '', sebab: sebab },
      lulus ? 'Lulus' : 'Tidak Lulus', lulus ? 'aLulus' : 'aTolak');
  };
  on('aLulus', function () { keputusan(true); });
  on('aTolak', function () { keputusan(false); });

  on('aPulang', function () {
    var sebab = document.getElementById('kSebab').value.trim();
    if (!sebab) return alert('Nyatakan sebab pemulangan kepada penyemak.');
    hantar('pulangPenyemak', { sebab: sebab }, 'Pulangkan kepada Penyemak', 'aPulang');
  });
}

/* ---------- mula ---------- */
memuatkan();
Api.muatKonfig().then(render, render);
