# Menyiapkan Twitch

*English: [setup-twitch.md](setup-twitch.md)*

StreamBridge mengirim pesan penonton TikTok Anda ke chat Twitch Anda.
Yang dibutuhkan hanya akun Twitch Anda. Anda tidak pernah mengetik password
Twitch di StreamBridge. Persetujuan dilakukan langsung di situs Twitch.

## 1. Login dengan akun Twitch Anda (disarankan)

Secara default, pesan dikirim **atas nama akun channel Anda sendiri**.

1. Di StreamBridge, pilih **Log in with Twitch**.
2. StreamBridge menampilkan kode pendek (misalnya `ABCD-EFGH`) dan membuka
   `twitch.tv/activate` di browser.
3. Pastikan kode di halaman Twitch sama, lalu klik **Authorize**.
4. StreamBridge menampilkan "Logged in as @namaanda". Selesai.

Login ini diingat. Anda hanya perlu login lagi kalau StreamBridge tidak
dipakai selama 30 hari, kalau password Twitch diganti, atau kalau
StreamBridge diputus dari Twitch.

## 2. Memakai akun bot terpisah (lanjutan)

Sebagian streamer lebih suka pesan datang dari akun kedua, misalnya
`namaanda_bot`. Ini opsional.

**Bot wajib menjadi moderator di channel Anda.** StreamBridge mengeceknya
setiap kali Start ditekan, dan Twitch tidak akan dijalankan sebelum bot
menjadi moderator.

1. **Buat akun bot** di Twitch (logout dulu, atau pakai jendela browser
   privat). Beri nama yang jelas, misalnya `namaanda_bot`.
2. **Jadikan moderator** di channel Anda. Pilih salah satu:
   - ketik `/mod namaanda_bot` di chat Twitch Anda sendiri, atau
   - buka **Creator Dashboard → Community → Roles**, klik **Add New**,
     pilih **Moderator**, lalu masukkan nama bot.
3. **Login sebagai bot** di StreamBridge (**Use a separate bot account**).
   ⚠️ Saat halaman Twitch terbuka, pastikan browser itu sedang login
   **sebagai bot**, bukan akun utama Anda. Kalau perlu, buka link-nya di
   jendela privat dan login dengan akun bot di sana.
4. Masukkan **nama channel Anda** (tempat bot akan mengirim pesan).
5. StreamBridge mengecek apakah bot sudah moderator. Kalau belum, akan muncul:
   *"The bot @namaanda_bot is not a moderator of channel namaanda. Type
   /mod namaanda_bot in your Twitch chat, then try again."*

Untuk mengecek daftar moderator sendiri, ketik `/mods` di chat Anda, atau
lihat di Creator Dashboard → Community → Roles.

## Mengatasi masalah

| Yang muncul | Yang perlu dilakukan |
|---|---|
| "Twitch login expired; please log in again" | Login lagi (bagian 1 atau 2). |
| "...is not a moderator of channel..." | Jadikan bot moderator (bagian 2, langkah 2), lalu Start lagi. |
| "Twitch does not allow this account to chat here" | Bot kehilangan status moderator, atau akunnya di-ban/timeout di channel Anda. |
| Sebuah pesan ditolak dengan alasan dari Twitch | AutoMod Twitch atau pengaturan chat Anda memblokir pesan itu. Pesan lain tetap mengalir. |
| Pesan datang terlambat saat chat ramai | Twitch mengizinkan sekitar 100 pesan per 30 detik. StreamBridge tetap di bawah batas itu dan tidak pernah membuang pesan Twitch, jadi sebagian pesan bisa sedikit terlambat. |

## Privasi dan mencabut akses

- Login Twitch Anda hanya disimpan di PC Anda, di **Windows Credential
  Manager**. Login itu tidak pernah ditulis ke file pengaturan atau log
  StreamBridge.
- Untuk mencabut akses StreamBridge sepenuhnya, buka
  [twitch.tv/settings/connections](https://www.twitch.tv/settings/connections)
  lalu klik **Disconnect** di samping StreamBridge.

## Untuk pengembang (command line)

```powershell
.\.venv\Scripts\python.exe tools\cli.py --twitch-login        # akun streamer
.\.venv\Scripts\python.exe tools\cli.py --twitch-login-bot    # akun bot
.\.venv\Scripts\python.exe tools\cli.py --tiktok @username --twitch
.\.venv\Scripts\python.exe tools\cli.py --tiktok @username --twitch --twitch-channel namaanda
.\.venv\Scripts\python.exe tools\cli.py --twitch-logout
```
