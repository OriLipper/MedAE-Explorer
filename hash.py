import hashlib

password = "root"
hashed = hashlib.sha256(password.encode()).hexdigest()
print(hashed)