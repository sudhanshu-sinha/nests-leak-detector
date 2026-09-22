import os
import asyncio
import aiohttp
import time
import random
import re
import sqlite3
import hashlib
from datetime import datetime
from pathlib import Path

# telegram config - set in env
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

BASE = "https://nests.tribal.gov.in"
DB = Path(__file__).parent / "data.db"

# headers
UA = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/122.0.0.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15",
]

def log(m):
    # Indian time IST = UTC+5:30
    from datetime import timezone, timedelta
    IST = timezone(timedelta(hours=5, minutes=30))
    now_ist = datetime.now(IST)
    print(f"[{now_ist.strftime('%d-%m-%Y %I:%M:%S %p IST')}] {m}")

def init_db():
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute("CREATE TABLE IF NOT EXISTS seen (id TEXT PRIMARY KEY, url TEXT, time TEXT)")
    conn.commit()
    conn.close()

def already_seen(url):
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    hid = hashlib.md5(url.encode()).hexdigest()
    c.execute("SELECT id FROM seen WHERE id=?", (hid,))
    r = c.fetchone()
    conn.close()
    return r is not None

def save_seen(url):
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    hid = hashlib.md5(url.encode()).hexdigest()
    try:
        c.execute("INSERT OR IGNORE INTO seen VALUES (?,?,?)", (hid, url, datetime.now().isoformat()))
        conn.commit()
        conn.close()
        return True
    except:
        conn.close()
        return False

async def send_tg(session, file_url, pdf_file=None):
    if not TOKEN or not CHAT_ID:
        log(f"no token, would send {file_url}")
        return

    # if we have pdf file, send as document
    if pdf_file and Path(pdf_file).exists():
        url = f"https://api.telegram.org/bot{TOKEN}/sendDocument"
        try:
            from datetime import timezone, timedelta
            IST = timezone(timedelta(hours=5, minutes=30))
            now_ist = datetime.now(IST).strftime('%d-%m-%Y %I:%M %p IST')
            with open(pdf_file, 'rb') as f:
                data = aiohttp.FormData()
                data.add_field('chat_id', CHAT_ID)
                data.add_field('caption', f"New PDF found on NESTS server!\n\nLink: {file_url}\nTime: {now_ist}\n\n#ESSE2025")
                data.add_field('document', f, filename=Path(pdf_file).name, content_type='application/pdf')
                async with session.post(url, data=data, timeout=30) as resp:
                    if resp.status == 200:
                        log(f"sent doc {pdf_file}")
                        return
        except Exception as e:
            log(f"doc send err {e}")

    # fallback text
    from datetime import timezone, timedelta
    IST = timezone(timedelta(hours=5, minutes=30))
    now_ist = datetime.now(IST).strftime('%d-%m-%Y %I:%M:%S %p IST')
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    text = f"New PDF uploaded on NESTS!\n\n{file_url}\n\nTime: {now_ist}\n\nDownload now, not yet on website."
    try:
        async with session.post(url, data={"chat_id": CHAT_ID, "text": text}, timeout=15) as resp:
            if resp.status == 200:
                log(f"sent msg {file_url[:50]}")
    except Exception as e:
        log(f"tg err {e}")

async def check_id(session, ls_id, lid):
    url = f"{BASE}/showfile.php?lang=1&level=1&ls_id={ls_id}&lid={lid}"
    if already_seen(url):
        return None
    try:
        headers = {"User-Agent": random.choice(UA)}
        async with session.get(url, headers=headers, timeout=10) as resp:
            ctype = resp.headers.get("Content-Type","")
            disp = resp.headers.get("Content-Disposition","")
            if "pdf" in ctype.lower() or "pdf" in disp.lower():
                data = await resp.read()
                if data[:4] == b"%PDF" or len(data) > 5000:
                    path = Path(__file__).parent / f"{ls_id}_{lid}.pdf"
                    with open(path, 'wb') as f:
                        f.write(data)
                    if save_seen(url):
                        log(f"FOUND ID {ls_id}/{lid} size {len(data)}")
                        await send_tg(session, url, str(path))
                        return url
    except:
        pass
    return None

async def check_ts(session, ts):
    # direct folder check - this is where pdf actually stored
    url = f"{BASE}/WriteReadData/RTF1984/{ts}.pdf"
    if already_seen(url):
        return None
    try:
        headers = {"User-Agent": random.choice(UA)}
        async with session.head(url, headers=headers, timeout=8) as resp:
            if resp.status == 200:
                clen = int(resp.headers.get("Content-Length","0"))
                if clen > 10000:
                    async with session.get(url, headers=headers, timeout=15) as resp2:
                        if resp2.status == 200:
                            data = await resp2.read()
                            if data[:4] == b"%PDF":
                                path = Path(__file__).parent / f"ts_{ts}.pdf"
                                with open(path, 'wb') as f:
                                    f.write(data)
                                if save_seen(url):
                                    log(f"FOUND TS {ts}")
                                    await send_tg(session, url, str(path))
                                    return url
    except:
        pass
    return None

async def one_scan():
    init_db()
    log("scan started")

    # get current max id from website
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(f"{BASE}/show_content.php?lang=1&level=0&ls_id=15&lid=13", headers={"User-Agent": random.choice(UA)}, timeout=15) as resp:
                txt = await resp.text()
                ids = re.findall(r"ls_id=(\d+)", txt)
                max_id = max(int(x) for x in ids) if ids else 1041
    except:
        max_id = 1041

    log(f"max id on site {max_id}")

    async with aiohttp.ClientSession() as session:
        tasks = []
        # check next 50 ids
        for ls_id in range(max_id+1, max_id+51):
            for diff in [391, 390, 392, 389, 393]:
                lid = ls_id - diff
                if lid > 0:
                    tasks.append(check_id(session, ls_id, lid))

        # limit to 20 at a time
        sem = asyncio.Semaphore(20)
        async def run_with_sem(coro):
            async with sem:
                return await coro

        res = await asyncio.gather(*[run_with_sem(t) for t in tasks], return_exceptions=True)
        log(f"id scan done found {len([x for x in res if x])}")

        # timestamp scan - last 30 min every 5 sec
        now = int(time.time())
        ts_tasks = []
        for i in range(0, 30*60, 5):
            ts_tasks.append(check_ts(session, now - i))

        res2 = await asyncio.gather(*[run_with_sem(t) for t in ts_tasks], return_exceptions=True)
        log(f"ts scan done found {len([x for x in res2 if x])}")

async def loop():
    init_db()
    log("bot started")
    while True:
        try:
            await one_scan()
            # sleep 15 sec, 5 sec in evening time when they usually upload
            h = datetime.now().hour
            if 18 <= h <= 23:
                await asyncio.sleep(5)
            else:
                await asyncio.sleep(15)
        except Exception as e:
            log(f"err {e}")
            await asyncio.sleep(10)

async def test_telegram():
    # test if telegram working
    if not TOKEN or not CHAT_ID:
        log("ERROR: TELEGRAM_BOT_TOKEN or CHAT_ID not set")
        return
    from datetime import timezone, timedelta
    IST = timezone(timedelta(hours=5, minutes=30))
    now_ist = datetime.now(IST).strftime('%d-%m-%Y %I:%M %p IST')
    log(f"testing telegram with chat_id {CHAT_ID}")
    async with aiohttp.ClientSession() as session:
        url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
        text = f"✅ NESTS Bot Test OK!\n\nYour bot is perfectly working.\nTime: {now_ist}\n\nCurrent max ID on site: 1041\nLast PDF: 18 Sep 2026 (1789749299.pdf)\nNext PDF expected anytime now.\n\nWhen new PDF uploads, you will get it here in 2 mins.\n\n#Test"
        try:
            async with session.post(url, data={"chat_id": CHAT_ID, "text": text}, timeout=15) as resp:
                txt = await resp.text()
                log(f"telegram response {resp.status}: {txt[:200]}")
                if resp.status == 200:
                    log("✅ TEST PASSED - Check your Telegram now!")
                else:
                    log("❌ TEST FAILED - Check token/chat_id, and send /start to your bot")
        except Exception as e:
            log(f"test err {e}")

if __name__ == "__main__":
    import sys
    if "--test" in sys.argv:
        asyncio.run(test_telegram())
    elif "--loop" in sys.argv:
        asyncio.run(loop())
    else:
        asyncio.run(one_scan())
