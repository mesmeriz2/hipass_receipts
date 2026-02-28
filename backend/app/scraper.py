import asyncio
from datetime import date, timedelta
from pathlib import Path
from typing import Callable, Optional

from playwright.async_api import async_playwright, Page

from . import config

CHROMIUM_ARGS = [
    "--no-sandbox",
    "--disable-gpu",
    "--disable-dev-shm-usage",
    "--disable-extensions",
    "--disable-background-timer-throttling",
    "--disable-renderer-backgrounding",
    "--disable-backgrounding-occluded-windows",
    "--disable-features=TranslateUI",
]

# In-memory log for the most recent capture session
capture_logs: list[dict] = []


async def login(page: Page, user_id: str, password: str) -> None:
    await page.goto("https://www.hipass.co.kr/comm/lginpg.do")

    try:
        await page.wait_for_load_state("networkidle", timeout=8000)
    except Exception:
        pass

    # Close any popup
    popup_selectors = [
        "text=취소",
        'button:has-text("취소")',
        '[onclick*="close"]',
        ".popup_close",
        ".close_btn",
    ]
    for selector in popup_selectors:
        try:
            el = await page.query_selector(selector)
            if el and await el.is_visible():
                await el.click()
                break
        except Exception:
            continue

    await page.wait_for_selector("#per_user_id:not([disabled])", timeout=10000)
    await page.wait_for_selector("#per_passwd:not([disabled])", timeout=10000)

    # Use click + keyboard.type() to simulate real keystrokes.
    # fill() bypasses keydown/keyup/keypress events that the site's JS uses
    # to validate inputs and enable the login button.
    await page.click("#per_user_id", click_count=3)
    await page.keyboard.type(user_id)

    await page.click("#per_passwd", click_count=3)
    await page.keyboard.type(password)

    # Wait for the login button to become enabled
    try:
        await page.wait_for_selector("#per_login:not([disabled])", timeout=5000)
    except Exception:
        pass  # button may not use disabled state — proceed anyway

    await page.click("#per_login")

    # Wait for post-login redirect to complete
    try:
        await page.wait_for_load_state("networkidle", timeout=15000)
    except Exception:
        pass

    # Verify login succeeded — login page URL contains 'lginpg'
    if "lginpg" in page.url:
        raise RuntimeError(
            f"로그인 실패 — 로그인 페이지에 머물러 있음 (자격증명 또는 보안문자 확인 필요). URL: {page.url}"
        )


async def navigate_to_lookup(page: Page, ecd_no: str) -> None:
    await page.goto("https://www.hipass.co.kr/usepculr/InitUsePculrTabSearch.do")

    try:
        await page.wait_for_load_state("networkidle", timeout=10000)
    except Exception:
        pass

    if ecd_no:
        try:
            await page.select_option("#ecd_no", value=ecd_no)
        except Exception:
            pass


async def _find_form_frame(page: Page):
    """Return the frame (or main page) that contains #sDate_view.
    HiPass may embed the search form inside an iframe."""
    try:
        el = await page.query_selector("#sDate_view")
        if el:
            return page
    except Exception:
        pass
    for frame in page.frames:
        if frame.url == "about:blank":
            continue
        try:
            el = await frame.query_selector("#sDate_view")
            if el:
                return frame
        except Exception:
            continue
    return page  # fall back to main page


async def capture_date(
    page: Page, target_date: date, output_dir: Path
) -> Optional[str]:
    date_str = target_date.strftime("%Y-%m-%d")
    alert_fired = False

    def on_dialog(dialog):
        nonlocal alert_fired
        msg = dialog.message.lower() if dialog.message else ""
        print(f"[scraper] dialog: type={dialog.type!r}, message={dialog.message!r}")
        if dialog.type == "alert" and ("없습니다" in msg or "없음" in msg):
            # "출력할 영수증 데이터가 없습니다." — genuine no-data alert
            alert_fired = True
            asyncio.ensure_future(dialog.dismiss())
        else:
            # confirm() asking to print receipt → accept so the popup window opens
            asyncio.ensure_future(dialog.accept())

    page.on("dialog", on_dialog)
    try:
        form = await _find_form_frame(page)
        print(f"[scraper] {date_str}: form frame = {getattr(form, 'url', 'main_page')!r}")

        # #sDate_view / #eDate_view are display-only fields.
        # #sDate / #eDate are the hidden inputs actually used for the query (YYYYMMDD format).
        date_hidden = target_date.strftime("%Y%m%d")
        await form.evaluate(
            """([dateStr, dateHidden]) => {
                const s = document.querySelector('#sDate_view');
                const e = document.querySelector('#eDate_view');
                const sH = document.querySelector('#sDate');
                const eH = document.querySelector('#eDate');
                if (s) { s.value = dateStr; s.dispatchEvent(new Event('change', {bubbles: true})); }
                if (e) { e.value = dateStr; e.dispatchEvent(new Event('change', {bubbles: true})); }
                if (sH) { sH.value = dateHidden; sH.dispatchEvent(new Event('change', {bubbles: true})); }
                if (eH) { eH.value = dateHidden; eH.dispatchEvent(new Event('change', {bubbles: true})); }
            }""",
            [date_str, date_hidden],
        )
        print(f"[scraper] {date_str}: date set → view={date_str}, hidden={date_hidden}")

        await form.wait_for_selector("#lookupBtn a", timeout=5000)
        await form.click("#lookupBtn a")
        print(f"[scraper] {date_str}: lookup clicked")

        # Give the iframe navigation time to actually start before waiting.
        # Using 1.5s here because wait_for_load_state("load") returns immediately
        # if the frame is already in "loaded" state from its previous navigation.
        await asyncio.sleep(1.5)

        frame = page.frame(name="if_main_post")
        if frame is None:
            print(f"[scraper] {date_str}: if_main_post not found (step 1)")
            return None

        try:
            await frame.wait_for_load_state("load", timeout=15000)
        except Exception:
            pass

        # Re-acquire after load to ensure we have the current JS context
        frame = page.frame(name="if_main_post")
        if frame is None:
            print(f"[scraper] {date_str}: if_main_post not found (step 2)")
            return None

        popup_btn_selector = "#billAll"
        try:
            # 10s timeout — covers slow iframe rendering after navigation
            await frame.wait_for_selector(popup_btn_selector, timeout=10000)
        except Exception:
            print(f"[scraper] {date_str}: #billAll not found — no data or iframe still loading")
            return None

        print(f"[scraper] {date_str}: #billAll found, clicking")
        await frame.eval_on_selector(popup_btn_selector, "el => el.scrollIntoView()")

        # Reset alert_fired here — a prior lookup phase alert (e.g. session warning)
        # must not be mistaken for a "no receipt data" alert from #billAll itself.
        alert_fired = False
        await frame.eval_on_selector(popup_btn_selector, "el => el.click()")
        await asyncio.sleep(0.8)  # give alert/popup time to appear

        if alert_fired:
            # "출력할 영수증 데이터가 없습니다." — no receipt data for this date
            print(f"[scraper] {date_str}: alert fired after #billAll — no receipt data")
            return None

        # No alert fired — detect the new popup window via context.pages
        pages = page.context.pages
        popup = pages[-1] if len(pages) > 1 and pages[-1] != page else None
        if popup is None:
            print(f"[scraper] {date_str}: popup window not detected (pages={len(page.context.pages)})")
            return None

        print(f"[scraper] {date_str}: popup detected, capturing .popup_content")
        await popup.wait_for_selector(".popup_content", timeout=10000)
        popup_content = await popup.query_selector(".popup_content")

        if popup_content is None:
            print(f"[scraper] {date_str}: .popup_content not found in popup")
            await popup.close()
            return None

        filename = f"하이패스({date_str}).png"
        await popup_content.screenshot(path=str(output_dir / filename))
        print(f"[scraper] {date_str}: screenshot saved → {filename}")

        try:
            await popup.close()
        except Exception:
            pass

        return filename

    except Exception:
        raise
    finally:
        page.remove_listener("dialog", on_dialog)


async def capture_single_date_standalone(
    target_date: date,
    progress_callback: Optional[Callable[[int, int, str], None]] = None,
) -> list[dict]:
    """Full Playwright session for a single date. Used for one-off captures and testing."""
    global capture_logs
    capture_logs = []

    date_str = target_date.strftime("%Y-%m-%d")

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, args=CHROMIUM_ARGS)
        page = await browser.new_page(viewport={"width": 1024, "height": 768})

        try:
            await login(page, config.HIPASS_ID, config.HIPASS_PW)
            await navigate_to_lookup(page, config.ECD_NO)
        except Exception as e:
            await browser.close()
            capture_logs.append({
                "date": date_str,
                "status": "error",
                "message": f"로그인 실패: {e}",
                "timestamp": _now_iso(),
            })
            return capture_logs

        filename = f"하이패스({date_str}).png"
        output_path = config.SCREENSHOTS_DIR / filename

        if output_path.exists():
            capture_logs.append({
                "date": date_str,
                "status": "skipped",
                "message": "이미 존재함",
                "timestamp": _now_iso(),
            })
        else:
            try:
                result = await capture_date(page, target_date, config.SCREENSHOTS_DIR)
                capture_logs.append({
                    "date": date_str,
                    "status": "success" if result else "empty",
                    "message": "캡처 완료" if result else "통행 기록 없음",
                    "timestamp": _now_iso(),
                })
            except Exception as e:
                capture_logs.append({
                    "date": date_str,
                    "status": "error",
                    "message": str(e),
                    "timestamp": _now_iso(),
                })

        if progress_callback:
            progress_callback(1, 1, date_str)

        await browser.close()

    return capture_logs


async def capture_last_n_days(
    n: int = 14,
    progress_callback: Optional[Callable[[int, int, str], None]] = None,
) -> list[dict]:
    global capture_logs
    capture_logs = []

    today = date.today()
    dates = [today - timedelta(days=i) for i in range(n)]

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, args=CHROMIUM_ARGS)
        page = await browser.new_page(viewport={"width": 1024, "height": 768})

        try:
            await login(page, config.HIPASS_ID, config.HIPASS_PW)
            await navigate_to_lookup(page, config.ECD_NO)
        except Exception as e:
            await browser.close()
            capture_logs.append({
                "date": today.isoformat(),
                "status": "error",
                "message": f"로그인 실패: {e}",
                "timestamp": _now_iso(),
            })
            return capture_logs

        for idx, target_date in enumerate(dates):
            date_str = target_date.strftime("%Y-%m-%d")
            filename = f"하이패스({date_str}).png"
            output_path = config.SCREENSHOTS_DIR / filename

            if output_path.exists():
                capture_logs.append({
                    "date": date_str,
                    "status": "skipped",
                    "message": "이미 존재함",
                    "timestamp": _now_iso(),
                })
                if progress_callback:
                    progress_callback(idx + 1, n, date_str)
                continue

            try:
                result = await capture_date(page, target_date, config.SCREENSHOTS_DIR)
                if result:
                    entry = {
                        "date": date_str,
                        "status": "success",
                        "message": "캡처 완료",
                        "timestamp": _now_iso(),
                    }
                else:
                    entry = {
                        "date": date_str,
                        "status": "empty",
                        "message": "통행 기록 없음",
                        "timestamp": _now_iso(),
                    }
            except Exception as e:
                entry = {
                    "date": date_str,
                    "status": "error",
                    "message": str(e),
                    "timestamp": _now_iso(),
                }
                # Try to recover page state so subsequent dates can still be captured
                try:
                    await navigate_to_lookup(page, config.ECD_NO)
                except Exception:
                    pass

            capture_logs.append(entry)
            if progress_callback:
                progress_callback(idx + 1, n, date_str)
            await asyncio.sleep(config.CAPTURE_COOLDOWN)

        await browser.close()

    return capture_logs


def _now_iso() -> str:
    from datetime import datetime

    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")
