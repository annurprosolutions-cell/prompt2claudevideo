/* Sistem Permohonan Bantuan - prototaip client-side.
   Semua data disimpan dalam localStorage. Tiada backend, tiada kos. */

const CFG = {
  prefix: 'BK',                 // Bantuan Kewangan
  slaSemakanHari: 5,            // hari bekerja
  slaKelulusanHari: 3,
  hadPusinganPembetulan: 3,
  tempohPembetulanHari: 14,     // hari kalendar untuk pemohon hantar semula
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
    { id: 'PS01', nama: 'Aminah Yusof',   peranan: 'penyemak' },
    { id: 'PS02', nama: 'Rahim Abdullah', peranan: 'penyemak' },
    { id: 'PL01', nama: 'Dr. Faridah Omar', peranan: 'pelulus' },
    { id: 'AU01', nama: 'Unit Audit Dalam', peranan: 'auditor' }
  ]
};

const STATUS = {
  DRAF:        { label: 'Draf',                    cls: 'b-draf' },
  BARU:        { label: 'Baru Diterima',           cls: 'b-baru' },
  SEMAKAN:     { label: 'Dalam Semakan',           cls: 'b-semakan' },
  PEMBETULAN:  { label: 'Perlu Pembetulan',        cls: 'b-pembetulan' },
  KELULUSAN:   { label: 'Menunggu Kelulusan',      cls: 'b-kelulusan' },
  LULUS:       { label: 'Lulus',                   cls: 'b-lulus' },
  TOLAK:       { label: 'Tidak Lulus',             cls: 'b-tolak' },
  DITARIK:     { label: 'Ditarik Oleh Pemohon',    cls: 'b-tutup' },
  TAMAT:       { label: 'Tutup - Tamat Tempoh',    cls: 'b-tutup' }
};

/* ---------- storage ---------- */
const KEY = 'sbantuan.db.v1';
const SESSKEY = 'sbantuan.sesi.v1';

function blankDb() {
  return { seq: 0, rr: 0, apps: [], notis: [] };
}
let db = load();
function load() {
  try {
    const raw = localStorage.getItem(KEY);
    return raw ? JSON.parse(raw) : blankDb();
  } catch (e) { return blankDb(); }
}
function save() {
  try { localStorage.setItem(KEY, JSON.stringify(db)); }
  catch (e) { alert('Gagal simpan data: ' + e.message); }
}
let sesi = null;
try { sesi = JSON.parse(sessionStorage.getItem(SESSKEY) || 'null'); } catch (e) {}
function setSesi(s) {
  sesi = s;
  try { s ? sessionStorage.setItem(SESSKEY, JSON.stringify(s)) : sessionStorage.removeItem(SESSKEY); }
  catch (e) {}
}

/* ---------- helpers ---------- */
const esc = s => String(s == null ? '' : s)
  .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
  .replace(/"/g, '&quot;').replace(/'/g, '&#39;');

const now = () => new Date().toISOString();

function tarikh(iso, denganMasa) {
  if (!iso) return '-';
  const d = new Date(iso);
  const s = String(d.getDate()).padStart(2, '0') + '/' +
            String(d.getMonth() + 1).padStart(2, '0') + '/' + d.getFullYear();
  if (!denganMasa) return s;
  return s + ' ' + String(d.getHours()).padStart(2, '0') + ':' + String(d.getMinutes()).padStart(2, '0');
}
const rm = n => 'RM ' + Number(n || 0).toLocaleString('en-MY', { minimumFractionDigits: 2, maximumFractionDigits: 2 });

function tambahHariBekerja(dari, hari) {
  const d = new Date(dari);
  let baki = hari;
  while (baki > 0) {
    d.setDate(d.getDate() + 1);
    const h = d.getDay();
    if (h !== 0 && h !== 6) baki--;
  }
  return d.toISOString();
}
function tambahHari(dari, hari) {
  const d = new Date(dari);
  d.setDate(d.getDate() + hari);
  return d.toISOString();
}
function bakiHari(iso) {
  if (!iso) return null;
  return Math.ceil((new Date(iso) - new Date()) / 86400000);
}
function slaHtml(app) {
  if (!['BARU', 'SEMAKAN', 'KELULUSAN'].includes(app.status) || !app.dueAt) return '';
  const b = bakiHari(app.dueAt);
  if (b < 0) return '<span class="sla-late">Lewat ' + Math.abs(b) + ' hari</span>';
  if (b <= 1) return '<span class="sla-warn">Tempoh tamat ' + tarikh(app.dueAt) + '</span>';
  return '<span class="sla-ok">Baki ' + b + ' hari</span>';
}
function nextRef() {
  db.seq += 1;
  return CFG.prefix + '/' + new Date().getFullYear() + '/' + String(db.seq).padStart(5, '0');
}
function penyemakSeterusnya() {
  const list = CFG.pegawai.filter(p => p.peranan === 'penyemak');
  const p = list[db.rr % list.length];
  db.rr += 1;
  return p.id;
}
function namaPegawai(id) {
  const p = CFG.pegawai.find(x => x.id === id);
  return p ? p.nama + ' (' + p.id + ')' : (id || '-');
}

/* ---------- audit (append sahaja) ---------- */
function audit(app, tindakan, butiran) {
  app.audit.push({
    ts: now(),
    pelakuId: sesi ? (sesi.pegawaiId || sesi.ic) : 'SISTEM',
    pelakuNama: sesi ? sesi.nama : 'Sistem',
    peranan: sesi ? sesi.peranan : 'sistem',
    tindakan: tindakan,
    butiran: butiran || ''
  });
}
function notis(app, kepada, mesej) {
  db.notis.push({ ts: now(), ref: app.ref, kepada: kepada, mesej: mesej, dibaca: false });
}

/* ---------- kerja automatik: tutup permohonan tamat tempoh ---------- */
function prosesTamatTempoh() {
  let ubah = false;
  db.apps.forEach(app => {
    if (app.status === 'PEMBETULAN' && app.deadlinePemohon && new Date(app.deadlinePemohon) < new Date()) {
      app.status = 'TAMAT';
      app.dueAt = null;
      const simpan = sesi; sesi = null;
      audit(app, 'TUTUP_AUTO', 'Pemohon tidak hantar pembetulan dalam tempoh ' + CFG.tempohPembetulanHari + ' hari');
      sesi = simpan;
      notis(app, app.pemohon.ic, 'Permohonan ' + app.ref + ' ditutup kerana tiada pembetulan dalam tempoh ditetapkan.');
      ubah = true;
    }
  });
  if (ubah) save();
}

/* ================= UI ================= */
const el = document.getElementById('app');
let view = { nama: 'senarai', id: null, tab: null, msg: null };

function render() {
  prosesTamatTempoh();
  const who = document.getElementById('who');
  const btnOut = document.getElementById('btnLogout');
  if (!sesi) {
    who.textContent = '';
    btnOut.hidden = true;
    return renderLogin();
  }
  who.textContent = sesi.nama + ' — ' + peranLabel(sesi.peranan);
  btnOut.hidden = false;
  if (view.nama === 'butiran') return renderButiran();
  if (view.nama === 'borang') return renderBorang();
  return renderSenarai();
}
function peranLabel(p) {
  return { pemohon: 'Pemohon', penyemak: 'Pegawai Penyemak', pelulus: 'Pegawai Pelulus', auditor: 'Auditor' }[p] || p;
}
function go(nama, id) { view = { nama: nama, id: id || null, tab: view.tab, msg: null }; render(); }
function mesej(m, jenis) { view.msg = { teks: m, jenis: jenis || 'ok' }; }
function msgHtml() {
  if (!view.msg) return '';
  const h = '<div class="notice ' + (view.msg.jenis === 'err' ? 'err' : 'ok') + '">' + esc(view.msg.teks) + '</div>';
  view.msg = null;
  return h;
}

/* ---------- login ---------- */
function renderLogin() {
  el.innerHTML = `
  <div class="card login">
    <h2>Masuk ke sistem</h2>
    <p class="muted">Prototaip: pilih peranan untuk mencuba aliran kerja. Tiada pengesahan sebenar.</p>
    <label>Peranan</label>
    <select id="peranan">
      <option value="pemohon">Pemohon</option>
      <option value="penyemak">Pegawai Penyemak</option>
      <option value="pelulus">Pegawai Pelulus</option>
      <option value="auditor">Auditor (lihat sahaja)</option>
    </select>
    <div id="medanPemohon">
      <label>Nama penuh</label><input id="lNama" placeholder="Siti Nurhaliza binti Ahmad">
      <label>No. Kad Pengenalan</label><input id="lIc" placeholder="900101-10-5566">
    </div>
    <div id="medanPegawai" hidden>
      <label>Pegawai</label><select id="lPegawai"></select>
    </div>
    <div class="actions"><button id="btnMasuk">Masuk</button></div>
  </div>`;

  const sel = document.getElementById('peranan');
  const selP = document.getElementById('lPegawai');
  function segar() {
    const p = sel.value;
    document.getElementById('medanPemohon').hidden = p !== 'pemohon';
    document.getElementById('medanPegawai').hidden = p === 'pemohon';
    selP.innerHTML = CFG.pegawai.filter(x => x.peranan === p)
      .map(x => `<option value="${x.id}">${esc(x.nama)} (${x.id})</option>`).join('');
  }
  sel.onchange = segar; segar();

  document.getElementById('btnMasuk').onclick = () => {
    const p = sel.value;
    if (p === 'pemohon') {
      const nama = document.getElementById('lNama').value.trim();
      const ic = document.getElementById('lIc').value.trim();
      if (!nama || !ic) return alert('Sila isi nama dan nombor kad pengenalan.');
      setSesi({ peranan: 'pemohon', nama: nama, ic: ic });
    } else {
      const id = selP.value;
      const peg = CFG.pegawai.find(x => x.id === id);
      setSesi({ peranan: p, nama: peg.nama, pegawaiId: peg.id });
    }
    go('senarai');
  };
}
document.getElementById('btnLogout').onclick = () => { setSesi(null); go('senarai'); };

/* ---------- senarai / dashboard ---------- */
function appsUntukSesi() {
  if (sesi.peranan === 'pemohon') return db.apps.filter(a => a.pemohon.ic === sesi.ic);
  if (sesi.peranan === 'penyemak') return db.apps.filter(a => a.penyemakId === sesi.pegawaiId);
  if (sesi.peranan === 'pelulus') return db.apps.filter(a => ['KELULUSAN', 'LULUS', 'TOLAK'].includes(a.status));
  return db.apps.slice();
}

function renderSenarai() {
  let list = appsUntukSesi().slice().sort((a, b) => (b.dihantarPada || b.dibukaPada).localeCompare(a.dihantarPada || a.dibukaPada));
  const kira = s => list.filter(a => a.status === s).length;

  const statHtml = sesi.peranan === 'pemohon' ? '' : `
    <div class="stats">
      <div class="stat"><div class="n">${list.length}</div><div class="l">Jumlah</div></div>
      <div class="stat"><div class="n">${kira('BARU') + kira('SEMAKAN')}</div><div class="l">Dalam semakan</div></div>
      <div class="stat"><div class="n">${kira('KELULUSAN')}</div><div class="l">Menunggu kelulusan</div></div>
      <div class="stat"><div class="n">${list.filter(a => ['BARU','SEMAKAN','KELULUSAN'].includes(a.status) && a.dueAt && bakiHari(a.dueAt) < 0).length}</div><div class="l">Lewat SLA</div></div>
      <div class="stat"><div class="n">${kira('LULUS')}</div><div class="l">Lulus</div></div>
    </div>`;

  const tindakan = sesi.peranan === 'pemohon'
    ? '<div class="actions"><button id="btnBaru">Permohonan Baru</button></div>'
    : (sesi.peranan === 'auditor' ? '<div class="actions"><button class="ghost" id="btnCsv">Muat Turun CSV</button></div>' : '');

  const baris = list.map(a => `
    <tr class="clickable" data-id="${a.id}">
      <td class="ref">${esc(a.ref)}</td>
      ${sesi.peranan === 'pemohon' ? '' : '<td>' + esc(a.pemohon.nama) + '<div class="muted">' + esc(a.pemohon.ic) + '</div></td>'}
      <td>${esc(a.butiran.jenis)}</td>
      <td><span class="badge ${STATUS[a.status].cls}">${STATUS[a.status].label}</span><div>${slaHtml(a)}</div></td>
      <td>${tarikh(a.dihantarPada || a.dibukaPada)}</td>
    </tr>`).join('');

  el.innerHTML = msgHtml() + statHtml + `
    <div class="card">
      <h2>${sesi.peranan === 'pemohon' ? 'Permohonan Saya' : sesi.peranan === 'penyemak' ? 'Tugasan Semakan' : sesi.peranan === 'pelulus' ? 'Permohonan Untuk Kelulusan' : 'Semua Permohonan'}</h2>
      ${tindakan}
      ${list.length ? `<table><thead><tr>
        <th>No. Rujukan</th>
        ${sesi.peranan === 'pemohon' ? '' : '<th>Pemohon</th>'}
        <th>Jenis Bantuan</th><th>Status</th><th>Tarikh</th>
      </tr></thead><tbody>${baris}</tbody></table>`
      : '<p class="muted">Tiada rekod.</p>'}
    </div>` + notisHtml();

  el.querySelectorAll('tr.clickable').forEach(tr => tr.onclick = () => go('butiran', tr.dataset.id));
  const b1 = document.getElementById('btnBaru'); if (b1) b1.onclick = () => go('borang');
  const b2 = document.getElementById('btnCsv'); if (b2) b2.onclick = muatTurunCsv;
}

function notisHtml() {
  const kepada = sesi.peranan === 'pemohon' ? sesi.ic : sesi.pegawaiId;
  const n = db.notis.filter(x => x.kepada === kepada).slice(-8).reverse();
  if (!n.length) return '';
  return `<div class="card"><h2>Pemberitahuan</h2><ul class="timeline">` +
    n.map(x => `<li><div class="ts">${tarikh(x.ts, true)}</div>${esc(x.mesej)}</li>`).join('') +
    `</ul><p class="muted">Dalam sistem sebenar, mesej ini juga dihantar melalui e-mel/SMS.</p></div>`;
}

/* ---------- borang permohonan / pembetulan ---------- */
function renderBorang() {
  const app = view.id ? db.apps.find(a => a.id === view.id) : null;
  const pembetulan = !!app;
  const p = app ? app.pemohon : { nama: sesi.nama, ic: sesi.ic, tel: '', emel: '', alamat: '' };
  const b = app ? app.butiran : { jenis: CFG.jenisBantuan[0], pendapatan: '', tanggungan: '', sebab: '' };

  el.innerHTML = msgHtml() + `
  <div class="card">
    <h2>${pembetulan ? 'Pembetulan Permohonan ' + esc(app.ref) : 'Borang Permohonan Bantuan'}</h2>
    ${pembetulan ? `<div class="notice"><strong>Catatan pegawai penyemak:</strong><br>${esc(app.catatanPembetulan || '-')}
      <br><br>Tarikh akhir hantar semula: <strong>${tarikh(app.deadlinePemohon)}</strong> &middot;
      Pusingan ${app.pusinganPembetulan} daripada ${CFG.hadPusinganPembetulan}</div>` : ''}

    <h3>Maklumat Pemohon</h3>
    <div class="row">
      <div><label>Nama penuh *</label><input id="fNama" value="${esc(p.nama)}"></div>
      <div><label>No. Kad Pengenalan *</label><input id="fIc" value="${esc(p.ic)}" ${pembetulan ? 'readonly' : ''}></div>
    </div>
    <div class="row">
      <div><label>No. telefon *</label><input id="fTel" value="${esc(p.tel)}" placeholder="012-3456789"></div>
      <div><label>E-mel</label><input id="fEmel" type="email" value="${esc(p.emel)}"></div>
    </div>
    <label>Alamat surat-menyurat *</label><textarea id="fAlamat">${esc(p.alamat)}</textarea>

    <h3>Butiran Bantuan</h3>
    <label>Jenis bantuan *</label>
    <select id="fJenis">${CFG.jenisBantuan.map(j => `<option ${j === b.jenis ? 'selected' : ''}>${esc(j)}</option>`).join('')}</select>
    <div class="row">
      <div><label>Pendapatan kasar sebulan (RM) *</label><input id="fPendapatan" type="number" min="0" step="1" value="${esc(b.pendapatan)}"></div>
      <div><label>Bilangan tanggungan *</label><input id="fTanggungan" type="number" min="0" step="1" value="${esc(b.tanggungan)}"></div>
    </div>
    <label>Sebab permohonan *</label><textarea id="fSebab">${esc(b.sebab)}</textarea>

    <h3>Dokumen Sokongan</h3>
    <p class="muted">Prototaip: hanya nama fail direkodkan, fail tidak dimuat naik ke mana-mana pelayan.</p>
    ${CFG.dokumenWajib.map((d, i) => `
      <label>${esc(d)} *</label>
      <input type="file" id="fDok${i}">
      ${app && app.dokumen[i] && app.dokumen[i].nama ? `<div class="muted">Sedia ada: ${esc(app.dokumen[i].nama)} (versi ${app.dokumen[i].versi}) — biar kosong jika tiada perubahan</div>` : ''}
    `).join('')}

    <div class="actions">
      <button id="btnHantar">${pembetulan ? 'Hantar Semula' : 'Hantar Permohonan'}</button>
      <button class="ghost" id="btnBatal">Kembali</button>
    </div>
  </div>`;

  document.getElementById('btnBatal').onclick = () => go('senarai');
  document.getElementById('btnHantar').onclick = () => hantarBorang(app);
}

function hantarBorang(app) {
  const v = id => (document.getElementById(id).value || '').trim();
  const pemohon = { nama: v('fNama'), ic: v('fIc'), tel: v('fTel'), emel: v('fEmel'), alamat: v('fAlamat') };
  const butiran = { jenis: v('fJenis'), pendapatan: v('fPendapatan'), tanggungan: v('fTanggungan'), sebab: v('fSebab') };

  const kosong = [];
  if (!pemohon.nama) kosong.push('Nama');
  if (!pemohon.ic) kosong.push('No. KP');
  if (!pemohon.tel) kosong.push('No. telefon');
  if (!pemohon.alamat) kosong.push('Alamat');
  if (butiran.pendapatan === '') kosong.push('Pendapatan');
  if (butiran.tanggungan === '') kosong.push('Bilangan tanggungan');
  if (!butiran.sebab) kosong.push('Sebab permohonan');

  const dokBaru = CFG.dokumenWajib.map((d, i) => {
    const f = document.getElementById('fDok' + i).files[0];
    return f ? { jenis: d, nama: f.name, saiz: f.size } : null;
  });
  CFG.dokumenWajib.forEach((d, i) => {
    const adaLama = app && app.dokumen[i] && app.dokumen[i].nama;
    if (!dokBaru[i] && !adaLama) kosong.push(d);
  });

  if (kosong.length) {
    alert('Maklumat belum lengkap:\n- ' + kosong.join('\n- '));
    return;
  }

  if (!app) {
    const baru = {
      id: 'A' + Date.now() + Math.floor(Math.random() * 1000),
      ref: nextRef(),
      dibukaPada: now(),
      dihantarPada: now(),
      status: 'BARU',
      pemohon: pemohon,
      butiran: butiran,
      dokumen: dokBaru.map(d => ({ jenis: d.jenis, nama: d.nama, saiz: d.saiz, versi: 1, pada: now() })),
      penyemakId: penyemakSeterusnya(),
      pelulusId: null,
      pusinganPembetulan: 0,
      catatanPembetulan: '',
      checklist: [],
      keputusan: null,
      dueAt: tambahHariBekerja(now(), CFG.slaSemakanHari),
      deadlinePemohon: null,
      audit: []
    };
    db.apps.push(baru);
    audit(baru, 'HANTAR_PERMOHONAN', 'Permohonan dihantar oleh pemohon');
    const _s = sesi; sesi = null;
    audit(baru, 'AGIH_TUGASAN', 'Diagih secara automatik kepada ' + namaPegawai(baru.penyemakId));
    sesi = _s;
    notis(baru, baru.pemohon.ic, 'Permohonan anda diterima. No. rujukan: ' + baru.ref);
    notis(baru, baru.penyemakId, 'Tugasan semakan baru: ' + baru.ref + ' (' + baru.butiran.jenis + ')');
    save();
    mesej('Permohonan berjaya dihantar. No. rujukan anda: ' + baru.ref);
    go('butiran', baru.id);
    return;
  }

  // pembetulan
  app.pemohon = pemohon;
  app.butiran = butiran;
  dokBaru.forEach((d, i) => {
    if (!d) return;
    const lama = app.dokumen[i];
    app.dokumen[i] = { jenis: d.jenis, nama: d.nama, saiz: d.saiz, versi: (lama ? lama.versi : 0) + 1, pada: now() };
  });
  app.status = 'SEMAKAN';
  app.catatanPembetulan = '';
  app.deadlinePemohon = null;
  app.dueAt = tambahHariBekerja(now(), CFG.slaSemakanHari);
  audit(app, 'HANTAR_PEMBETULAN', 'Pembetulan pusingan ' + app.pusinganPembetulan + ' dihantar');
  notis(app, app.penyemakId, 'Pembetulan diterima untuk ' + app.ref + '. Sila semak semula.');
  save();
  mesej('Pembetulan berjaya dihantar. Permohonan kembali kepada pegawai penyemak.');
  go('butiran', app.id);
}

/* ---------- butiran permohonan ---------- */
function renderButiran() {
  const app = db.apps.find(a => a.id === view.id);
  if (!app) { go('senarai'); return; }

  const bolehLihat = sesi.peranan === 'auditor' ||
    (sesi.peranan === 'pemohon' && app.pemohon.ic === sesi.ic) ||
    (sesi.peranan === 'penyemak' && app.penyemakId === sesi.pegawaiId) ||
    (sesi.peranan === 'pelulus' && ['KELULUSAN', 'LULUS', 'TOLAK'].includes(app.status));
  if (!bolehLihat) {
    el.innerHTML = '<div class="card"><div class="notice err">Anda tiada kebenaran melihat permohonan ini.</div>' +
      '<div class="actions"><button class="ghost" id="bk">Kembali</button></div></div>';
    document.getElementById('bk').onclick = () => go('senarai');
    return;
  }

  el.innerHTML = msgHtml() + `
  <div class="card">
    <h2><span class="ref">${esc(app.ref)}</span> &middot;
      <span class="badge ${STATUS[app.status].cls}">${STATUS[app.status].label}</span> ${slaHtml(app)}</h2>
    <div class="row">
      <div><strong>Pemohon</strong><div>${esc(app.pemohon.nama)}</div><div class="muted">${esc(app.pemohon.ic)}</div></div>
      <div><strong>Hubungi</strong><div>${esc(app.pemohon.tel)}</div><div class="muted">${esc(app.pemohon.emel || '-')}</div></div>
      <div><strong>Jenis bantuan</strong><div>${esc(app.butiran.jenis)}</div></div>
      <div><strong>Pendapatan / tanggungan</strong><div>${rm(app.butiran.pendapatan)} &middot; ${esc(app.butiran.tanggungan)} orang</div></div>
    </div>
    <h3>Alamat</h3><div>${esc(app.pemohon.alamat)}</div>
    <h3>Sebab permohonan</h3><div>${esc(app.butiran.sebab)}</div>
    <h3>Dokumen</h3>
    <ul class="doclist">${app.dokumen.map(d => `<li><span>${esc(d.jenis)}<div class="muted">${esc(d.nama)}</div></span><span class="v">versi ${d.versi} &middot; ${tarikh(d.pada)}</span></li>`).join('')}</ul>
    <h3>Pengendalian</h3>
    <div class="row">
      <div><strong>Penyemak</strong><div>${esc(namaPegawai(app.penyemakId))}</div></div>
      <div><strong>Pelulus</strong><div>${esc(app.pelulusId ? namaPegawai(app.pelulusId) : '-')}</div></div>
      <div><strong>Pusingan pembetulan</strong><div>${app.pusinganPembetulan} / ${CFG.hadPusinganPembetulan}</div></div>
    </div>
    ${app.keputusan ? `<h3>Keputusan</h3>
      <div>${app.keputusan.status === 'LULUS'
        ? 'Lulus — jumlah diluluskan <strong>' + rm(app.keputusan.jumlah) + '</strong>' + (app.keputusan.tempoh ? ' untuk ' + esc(app.keputusan.tempoh) : '')
        : 'Tidak lulus'}</div>
      <div class="muted">Sebab/ulasan: ${esc(app.keputusan.sebab || '-')}</div>
      <div class="muted">Diputuskan oleh ${esc(namaPegawai(app.keputusan.oleh))} pada ${tarikh(app.keputusan.pada, true)}</div>` : ''}
  </div>
  ${panelTindakan(app)}
  <div class="card">
    <h2>Jejak Audit</h2>
    <ul class="timeline">${app.audit.slice().reverse().map(a => `
      <li><div class="ts">${tarikh(a.ts, true)} &middot; ${esc(a.pelakuNama)} (${esc(a.peranan)})</div>
      <strong>${esc(a.tindakan)}</strong>${a.butiran ? ' — ' + esc(a.butiran) : ''}</li>`).join('')}</ul>
    <p class="muted">Rekod audit hanya boleh ditambah, tidak boleh diubah atau dibuang.</p>
  </div>
  <div class="actions"><button class="ghost" id="bkList">Kembali ke senarai</button></div>`;

  document.getElementById('bkList').onclick = () => go('senarai');
  pasangTindakan(app);
}

function panelTindakan(app) {
  if (sesi.peranan === 'pemohon') {
    let h = '';
    if (app.status === 'PEMBETULAN') {
      h += `<div class="card"><h2>Tindakan Anda</h2>
        <div class="notice"><strong>Catatan penyemak:</strong><br>${esc(app.catatanPembetulan)}</div>
        <p class="muted">Tarikh akhir hantar semula: <strong>${tarikh(app.deadlinePemohon)}</strong></p>
        <div class="actions"><button id="aBetul">Buat Pembetulan</button></div></div>`;
    }
    if (['BARU', 'SEMAKAN', 'PEMBETULAN', 'KELULUSAN'].includes(app.status)) {
      h += `<div class="card"><h2>Tarik Balik</h2>
        <p class="muted">Anda boleh menarik balik permohonan selagi keputusan belum dibuat.</p>
        <div class="actions"><button class="danger" id="aTarik">Tarik Balik Permohonan</button></div></div>`;
    }
    return h;
  }

  if (sesi.peranan === 'penyemak' && ['BARU', 'SEMAKAN'].includes(app.status)) {
    const hadPenuh = app.pusinganPembetulan >= CFG.hadPusinganPembetulan;
    return `<div class="card"><h2>Semakan</h2>
      <div class="checklist">${CFG.checklistSemakan.map((c, i) =>
        `<label><input type="checkbox" class="cl" data-i="${i}" ${app.checklist.includes(i) ? 'checked' : ''}><span>${esc(c)}</span></label>`).join('')}</div>
      <label>Catatan semakan</label><textarea id="sCatatan">${esc(app.catatanPembetulan || '')}</textarea>
      ${hadPenuh ? `<div class="notice">Had ${CFG.hadPusinganPembetulan} pusingan pembetulan telah dicapai. Permohonan perlu dibawa ke pelulus untuk keputusan.</div>` : ''}
      <div class="actions">
        <button class="ok" id="aLulusSemak">Lengkap — Hantar ke Pelulus</button>
        <button class="ghost" id="aPembetulan" ${hadPenuh ? 'disabled' : ''}>Kembalikan untuk Pembetulan</button>
        <button class="ghost" id="aSimpan">Simpan Catatan</button>
      </div></div>`;
  }

  if (sesi.peranan === 'pelulus' && app.status === 'KELULUSAN') {
    return `<div class="card"><h2>Keputusan</h2>
      <div class="row">
        <div><label>Jumlah diluluskan (RM)</label><input id="kJumlah" type="number" min="0" step="10" value="300"></div>
        <div><label>Tempoh bantuan</label><select id="kTempoh">
          <option>Sekali sahaja</option><option>3 bulan</option><option>6 bulan</option><option>12 bulan</option></select></div>
      </div>
      <label>Ulasan / sebab keputusan *</label><textarea id="kSebab"></textarea>
      <div class="actions">
        <button class="ok" id="aLulus">Lulus</button>
        <button class="danger" id="aTolak">Tidak Lulus</button>
        <button class="ghost" id="aPulang">Pulangkan kepada Penyemak</button>
      </div></div>`;
  }
  return '';
}

function pasangTindakan(app) {
  const on = (id, fn) => { const b = document.getElementById(id); if (b) b.onclick = fn; };

  on('aBetul', () => go('borang', app.id));

  on('aTarik', () => {
    if (!confirm('Tarik balik permohonan ' + app.ref + '? Tindakan ini tidak boleh dibatalkan.')) return;
    app.status = 'DITARIK'; app.dueAt = null; app.deadlinePemohon = null;
    audit(app, 'TARIK_BALIK', 'Ditarik balik oleh pemohon');
    if (app.penyemakId) notis(app, app.penyemakId, app.ref + ' ditarik balik oleh pemohon.');
    save(); mesej('Permohonan telah ditarik balik.'); go('senarai');
  });

  const ambilChecklist = () => Array.from(document.querySelectorAll('input.cl'))
    .filter(c => c.checked).map(c => Number(c.dataset.i));

  on('aSimpan', () => {
    app.checklist = ambilChecklist();
    app.catatanPembetulan = document.getElementById('sCatatan').value.trim();
    if (app.status === 'BARU') { app.status = 'SEMAKAN'; audit(app, 'MULA_SEMAKAN', 'Semakan dimulakan'); }
    audit(app, 'SIMPAN_CATATAN', 'Checklist: ' + app.checklist.length + '/' + CFG.checklistSemakan.length);
    save(); mesej('Catatan semakan disimpan.'); render();
  });

  on('aPembetulan', () => {
    const catatan = document.getElementById('sCatatan').value.trim();
    if (!catatan) return alert('Catatan wajib diisi — pemohon perlu tahu apa yang perlu dibetulkan.');
    app.checklist = ambilChecklist();
    app.catatanPembetulan = catatan;
    app.pusinganPembetulan += 1;
    app.status = 'PEMBETULAN';
    app.deadlinePemohon = tambahHari(now(), CFG.tempohPembetulanHari);
    app.dueAt = null;
    audit(app, 'KEMBALI_PEMBETULAN', 'Pusingan ' + app.pusinganPembetulan + ': ' + catatan);
    notis(app, app.pemohon.ic, app.ref + ' dikembalikan untuk pembetulan. Tarikh akhir: ' + tarikh(app.deadlinePemohon));
    save(); mesej('Permohonan dikembalikan kepada pemohon.'); go('senarai');
  });

  on('aLulusSemak', () => {
    app.checklist = ambilChecklist();
    if (app.checklist.length < CFG.checklistSemakan.length &&
        !confirm('Checklist belum lengkap sepenuhnya. Teruskan hantar ke pelulus?')) return;
    const pelulus = CFG.pegawai.find(p => p.peranan === 'pelulus');
    app.catatanPembetulan = document.getElementById('sCatatan').value.trim();
    app.status = 'KELULUSAN';
    app.pelulusId = pelulus.id;
    app.dueAt = tambahHariBekerja(now(), CFG.slaKelulusanHari);
    audit(app, 'HANTAR_KELULUSAN', 'Disyorkan kepada ' + namaPegawai(pelulus.id) +
      (app.catatanPembetulan ? ' — catatan: ' + app.catatanPembetulan : ''));
    notis(app, pelulus.id, 'Permohonan ' + app.ref + ' menunggu keputusan anda.');
    notis(app, app.pemohon.ic, app.ref + ': semakan selesai, menunggu keputusan pelulus.');
    save(); mesej('Permohonan dihantar kepada pegawai pelulus.'); go('senarai');
  });

  const keputusan = (lulus) => {
    const sebab = document.getElementById('kSebab').value.trim();
    if (!sebab) return alert('Ulasan/sebab keputusan wajib diisi untuk tujuan audit.');
    const jumlah = lulus ? Number(document.getElementById('kJumlah').value || 0) : 0;
    const tempoh = lulus ? document.getElementById('kTempoh').value : '';
    if (lulus && jumlah <= 0) return alert('Jumlah diluluskan perlu lebih daripada sifar.');
    if (!confirm((lulus ? 'Luluskan' : 'Tolak') + ' permohonan ' + app.ref + '? Keputusan ini kekal dalam rekod audit.')) return;
    app.status = lulus ? 'LULUS' : 'TOLAK';
    app.dueAt = null;
    app.keputusan = { status: app.status, jumlah: jumlah, tempoh: tempoh, sebab: sebab, oleh: sesi.pegawaiId, pada: now() };
    audit(app, lulus ? 'LULUS' : 'TOLAK', (lulus ? rm(jumlah) + ' / ' + tempoh + ' — ' : '') + sebab);
    notis(app, app.pemohon.ic, app.ref + ': permohonan anda ' + (lulus ? 'DILULUSKAN (' + rm(jumlah) + ')' : 'TIDAK DILULUSKAN') + '.');
    notis(app, app.penyemakId, app.ref + ': keputusan ' + STATUS[app.status].label + ' telah dibuat.');
    save(); mesej('Keputusan direkodkan dan pemohon dimaklumkan.'); go('senarai');
  };
  on('aLulus', () => keputusan(true));
  on('aTolak', () => keputusan(false));

  on('aPulang', () => {
    const sebab = document.getElementById('kSebab').value.trim();
    if (!sebab) return alert('Nyatakan sebab pemulangan kepada penyemak.');
    app.status = 'SEMAKAN';
    app.dueAt = tambahHariBekerja(now(), CFG.slaSemakanHari);
    audit(app, 'PULANG_KE_PENYEMAK', sebab);
    notis(app, app.penyemakId, app.ref + ' dipulangkan oleh pelulus: ' + sebab);
    save(); mesej('Permohonan dipulangkan kepada pegawai penyemak.'); go('senarai');
  });
}

/* ---------- eksport CSV (auditor) ---------- */
function muatTurunCsv() {
  const q = s => '"' + String(s == null ? '' : s).replace(/"/g, '""') + '"';
  const baris = [['No. Rujukan', 'Tarikh Hantar', 'Nama', 'No. KP', 'Jenis Bantuan', 'Pendapatan',
    'Status', 'Penyemak', 'Pelulus', 'Pusingan Pembetulan', 'Jumlah Lulus', 'Sebab Keputusan',
    'Bilangan Rekod Audit'].map(q).join(',')];
  db.apps.forEach(a => baris.push([a.ref, tarikh(a.dihantarPada, true), a.pemohon.nama, a.pemohon.ic,
    a.butiran.jenis, a.butiran.pendapatan, STATUS[a.status].label, namaPegawai(a.penyemakId),
    a.pelulusId ? namaPegawai(a.pelulusId) : '', a.pusinganPembetulan,
    a.keputusan ? a.keputusan.jumlah : '', a.keputusan ? a.keputusan.sebab : '',
    a.audit.length].map(q).join(',')));
  const blob = new Blob(['﻿' + baris.join('\r\n')], { type: 'text/csv;charset=utf-8' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = 'permohonan-bantuan-' + new Date().toISOString().slice(0, 10) + '.csv';
  a.click();
  URL.revokeObjectURL(url);
}

render();
