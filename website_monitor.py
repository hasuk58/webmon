#!/usr/bin/env python3
import requests
import time
import concurrent.futures
import configparser
import ssl
import urllib3
import warnings
from datetime import datetime
from pathlib import Path
from requests.adapters import HTTPAdapter

# =============================
# 1. SSL 경고 완전 비활성화
# =============================
warnings.filterwarnings("ignore", category=urllib3.exceptions.InsecureRequestWarning)
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


# =============================
# 2. 브라우저 유사 SSL 어댑터
# =============================
class PermissiveSSLAdapter(HTTPAdapter):
    """브라우저 수준 SSL 허용 + 연결 풀 지원"""

    def __init__(self, *args, **kwargs):
        kwargs.setdefault("pool_connections", 100)
        kwargs.setdefault("pool_maxsize", 100)
        super().__init__(*args, **kwargs)

    def init_poolmanager(self, *args, **kwargs):
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        ctx.options &= ~ssl.OP_NO_TLSv1_2
        ctx.options &= ~ssl.OP_NO_TLSv1_3
        try:
            ctx.set_ciphers("DEFAULT:@SECLEVEL=0")
        except Exception:
            pass
        kwargs["ssl_context"] = ctx
        return super().init_poolmanager(*args, **kwargs)

    def proxy_manager_for(self, *args, **kwargs):
        kwargs["ssl_context"] = ssl._create_unverified_context()
        return super().proxy_manager_for(*args, **kwargs)


# =============================
# 3. 설정 로드
# =============================
config = configparser.ConfigParser()
cfg_path = Path("setting.ini")

if not cfg_path.exists():
    config["General"] = {
        "concurrent_limit": "5",
        "interval": "2",
        "cooldown": "5"
    }
    config["Telegram"] = {
        "bot_token": "YOUR_BOT_TOKEN",
        "chat_id": "YOUR_CHAT_ID"
    }
    with open(cfg_path, "w", encoding="utf-8") as f:
        config.write(f)
    print("⚙️ setting.ini 생성됨 — bot_token, chat_id 입력 후 다시 실행.")
    raise SystemExit(0)

config.read(cfg_path, encoding="utf-8")

CONCURRENT_LIMIT = int(config["General"].get("concurrent_limit", "5"))
INTERVAL = int(config["General"].get("interval", "2"))
COOLDOWN = int(config["General"].get("cooldown", "5"))
BOT_TOKEN = config["Telegram"].get("bot_token", "")
CHAT_ID = config["Telegram"].get("chat_id", "")


# =============================
# 4. 전역 변수 / 설정
# =============================
TIMEOUT_DEFAULT = 10
SLOW_DEFAULT = 3.0
ALERT_REPEAT_LIMIT = 10
alert_state = {}

DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/122.0.6261.70 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Encoding": "gzip, deflate, br",
    "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
    "Cache-Control": "max-age=0",
    "Referer": "https://www.google.com/",
    "Upgrade-Insecure-Requests": "1",
    "Connection": "keep-alive"
}


# =============================
# 5. 세션 재생성
# =============================
def reset_session():
    global session
    try:
        session.close()
    except Exception:
        pass
    session = requests.Session()
    adapter = PermissiveSSLAdapter(pool_connections=100, pool_maxsize=100)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    session.headers.update(DEFAULT_HEADERS)
    print(f"[{datetime.now():%H:%M:%S}] 🔄 세션 재생성 완료")


# =============================
# 6. SSL 관련 메시지 억제 필터
# =============================
def should_suppress_message(text: str) -> bool:
    if not text:
        return False
    t = text.lower()
    suppress_keywords = [
        "certificate_verify_failed",
        "ssl: certificate_verify_failed",
        "wrong_signature_type",
        "ssl: wrong_signature_type",
        "sslerror(certificateerror"
    ]
    return any(k in t for k in suppress_keywords)


# =============================
# 7. 텔레그램 전송
# =============================
def send_telegram_message(msg: str):
    if should_suppress_message(msg):
        print(f"[{datetime.now():%H:%M:%S}] (텔레그램 억제) SSL 관련 메시지 전송 생략.")
        return

    if not BOT_TOKEN or not CHAT_ID:
        print(f"[{datetime.now():%H:%M:%S}] ⚠️ Telegram 설정 누락 (setting.ini 확인).")
        return

    try:
        resp = requests.post(
            f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
            json={"chat_id": CHAT_ID, "text": msg, "disable_web_page_preview": True},
            timeout=8
        )
        if resp.status_code != 200:
            print(f"[{datetime.now():%H:%M:%S}] ⚠️ Telegram 오류: {resp.status_code} {resp.text}")
    except Exception as e:
        print(f"[{datetime.now():%H:%M:%S}] ⚠️ 텔레그램 전송 실패: {e}")


# =============================
# 8. 사이트 검사
# =============================
def check_site(target, idx, total):
    url = target["url"]
    timeout = target["timeout"]
    slow = target["slow"]
    note = target["note"]

    meta = alert_state.get(url, {"problem_active": False, "repeat_count": 0})
    print(f"[{datetime.now():%H:%M:%S}] ({idx}/{total}) 🌐 {url} 검사 중...", end="\r")

    try:
        start = time.time()
        r = session.get(url, timeout=timeout, verify=False)
        elapsed = time.time() - start

        if r.status_code >= 400:
            raise Exception(f"HTTP {r.status_code}")

        # 느린 응답 감지
        if elapsed > slow:
            print(f"[{datetime.now():%H:%M:%S}] ({idx}/{total}) ⚠️ 느림: {url} ({elapsed:.2f}s > {slow:.2f}s)")

        # 정상 응답 처리
        if meta.get("problem_active"):
            send_telegram_message(f"✅ 복구됨: {url}\n{note}")
        meta["problem_active"] = False
        meta["repeat_count"] = 0
        print(f"[{datetime.now():%H:%M:%S}] ({idx}/{total}) ✅ {url} 정상 ({elapsed:.2f}s)        ")

    except Exception as e:
        emsg = str(e)
        payload = f"⚠️ 연결 실패: {url}\n이유: {emsg}\n{note}"

        if not meta.get("problem_active"):
            send_telegram_message(payload)
            meta["problem_active"] = True
            meta["repeat_count"] = 1
        else:
            if meta.get("repeat_count", 0) < ALERT_REPEAT_LIMIT:
                send_telegram_message(
                    f"🚨 여전히 장애 중: {url}\n({meta['repeat_count']+1}/{ALERT_REPEAT_LIMIT})\n이유: {emsg}\n{note}"
                )
                meta["repeat_count"] += 1

        print(f"[{datetime.now():%H:%M:%S}] ({idx}/{total}) ❌ {url} 오류 ({emsg})        ")

    alert_state[url] = meta


# =============================
# 9. 리스트 분할
# =============================
def chunk_list(lst, size):
    for i in range(0, len(lst), size):
        yield lst[i:i + size]


# =============================
# 10. 메인 루프
# =============================
def main():
    target_dir = Path("target_sites")
    target_dir.mkdir(exist_ok=True)
    targets = []
    for f in sorted(target_dir.glob("*.txt")):
        data = {}
        for line in f.read_text(encoding="utf-8").splitlines():
            if "=" in line:
                k, v = [x.strip() for x in line.split("=", 1)]
                data[k.lower()] = v
        if "url" in data:
            targets.append({
                "url": data["url"],
                "timeout": float(data.get("timeout", TIMEOUT_DEFAULT)),
                "slow": float(data.get("slow_threshold", SLOW_DEFAULT)),
                "note": data.get("note", "")
            })

    if not targets:
        print("❌ target_sites 폴더에 검사 대상이 없습니다.")
        return

    total_sites = len(targets)
    send_telegram_message(
        f"🟢 모니터링 시작 ({total_sites}개 사이트)\n"
        f"동시 검사: {CONCURRENT_LIMIT}개 / 간격: {INTERVAL}s / 쿨다운: {COOLDOWN}s"
    )

    while True:
        print(f"\n[{datetime.now():%H:%M:%S}] 🌐 총 {total_sites}개 사이트 검사 시작 ------------------")
        idx = 1
        for group in chunk_list(targets, CONCURRENT_LIMIT):
            with concurrent.futures.ThreadPoolExecutor(max_workers=CONCURRENT_LIMIT) as executor:
                futures = [
                    executor.submit(check_site, t, idx + i, total_sites)
                    for i, t in enumerate(group)
                ]
                concurrent.futures.wait(futures)
            print(f"[{datetime.now():%H:%M:%S}] ⏸️ {INTERVAL}초 대기 후 다음 그룹 실행")
            time.sleep(INTERVAL)
            idx += len(group)

        print(f"[{datetime.now():%H:%M:%S}] ✅ 전체 검사 완료. {COOLDOWN}초 대기...\n")
        time.sleep(COOLDOWN)
        reset_session()


# =============================
# 11. 실행
# =============================
if __name__ == "__main__":
    try:
        reset_session()
        main()
    except KeyboardInterrupt:
        print("\n🛑 프로그램 종료됨.")

