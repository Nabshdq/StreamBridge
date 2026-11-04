# Menyiapkan YouTube

*English: [setup-youtube.md](setup-youtube.md)*

StreamBridge mengirim pesan penonton TikTok Anda ke live chat YouTube.
Berbeda dengan Twitch, YouTube butuh **persiapan sekali saja di Google Cloud**.
Gratis dan sekitar 15 menit. Anda membuat "proyek" kecil sendiri, jadi batas
harian YouTube milik Anda dan tidak dibagi dengan orang lain.

> Langkah wizard di dalam aplikasi untuk ini belum dibuat. Sampai selesai,
> pakai panduan ini sebagai acuan apa yang akan ditanyakan wizard. Google
> kadang mengganti nama menu (layar persetujuan kini ada di **Google Auth
> Platform**: Branding, Audience, Data Access, Clients), jadi nama tombol bisa
> sedikit berbeda. Langkah-langkah ini belum diuji dari awal sampai akhir.

## 0. Aktifkan live streaming di channel Anda lebih dulu

Saat pertama kali mengaktifkan live streaming, YouTube bisa memerlukan
**sampai 24 jam**. Channel juga harus terverifikasi dan tidak terkena
pembatasan live dalam 90 hari terakhir. Lakukan ini paling awal:
<https://www.youtube.com/features>

## 1. Buat proyek Google Cloud

1. Buka <https://console.cloud.google.com/> dan masuk dengan akun Google
   pemilik channel YouTube Anda.
2. Klik pemilih proyek di bagian atas, lalu **New project**. Beri nama
   `StreamBridge` dan klik **Create**.

## 2. Aktifkan YouTube Data API

1. Buka **APIs & Services > Library**.
2. Cari **YouTube Data API v3**, buka, lalu klik **Enable**.

## 3. Atur layar persetujuan (consent screen)

1. Buka **Google Auth Platform** (<https://console.cloud.google.com/auth/overview>)
   dan mulai pengaturan. Nama lamanya **APIs & Services > OAuth consent
   screen**.
2. Pilih tipe pengguna **External**.
3. Isi nama aplikasi (`StreamBridge`), email Anda sebagai email dukungan dan
   kontak pengembang. Sisanya kosongkan. Simpan.
4. Di langkah **Scopes**, tambahkan `.../auth/youtube.force-ssl`.
5. Di langkah **Test users**, tambahkan akun Google Anda sendiri.
6. **Penting:** kembali ke halaman consent screen, klik **Publish app**.
   Selama aplikasi berstatus "Testing", Google mengeluarkan login Anda setiap
   **7 hari** sehingga Anda harus login ulang tiap minggu. Setelah
   dipublikasikan, login bertahan.

Saat login, Google mungkin menampilkan **"Google hasn't verified this app"**.
Itu wajar: Anda membuat aplikasinya sendiri dan Anda satu-satunya
penggunanya. Klik **Advanced**, lalu **Go to StreamBridge (unsafe)**. Google
bisa terus menampilkan peringatan ini karena aplikasi belum diverifikasi; untuk
pemakaian pribadi tidak masalah (aplikasi tak terverifikasi dibatasi 100
pengguna).

## 4. Buat file login

1. Buka **Google Auth Platform > Clients** (nama lama: **APIs & Services >
   Credentials**).
2. Klik **Create client**.
3. Application type: **Desktop app**. Name: `StreamBridge`. Klik **Create**.
4. Unduh JSON saat itu juga; secret hanya ditampilkan sekali. Nama filenya `client_secret_....json`.
5. Berikan file ini ke StreamBridge saat diminta. StreamBridge menyalinnya ke
   foldernya sendiri. **Jangan bagikan file ini dan jangan unggah ke mana pun.**

## 5. Login

Pilih **Log in with Google** di StreamBridge. Browser terbuka, Anda
menyetujui akses, lalu login disimpan di Windows Credential Manager.

## Batas harian (kuota)

YouTube memberi tiap proyek **10.000 unit per hari**. Mengirim satu pesan
memakai **20 unit**, jadi paling banyak **500 pesan sehari**. Hitungan
direset tengah malam waktu Pacific (sekitar jam 15.00 WIB, atau 14.00 WIB saat
musim panas AS).

Agar cukup, StreamBridge:

- menggabungkan beberapa chat menjadi **satu** pesan (mode ringkas) dan hanya
  mengirim chat terbaru yang muat dalam 200 karakter;
- secara bawaan mengirim chat dan gift ke YouTube, tetapi tidak follow, like,
  atau share;
- (rencana) menampilkan "YouTube quota: terpakai / 10.000" dan, di atas 90%,
  hanya mengirim gift.

Dengan 500 pesan sehari, LIVE 2 sampai 3 jam hanya cukup jika chat digabung
dalam jendela waktu yang lebih panjang; StreamBridge sedang disetel untuk ini.
Chat yang tidak muat dihitung sebagai "dropped".

## Memakai akun bot terpisah (lanjutan)

Pesan biasanya datang dari channel Anda sendiri. Untuk memakai akun lain,
login dengan akun itu dan tempel **tautan live Anda** (misalnya
`https://www.youtube.com/watch?v=...`) di Pengaturan, karena akun kedua tidak
bisa mencari siaran Anda sendiri.

## Pemecahan masalah

| Pesan | Yang dilakukan |
|---|---|
| "YouTube live chat not found yet" | Live belum mulai, atau live streaming belum aktif (lihat langkah 0). StreamBridge mengecek lagi tiap menit. |
| "YouTube login expired" | Login ulang. Ini terjadi tiap minggu jika aplikasi dibiarkan "Testing" (langkah 3.6). |
| "Daily quota is used up" | Tunggu reset tengah malam Pacific. |
| "This is not a Desktop app client file" | Buat OAuth client dengan tipe **Desktop app** (langkah 4). |
