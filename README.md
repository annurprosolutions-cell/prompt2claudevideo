# Prompt2Claude

Nota digital interaktif untuk webinar **Prompt2Claude** — 17 & 18 Oktober 2026.

**Penceramah:** Ts. Ruzbihan Bakhtiar · Professional Technologist (MBOT)
**Penganjur:** AnnurPro Solutions

## Apa ini

Satu fail HTML yang mengandungi keseluruhan nota webinar dua hari:

- **Hari 1** — kenal Claude, global instruction, connector (Drive, Gmail, Calendar), skills, bina nota digital dan game
- **Hari 2** — Claude Code, GitHub Desktop, empat soalan sebelum bina sistem, bina dashboard, semak keselamatan, publish
- **Sijil** — dijana sebagai PDF terus dalam browser peserta, boleh dimuat turun atau dihantar ke emel

Kemajuan peserta disimpan dalam browser masing-masing. Tiada data dihantar ke mana-mana pelayan kecuali bila peserta tekan butang hantar sijil ke emel.

## Pemilihan UI/UX

Setiap builder prompt (nota, game, dashboard) ada pilihan gaya UI (10 gaya dengan pratonton visual), tema light/dark, dan ciri mesra pengguna. Pilihan terus masuk ke dalam prompt. Hari 1 ada jadual cadangan gaya ikut keadaan, lima peraturan UX, dan prompt semakan UX. Hari 2 guna pilihan yang sama untuk prompt peringkat paparan.

Isian builder disimpan dalam browser, jadi peserta boleh sambung kemudian.

## Kunci

Setiap hari dibuka dengan kunci yang diberi semasa sesi bermula. Kunci ditetapkan dalam `index.html`:

```js
var KEY_D1 = "...";
var KEY_D2 = "...";
```

Kunci ini mengawal aliran kelas sahaja, bukan keselamatan — sesiapa yang membuka kod sumber boleh melihatnya.

## Sijil melalui emel

Butang muat turun PDF berfungsi tanpa sebarang setup.

Butang hantar ke emel memerlukan satu Google Apps Script yang di-deploy sebagai web app. Kod penuh dan langkah deploy ada dalam tab **Survey & Sijil** di dalam nota. Selepas deploy, masukkan URL web app ke dalam `index.html`:

```js
var GAS_URL = "https://script.google.com/macros/s/..../exec";
```

Biarkan kosong kalau mahu guna muat turun sahaja.

## Nota teknikal

- Animasi muncul bila scroll, dan hormati tetapan *reduce motion* pada peranti
- Boleh dikendalikan dengan papan kekunci (tab, accordion, kotak tanda)
- Satu fail HTML, tiada proses build
- Logo dan gambar terbenam sebagai data URI
- jsPDF dimuat dari cdnjs untuk menjana sijil
- Fon Poppins dan Lora dari Google Fonts, jatuh ke Arial dan Georgia bila luar talian

---

© AnnurPro Solutions
