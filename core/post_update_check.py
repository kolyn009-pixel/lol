#!/usr/bin/env python3
import os, sys, sqlite3
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import database
from core import diagnostics

def main():
    database.create_tables()
    rows=diagnostics.run_checks(); failed=[r for r in rows if not r[2] and r[1]=='CRITICAL']
    for name,sev,ok,details in rows: print(('OK' if ok else sev),name,details)
    raise SystemExit(1 if failed else 0)
if __name__=='__main__': main()
