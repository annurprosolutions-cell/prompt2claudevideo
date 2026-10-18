/* Lapisan API: hantar ke Apps Script bila API_URL diisi,
   jika tidak jalankan enjin demo tempatan. */
var Api = (function () {
  var modSheet = typeof API_URL === 'string' && API_URL.trim().length > 0;
  var token = null;
  try { token = sessionStorage.getItem('sbantuan.token') || null; } catch (e) {}

  function setToken(t) {
    token = t;
    try { t ? sessionStorage.setItem('sbantuan.token', t) : sessionStorage.removeItem('sbantuan.token'); }
    catch (e) {}
  }

  function panggil(aksi, data) {
    var req = { aksi: aksi };
    if (data) Object.keys(data).forEach(function (k) { req[k] = data[k]; });
    if (token) req.token = token;

    if (!modSheet) {
      return new Promise(function (res) { setTimeout(function () { res(Demo.kendali(req)); }, 60); });
    }
    // Content-Type text/plain mengelak preflight OPTIONS yang tidak disokong Apps Script.
    return fetch(API_URL, {
      method: 'POST',
      headers: { 'Content-Type': 'text/plain;charset=utf-8' },
      body: JSON.stringify(req),
      redirect: 'follow'
    }).then(function (r) { return r.json(); })
      .catch(function (e) {
        return { ok: false, ralat: 'Gagal hubungi pelayan: ' + e.message +
          '. Pastikan URL Web App betul dan akses ditetapkan kepada "Anyone".' };
      });
  }

  /** Baca fail jadi base64 (mod Sheet) atau metadata sahaja (mod demo). */
  function bacaFail(input) {
    var f = input && input.files && input.files[0];
    if (!f) return Promise.resolve(null);
    if (f.size > CFG.maxSaizFailMB * 1024 * 1024) {
      return Promise.reject(new Error('Fail "' + f.name + '" melebihi ' + CFG.maxSaizFailMB + 'MB.'));
    }
    if (!modSheet) return Promise.resolve({ nama: f.name, saiz: f.size });
    return new Promise(function (res, rej) {
      var fr = new FileReader();
      fr.onload = function () {
        res({ nama: f.name, saiz: f.size, jenisMime: f.type || 'application/octet-stream',
              data: String(fr.result).split(',')[1] });
      };
      fr.onerror = function () { rej(new Error('Gagal baca fail ' + f.name)); };
      fr.readAsDataURL(f);
    });
  }

  /** Ambil tetapan sebenar dari pelayan (jenis bantuan, pegawai, checklist). */
  function muatKonfig() {
    if (!modSheet) return Promise.resolve();
    return panggil('konfig').then(function (r) {
      if (r && r.ok && r.cfg) {
        Object.keys(r.cfg).forEach(function (k) { CFG[k] = r.cfg[k]; });
      }
    });
  }

  return { panggil: panggil, bacaFail: bacaFail, muatKonfig: muatKonfig,
           setToken: setToken, modSheet: modSheet };
})();
