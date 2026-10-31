"""Official-source adapters. Unknown layouts fail closed and retain old dates.

Only approved public HTTPS hosts are fetched. Links found in an untrusted page
never extend the network allowlist. No cross-year date extrapolation.
"""
from __future__ import annotations

import hashlib
import ipaddress
import re
import socket
from html.parser import HTMLParser
from urllib.parse import urlparse, urljoin
from urllib.request import Request, build_opener, HTTPRedirectHandler
from datetime import datetime, timezone
from pathlib import Path
import json
import database
from web_backend import olympiad_store as store

REGISTRY='https://rsr-olymp.ru/'
MSU='https://olymp.msu.ru/rus/page/main/29/page/grafik-provedeniya-otborochnogo-ehtapa'
SPBU='https://distolymp2.spbu.ru/olymp/'
MOSCHEM='https://moschem.olimpiada.ru/news/492'
SEED=Path(__file__).resolve().parents[1]/'data/olympiads_2026_2027.json'
MONTHS={v:i+1 for i,v in enumerate(('января','февраля','марта','апреля','мая','июня','июля','августа','сентября','октября','ноября','декабря'))}
ALLOWED_HOSTS={'chem-olymp.mipt.ru','dovuz.sfu.ru','sch-olymp.spbu.ru','energy-hope.ru','rsr-olymp.ru','olymp.msu.ru','distolymp2.spbu.ru','moschem.olimpiada.ru',
 'olymp.hse.ru','www.sechenov.ru','sesc.nsu.ru','olymp.mephi.ru','dovuz.urfu.ru',
 'v-olymp.ru','malun.kpfu.ru','olymp.psu.ru','olympiads.mccme.ru','olimpiadakurchatov.ru',
 'www.energy-hope.ru','pvg.mk.ru','olymp-online.mipt.ru','olymp.bmstu.ru',
 'www.olympiada.spbu.ru','olympiada.spbu.ru','olymp-sibir.nstu.ru','olymp.itmo.ru',
 'abiturient.tsu.ru','oho.misis.ru','olympiad.gazprom.ru','physolymp.spb.ru',
 'olymp.academtalant.ru','turlom.olimpiada.ru','dovuz.sfu-kras.ru',
 'xn--l1ae4a.xn--l1afu.xn--p1ai'}


def safe_url(url):
    p=urlparse(str(url))
    return (p.scheme=='https' and p.hostname in ALLOWED_HOSTS and not p.username and
            not p.password and p.port in (None,443))


def allowed_event_url(url,item):
    if not safe_url(url):
        return False
    host=urlparse(url).hostname
    allowed={urlparse(item['official_url']).hostname}
    extras={38:{'chem-olymp.mipt.ru'} if item['subject']=='CHEMISTRY' else set(),60:{'dovuz.sfu.ru'},43:{'sch-olymp.spbu.ru'},36:{'www.energy-hope.ru','energy-hope.ru'}}
    allowed |= extras.get(item['registry_number'],set())
    if item['registry_number']==26 and item['subject']=='CHEMISTRY':
        allowed.add('moschem.olimpiada.ru')
    return host in allowed


def _public_url(url):
    if not safe_url(url):
        raise ValueError('source_host_not_approved')
    addresses=socket.getaddrinfo(urlparse(url).hostname,443,type=socket.SOCK_STREAM)
    if not addresses or any(not ipaddress.ip_address(a[4][0]).is_global for a in addresses):
        raise ValueError('source_address_not_public')


class Redirect(HTTPRedirectHandler):
    def redirect_request(self,req,fp,code,msg,headers,newurl):
        _public_url(newurl)
        return super().redirect_request(req,fp,code,msg,headers,newurl)


def fetch(url):
    _public_url(url)
    req=Request(url,headers={'User-Agent':'AdeliaOlympiadCalendar/1.0 (+https://adeliatutor.ru)', 'Accept':'text/html'})
    with build_opener(Redirect()).open(req,timeout=20) as response:
        content=response.read(2_000_001)
        if len(content)>2_000_000:
            raise ValueError('source_too_large')
        kind=response.headers.get_content_type()
        if kind not in {'text/html','application/xhtml+xml'}:
            raise ValueError('source_not_html')
        encoding=response.headers.get_content_charset() or 'utf-8'
        return content.decode(encoding,errors='replace')


class Page(HTMLParser):
    def __init__(self,html):
        super().__init__(convert_charrefs=True)
        self.parts=[];self.rows=[];self.links=[];self.row=None;self.cell=None;self.skip=0
        self.feed(html)

    def handle_starttag(self,tag,attrs):
        attrs=dict(attrs)
        if tag in {'script','style'}:
            self.skip+=1
        if tag=='tr':
            self.row=[]
        if tag in {'td','th'} and self.row is not None:
            self.cell={'parts':[],'href':None,'rowspan':int(attrs.get('rowspan','1'))}
        if tag=='a' and attrs.get('href'):self.links.append(attrs['href'])
        if tag=='a' and self.cell is not None and not self.cell['href']:
            self.cell['href']=attrs.get('href')
        if tag in {'br','p','div','li','tr','h1','h2','h3','h4','td','th'}:
            self.parts.append('\n')

    def handle_endtag(self,tag):
        if tag in {'script','style'}:
            self.skip=max(0,self.skip-1)
        if tag in {'td','th'} and self.cell is not None:
            self.cell['text']=' '.join(''.join(self.cell.pop('parts')).split())
            self.row.append(self.cell);self.cell=None
        if tag=='tr' and self.row is not None:
            if self.row:self.rows.append(self.row)
            self.row=None
        if tag in {'p','div','li','tr','h1','h2','h3','h4'}:
            self.parts.append('\n')

    def handle_data(self,data):
        if self.skip:return
        self.parts.append(data)
        if self.cell is not None:self.cell['parts'].append(data)

    @property
    def text(self):
        return ' '.join(''.join(self.parts).split()).replace('\xa0',' ')


def parse_registry(html,year):
    page=Page(html)
    if not re.search(re.escape(year.split('/')[0])+r'\s*[/–-]\s*(?:'+year.split('/')[1]+r'|'+year.split('/')[1][-2:]+r')',page.text):
        raise ValueError('registry_season_not_confirmed')
    number=title=url=None;out={}
    for row in page.rows:
        cells=[x['text'] for x in row]
        if len(row)>=5 and cells[0].isdigit():
            number=int(cells[0]);title=cells[1];url=urljoin(REGISTRY,row[1]['href'] or '')
            profile,subject,level=cells[-3:]
        elif len(row)==3 and number:
            profile,subject,level=cells
        else:
            continue
        code={'физика':'PHYSICS','химия':'CHEMISTRY'}.get(profile.casefold())
        if not code or subject.casefold() not in {'физика','химия'} or level not in {'1','2','3'}:
            continue
        if url.startswith('http://'):url='https://'+url[7:]
        if not safe_url(url):
            raise ValueError('registry_contains_unreviewed_host')
        oid=store.identity(year,number,code)
        item={'id':oid,'season':year,'registry_number':number,'title':title,'subject':code,
              'level':int(level),'official_url':url,'registry_url':REGISTRY}
        if oid in out and out[oid]!=item:
            raise ValueError('conflicting_registry_rows')
        out[oid]=item
    if len(out)<15:
        raise ValueError('registry_layout_changed')
    return list(out.values())


def _event(key,title,kind,start=None,end=None,precision='DATE',status='CONFIRMED',format='UNKNOWN',source=None):
    return dict(stage_key=key,title=title,kind=kind,start_at=start,end_at=end,precision=precision,
                status=status,format=format,source_url=source,evidence='')


def _date(day,month,year):
    return datetime(int(year),MONTHS[month.casefold()],int(day)).date().isoformat()


def parse_msu(html,year):
    p=Page(html)
    y=year.split('/')[0]
    out=[]
    for label,code in [('Физика','PHYSICS'),('Химия','CHEMISTRY')]:
        rows=[r for r in p.rows if r and r[0]['text'].casefold()==label.casefold()]
        if len(rows)!=1:raise ValueError('msu_subject_row_changed')
        text=' '.join(x['text'] for x in rows[0])
        matches=re.findall(r'(\d{1,2})\s+([а-я]+)\s+(20\d{2}).*?(\d{1,2}:\d{2})',text,re.I)
        if len(matches)!=2 or any(x[2]!=y for x in matches):raise ValueError('msu_dates_not_current')
        a,b=[_date(d,m,y)+'T'+t+':00+03:00' for d,m,y,t in matches]
        oid=store.identity(year,35,code)
        out.append((oid,_event('qualifier','Отборочный этап','QUALIFIER',a,b,'TIME',format='ONLINE',source=MSU)))
        # Registration deadline is published separately on the profile page;
        # never infer it merely from the qualifier's end date.
    if len(out)!=2:raise ValueError('msu_layout_changed')
    return out


def parse_spbu(html,year):
    t=Page(html).text
    if year not in t and year.replace('/','-') not in t:raise ValueError('spbu_season_missing')
    oid=store.identity(year,14,'PHYSICS');out=[]
    for n in (1,2):
        m=re.search(r'Дистанционный тур\s*'+str(n)+r'\s*:\s*(\d{1,2})(?:\s+([а-я]+))?\s*[-–—]\s*(\d{1,2})\s+([а-я]+)\s+(20\d{2})',t,re.I)
        if not m:raise ValueError('spbu_tour_layout_changed')
        d1,m1,d2,m2,y=m.groups()
        if y not in year.split('/'):raise ValueError('spbu_dates_not_current')
        out.append((oid,_event('qualifier-'+str(n),'Дистанционный тур '+str(n),'QUALIFIER',_date(d1,m1 or m2,y),_date(d2,m2,y),format='ONLINE',source=SPBU)))
    m=re.search(r'Заключительный\s*\(очный\)\s*тур\s*:\s*(\d{1,2})\s+([а-я]+)\s+(20\d{2})',t,re.I)
    if not m or m[3]!=year.split('/')[1]:raise ValueError('spbu_final_not_current')
    day=_date(*m.groups())
    out.append((oid,_event('final','Заключительный этап','FINAL',day,day,format='OFFLINE',source=SPBU)))
    return out


def parse_msu_profile(html,year):
    t=Page(html).text
    if year not in t:raise ValueError('msu_profile_season_missing')
    subject='PHYSICS' if re.search(r'Физика\s*[-–]',t,re.I) else 'CHEMISTRY' if re.search(r'Химия\s*[-–]',t,re.I) else None
    if not subject:raise ValueError('msu_profile_missing')
    m=re.search(r'Регистрация\s+До\s+(\d{1,2})\s+([а-я]+)\s+(20\d{2})\s+(\d{1,2}:\d{2})',t,re.I)
    if not m or m[3]!=year.split('/')[0]:raise ValueError('msu_registration_changed')
    end=_date(m[1],m[2],m[3])+'T'+m[4]+':00+03:00'
    url=MSU
    # Preserve a separately verified opening instant, rather than inferring it.
    oid=store.identity(year,35,subject);c=database.connect()
    try:r=c.execute("SELECT start_at FROM olympiad_events WHERE olympiad_id=? AND stage_key='registration'",(oid,)).fetchone()
    finally:c.close()
    start=r['start_at'] if r else None
    return [(oid,_event('registration','Регистрация','REGISTRATION',start,end,'TIME',format='ONLINE',source=url))]


def parse_moschem(html,year):
    t=Page(html).text
    # Isolate the olympiad's schedule before the separate VsOSH timetable.
    t=t.split('Награждение победителей')[0]
    m=re.search(r'Отборочный этап\s*\(дистанционный\)\s*(\d{1,2})\s+([а-я]+)\s*[-—–]\s*(\d{1,2})\s+([а-я]+)\s+(20\d{2})',t,re.I)
    if not m or m[5]!=year.split('/')[0]:raise ValueError('moschem_qualifier_not_current')
    a,ma,b,mb,y=m.groups();oid=store.identity(year,26,'CHEMISTRY')
    out=[(oid,_event('qualifier','Отборочный этап','QUALIFIER',_date(a,ma,y),_date(b,mb,y),format='ONLINE',source=MOSCHEM))]
    for label,key in [('теоретический','final-theory'),('практический','final-practice')]:
        m=re.search(label+r'\s+тур\s*[-—–]\s*(\d{1,2})\s+([а-я]+)\s+(20\d{2})(.{0,35})',t,re.I)
        if not m or m[3]!=year.split('/')[1]:raise ValueError('moschem_final_not_current')
        day=_date(m[1],m[2],m[3]);status='TENTATIVE' if re.search('проект|предвар',m[4],re.I) else 'CONFIRMED'
        out.append((oid,_event(key,'Заключительный · '+label+' тур','FINAL',day,day,status=status,format='OFFLINE',source=MOSCHEM)))
    return out


ADAPTERS={'msu':parse_msu,'msu-profile':parse_msu_profile,'spbu':parse_spbu,'moschem':parse_moschem}


def parse_chem_year(html,year):
    t=Page(html).text;a,b=year.split('/')
    m=re.search(r'(\d{1,2})\s+([а-я]+)\s+'+a+r'\s*[-—–]\s*(\d{1,2})\s+([а-я]+)\s+'+b,t,re.I)
    if not m:raise ValueError('chem_current_schedule_missing')
    first=_date(m[1],m[2],a);last=_date(m[3],m[4],b)
    # The official page has an explicit final stage after the qualifier.
    final=re.search(r'Заключительный.{0,100}?(\d{1,2})\s+([а-я]+)\s+'+b,t,re.I)
    if not final:raise ValueError('chem_current_final_missing')
    day=_date(final[1],final[2],b);oid=store.identity(year,38,'CHEMISTRY');url='https://chem-olymp.mipt.ru/'
    return [(oid,_event('qualifier','Отборочный этап','QUALIFIER',first,last,format='ONLINE',source=url)),
            (oid,_event('final','Заключительный этап','FINAL',day,day,format='OFFLINE',source=url))]


def parse_rosatom_year(html,year):
    t=Page(html).text;a,b=year.split('/')
    if not re.search(a+r'\s*[-–/]\s*(?:'+b+'|'+b[-2:]+')',t):raise ValueError('rosatom_season_missing')
    m=re.search(r'Физика\s*:\s*(\d{1,2})\s+([а-я]+)\s+'+b,t,re.I)
    if not m:raise ValueError('rosatom_current_final_missing')
    day=_date(m[1],m[2],b);url='https://olymp.mephi.ru/rosatom/stages/final'
    return [(store.identity(year,52,'PHYSICS'),_event('final','Заключительный этап · физика','FINAL',day,day,format='OFFLINE',source=url))]


def configure_source(item):
    n=item['registry_number'];sub=item['subject'];oid=item['id']
    if n==35:link_source(oid,MSU,'msu')
    elif n==14:link_source(oid,SPBU,'spbu')
    elif n==38 and sub=='CHEMISTRY':link_source(oid,'https://chem-olymp.mipt.ru/','chem-year')
    elif n==52 and sub=='PHYSICS':link_source(oid,'https://olymp.mephi.ru/rosatom/stages/final','rosatom-year')
    else:link_source(oid,item['official_url'])


def parse_verified(html,year,url):
    """Revalidate reviewed exact dates; changed/missing facts require review.

    This adapter does not invent replacement dates. Each event has its own
    source-specific date expression, checked on the current organizer page.
    """
    data=json.loads(SEED.read_text(encoding='utf-8'))
    if data['season']!=year:raise ValueError('verified_schedule_season_expired')
    text=Page(html).text
    if not all(y in text for y in year.split('/')):raise ValueError('verified_schedule_year_missing')
    events=[(oid,e) for oid,e in data['events'] if e['source_url']==url and e.get('verification_pattern')]
    if not events:raise ValueError('verified_schedule_missing')
    for oid,e in events:
        if not re.search(e['verification_pattern'],text,re.I):
            raise ValueError('organizer_dates_changed_review_required')
    return events


def link_source(oid,url,adapter='review'):
    if not safe_url(url):raise ValueError('source_host_not_approved')
    c=database.connect()
    try:
        c.execute('INSERT OR IGNORE INTO olympiad_sources(url,adapter) VALUES(?,?)',(url,adapter))
        if adapter in {'verified','chem-year','rosatom-year'}:c.execute('UPDATE olympiad_sources SET adapter=? WHERE url=?',(adapter,url))
        c.execute('INSERT OR IGNORE INTO olympiad_source_links VALUES(?,?)',(oid,url))
        c.commit()
    finally:c.close()


def seed():
    store.ensure_schema()
    data=json.loads(SEED.read_text(encoding='utf-8'))
    # Do not advertise last year's catalog as the current season.
    if data['season']!=store.season():return
    c=database.connect()
    try:present={r['id'] for r in c.execute('SELECT id FROM olympiad_catalog')}
    finally:c.close()
    store.upsert_catalog([x for x in data['items'] if x['id'] not in present],datetime.fromisoformat(data['verified_at']))
    for item in data['items']:
        oid=item['id'];number=item['registry_number']
        url,adapter=(MSU,'msu') if number==35 else (SPBU,'spbu') if number==14 else (MOSCHEM,'moschem') if number==26 and item['subject']=='CHEMISTRY' else (item['official_url'],'review')
        link_source(oid,url,adapter)
        if number==35:
            link_source(oid,'https://olymp.msu.ru/rus/event/'+('11026/' if item['subject']=='PHYSICS' else '11029/'),'msu-profile')
    for item in data['items']:
        if item.get('grade_min'):
            c=database.connect()
            try:
                c.execute('UPDATE olympiad_catalog SET grade_min=?,grade_max=?,grade_source=? WHERE id=? AND grade_min IS NULL',(item['grade_min'],item['grade_max'],item['grade_source'],item['id']));c.commit()
            finally:c.close()
    for oid,event in data['events']:
        if event.get('verification_pattern'):
            link_source(oid,event['source_url'],'verified')
        c=database.connect()
        try:exists=c.execute('SELECT 1 FROM olympiad_events WHERE olympiad_id=? AND stage_key=?',(oid,event['stage_key'])).fetchone()
        finally:c.close()
        if not exists:store.save_event(oid,event,checked=datetime.fromisoformat(data['verified_at']),notify=False)


ADAPTERS.update({'chem-year':parse_chem_year,'rosatom-year':parse_rosatom_year})


def refresh(fetcher=fetch):
    seed();year=store.season();results=[]
    try:
        items=parse_registry(fetcher(REGISTRY),year)
        store.upsert_catalog(items,authoritative=True)
        for item in items:
            configure_source(item)
            # Preserve explicitly selected schedule adapters for seeded entries.
            c=database.connect()
            try:exists=c.execute('SELECT 1 FROM olympiad_source_links WHERE olympiad_id=?',(item['id'],)).fetchone()
            finally:c.close()
            if not exists:link_source(item['id'],item['official_url'])
        store.rollover_subscriptions(year)
        registry_error=None
    except Exception as exc:
        registry_error=type(exc).__name__+': '+str(exc)[:180]
    c=database.connect()
    try:
        c.execute('INSERT OR IGNORE INTO olympiad_sources(url,adapter) VALUES(?,?)',(REGISTRY,'registry'))
        c.execute('UPDATE olympiad_sources SET checked_at=?,error=? WHERE url=?',(store.stamp(),registry_error,REGISTRY));c.commit()
        sources=[dict(x) for x in c.execute("SELECT DISTINCT s.* FROM olympiad_sources s JOIN olympiad_source_links l ON l.url=s.url JOIN olympiad_catalog o ON o.id=l.olympiad_id WHERE o.season=? AND o.active=1",(year,))]
    finally:c.close()
    for source in sources:
        at=store.stamp();digest=None;error=None;changed=False
        try:
            html=fetcher(source['url'])
            text=Page(html).text
            if len(text)<120:raise ValueError('source_content_missing')
            digest=hashlib.sha256(text.encode()).hexdigest()
            changed=bool(source['content_hash'] and source['content_hash']!=digest)
            parser=ADAPTERS.get(source['adapter'])
            events=parse_verified(html,year,source['url']) if source['adapter']=='verified' else parser(html,year) if parser else []
            if source['adapter']=='msu-profile':
                for _,event in events:event['source_url']=source['url']
            for oid,event in events:store.save_event(oid,event)
            if source['adapter']=='msu':
                for row in Page(html).rows:
                    if not row:continue
                    code={'физика':'PHYSICS','химия':'CHEMISTRY'}.get(row[0]['text'].casefold())
                    target=urljoin(MSU,row[0]['href'] or '')
                    if code and row[0]['href'] and urlparse(target).hostname=='olymp.msu.ru':
                        link_source(store.identity(year,35,code),target,'msu-profile')
        except Exception as exc:
            error=type(exc).__name__+': '+str(exc)[:180]
        review=bool(error or (changed and source['adapter']=='review'))
        c=database.connect()
        try:
            c.execute('''UPDATE olympiad_sources SET checked_at=?,error=?,
              content_hash=COALESCE(?,content_hash),changed_at=CASE WHEN ? THEN ? ELSE changed_at END,
              review_required=CASE WHEN ? THEN 1 ELSE review_required END WHERE url=?''',
              (at,error,digest if not error else None,int(changed),at,int(review),source['url']))
            if review and changed:
                ids=[r['olympiad_id'] for r in c.execute('SELECT olympiad_id FROM olympiad_source_links WHERE url=?',(source['url'],))]
                for oid in ids:
                    title=store.catalog_item(c,oid)['title']
                    for s in c.execute("SELECT * FROM olympiad_subscriptions WHERE role='teacher' AND olympiad_id=?",(oid,)):
                        store._notice(c,'teacher',s['entity_id'],oid,'source:'+str(digest),f'🏆 {title}\nОрганизатор обновил страницу. Проверьте расписание: {source["url"]}',json.loads(s['channels_json']),at)
            c.commit()
        finally:c.close()
        results.append({'url':source['url'],'changed':changed,'error':error,'review_required':review})
    return {'registry_error':registry_error,'sources':results}
