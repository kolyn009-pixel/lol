"""Secure PDF storage and text extraction for the teaching library.

Only teacher-authenticated API code should call this module. PDFs are stored
outside the public web root with random names. Extraction prefers pypdf/PyPDF2
and falls back to the system `pdftotext` binary. Scanned PDFs with no text are
reported as OCR_REQUIRED rather than silently producing broken tasks.
"""
from pathlib import Path
import os
import secrets
import subprocess

MAX_PDF_BYTES=int(os.getenv('ADELIA_MAX_PDF_BYTES',str(40*1024*1024)))
STORAGE_ROOT=Path(os.getenv('ADELIA_STORAGE_ROOT','/opt/tutorbot/storage')).resolve()
PDF_ROOT=(STORAGE_ROOT/'materials').resolve()


def _safe_original(name):
    name=Path(str(name or 'collection.pdf')).name.replace('\x00','').strip()
    return name[:180] or 'collection.pdf'


def validate_pdf(data,filename=None):
    if not isinstance(data,(bytes,bytearray)):raise ValueError('invalid_file')
    if not data:raise ValueError('empty_file')
    if len(data)>MAX_PDF_BYTES:raise ValueError('file_too_large')
    if not bytes(data[:5])==b'%PDF-':raise ValueError('not_pdf')
    name=_safe_original(filename)
    if not name.lower().endswith('.pdf'):raise ValueError('not_pdf')
    return name


def save_pdf(data,filename=None):
    name=validate_pdf(data,filename);PDF_ROOT.mkdir(parents=True,exist_ok=True)
    stored=secrets.token_hex(24)+'.pdf';path=(PDF_ROOT/stored).resolve()
    if PDF_ROOT not in path.parents:raise ValueError('invalid_storage_path')
    tmp=path.with_suffix('.tmp')
    with open(tmp,'wb') as f:
        f.write(data);f.flush();os.fsync(f.fileno())
    os.replace(tmp,path);os.chmod(path,0o640)
    return {'path':str(path),'original_filename':name,'size_bytes':len(data),'mime_type':'application/pdf'}


def _extract_pypdf(path):
    reader_cls=None
    try:
        from pypdf import PdfReader as reader_cls
    except Exception:
        try:
            from PyPDF2 import PdfReader as reader_cls
        except Exception:
            return None
    reader=reader_cls(str(path));pages=[]
    for i,p in enumerate(reader.pages,1):
        text=(p.extract_text() or '').strip();pages.append((i,text))
    return pages


def _extract_pdftotext(path):
    try:
        cp=subprocess.run(['pdftotext','-layout',str(path),'-'],capture_output=True,text=True,timeout=90,check=True)
    except Exception:
        return None
    raw=cp.stdout or ''
    chunks=raw.split('\f')
    return [(i+1,x.strip()) for i,x in enumerate(chunks) if x.strip()]


def extract_pdf_text(path):
    path=Path(path).resolve()
    if not path.exists():raise ValueError('file_not_found')
    pages=_extract_pypdf(path);method='PYPDF'
    if pages is None:
        pages=_extract_pdftotext(path);method='PDFTOTEXT'
    if pages is None:return {'status':'EXTRACTOR_UNAVAILABLE','text':'','pages':0,'method':None}
    text='\n\n'.join(f'[[PAGE {n}]]\n{txt}' for n,txt in pages if txt)
    visible=sum(len(txt.strip()) for _,txt in pages)
    if visible<80:return {'status':'OCR_REQUIRED','text':text,'pages':len(pages),'method':method}
    return {'status':'OK','text':text,'pages':len(pages),'method':method}


def remove_file(path):
    try:
        p=Path(path).resolve()
        if PDF_ROOT in p.parents and p.exists():p.unlink()
    except Exception:
        pass
