import sqlite3

conn = sqlite3.connect("sms.db")
tables = [r[0] for r in conn.execute("select name from sqlite_master where type='table'")]
print("TABLES:", tables)
print("DEPARTMENTS:", list(conn.execute("select id, code, name, intake from department")))
print("REGISTRATIONS:", list(conn.execute("select id, reference_no, status, full_name from registration")))
print("REG SCHEMA:", list(conn.execute("select sql from sqlite_master where name='registration'")))
