"""Secure PDF storage and text extraction for the teaching library.

Large teaching collections are streamed to disk in chunks instead of being
loaded into RAM. Files stay outside the public web root and are served only
through authenticated API endpoints.
"""
from pathlib import Path
import hashlib
import os
import secrets
import subprocess

MAX_PDF_BYTES=int(os.getenv('ADELIA_MAX_PDF_BYTES',str(250*1024*1024)))
STORAGE_ROOT=Path(os.getenv('ADELIA_STORAGE_ROOT','/opt/tutorbot/storage')).resolve()
PDF_ROOT=(STORAGE_ROOT/'materials').resolve()
CHUNK_SIZE=1024*1024


def _safe_original(name):
    name=Path(str(name or 'collection.pdf')).name.replace('\x00','').strip()
    return name[:180] or 'collection.pdf'


def _validate_name(filename):
    name=_safe_original(filename)
    if not name.lower().endswith('.pdf'):raise ValueError('not_pdf')
    return name


def validate_pdf(data,filename=None):
    if not isinstance(data,(bytes,bytearray)):raise ValueError('invalid_file')
    if not data:raise ValueError('empty_file')
    if len(data)>MAX_PDF_BYTES:raise ValueError('file_too_large')
    if bytes(data[:5])!=b'%PDF-':raise ValueError('not_pdf')
    return _validate_name(filename)


def _target():
    PDF_ROOT.mkdir(parents=True,exist_ok=True)
    stored=secrets.token_hex(24)+'.pdf';path=(PDF_ROOT/stored).resolve()
    if PDF_ROOT not in path.parents:raise ValueError('invalid_storage_path')
    return path


def save_pdf(data,filename=None):
    name=validate_pdf(data,filename);path=_target();tmp=path.with_suffix('.tmp');digest=hashlib.sha256(bytes(data)).hexdigest()
    with open(tmp,'wb') as f:
        f.write(data);f.flush();os.fsync(f.fileno())
    os.replace(tmp,path);os.chmod(path,0o640)
    return {'path':str(path),'original_filename':name,'size_bytes':len(data),'mime_type':'application/pdf','sha256':digest}


def save_pdf_stream(stream,filename=None):
    """Persist a file-like PDF using bounded memory."""
    if stream is None or not hasattr(stream,'read'):raise ValueError('invalid_file')
    name=_validate_name(filename);path=_target();tmp=path.with_suffix('.tmp');total=0;digest=hashlib.sha256();first=b''
    try:
        with open(tmp,'wb') as out:
            while True:
                chunk=stream.read(CHUNK_SIZE)
                if not chunk:break
                if not isinstance(chunk,(bytes,bytearray)):raise ValueError('invalid_file')
                if not first:first=bytes(chunk[:5])
                total+=len(chunk)
                if total>MAX_PDF_BYTES:raise ValueError('file_too_large')
                digest.update(chunk);out.write(chunk)
            if total<=0:raise ValueError('empty_file')
            if first!=b'%PDF-':raise ValueError('not_pdf')
            out.flush();os.fsync(out.fileno())
        os.replace(tmp,path);os.chmod(path,0o640)
        return {'path':str(path),'original_filename':name,'size_bytes':total,'mime_type':'application/pdf','sha256':digest.hexdigest()}
    except Exception:
        try:
            if tmp.exists():tmp.unlink()
        finally:raise


def _extract_pypdf(path):
    reader_cls=None
    try:
        from pypdf import PdfReader as reader_cls
    except Exception:
        try:from PyPDF2 import PdfReader as reader_cls
        except Exception:return None
    reader=reader_cls(str(path));pages=[]
    for i,p in enumerate(reader.pages,1):pages.append((i,(p.extract_text() or '').strip()))
    return pages


def _extract_pdftotext(path):
    try:cp=subprocess.run(['pdftotext','-layout',str(path),'-'],capture_output=True,text=True,timeout=180,check=True)
    except Exception:return None
    raw=cp.stdout or '';chunks=raw.split('\f');return [(i+1,x.strip()) for i,x in enumerate(chunks) if x.strip()]


def extract_pdf_text(path):
    path=Path(path).resolve()
    if not path.exists():raise ValueError('file_not_found')
    pages=_extract_pypdf(path);method='PYPDF'
    if pages is None:pages=_extract_pdftotext(path);method='PDFTOTEXT'
    if pages is None:return {'status':'EXTRACTOR_UNAVAILABLE','text':'','pages':0,'method':None}
    text='\n\n'.join(f'[[PAGE {n}]]\n{txt}' for n,txt in pages if txt);visible=sum(len(txt.strip()) for _,txt in pages)
    if visible<80:return {'status':'OCR_REQUIRED','text':text,'pages':len(pages),'method':method}
    return {'status':'OK','text':text,'pages':len(pages),'method':method}


def safe_material_path(path):
    p=Path(str(path or '')).resolve()
    return p if PDF_ROOT in p.parents and p.exists() and p.is_file() else None


def remove_file(path):
    try:
        p=safe_material_path(path)
        if p:p.unlink()
    except Exception:pass
