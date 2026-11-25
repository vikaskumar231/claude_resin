import os, sys, psycopg
from argon2 import PasswordHasher
email, pw = sys.argv[1], sys.argv[2]
with psycopg.connect(os.environ["DATABASE_URL"]) as c:
    c.execute("INSERT INTO admin_user(email,password_hash) VALUES (%s,%s)", (email, PasswordHasher().hash(pw)))
print("admin created")
