import asyncio
from datetime import date, timedelta
from pathlib import Path
from typing import Callable, Optional

from playwright.async_api import async_playwright, Page

from . import config

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
    try:
        form = await _find_form_frame(page)

        await form.fill("#sDate_view", date_str)
        await form.press("#sDate_view", "Enter")
        await form.fill("#eDate_view", date_str)
        await form.press("#eDate_view", "Enter")

        await form.wait_for_selector("#lookupBtn a", timeout=5000)

        # Get frame reference before clicking so we can wait for its reload
        frame = page.frame(name="if_main_post")
        if frame is None:
            return None

        await form.click("#lookupBtn a")

        # Wait for iframe to finish loading with the new query results
        try:
            await frame.wait_for_load_state("load", timeout=12000)
        except Exception:
            pass

        popup_btn_selector = "#billAll"
        try:
            await frame.wait_for_selector(popup_btn_selector, timeout=3000)
        except Exception:
            # No results for this date
            return None

        await frame.eval_on_selector(popup_btn_selector, "el => el.scrollIntoView()")

        async with page.expect_popup() as popup_info:
            await frame.eval_on_selector(popup_btn_selector, "el => el.click()")
        popup = await popup_info.value

        await popup.wait_for_selector(".popup_content", timeout=10000)
        popup_content = await popup.query_selector(".popup_content")

        if popup_content is None:
            await popup.close()
            return None

        filename = f"하이패스({date_str}).png"
        await popup_content.screenshot(path=str(output_dir / filename))

        try:
            await popup.close()
        except Exception:
            pass

        return filename

    except Exception:
        raise


async def capture_single_date_standalone(
    target_date: date,
    progress_callback: Optional[Callable[[int, int, str], None]] = None,
) -> list[dict]:
    """Full Playwright session for a single date. Used for one-off captures and testing."""
    global capture_logs
    capture_logs = []

    date_str = target_date.strftime("%Y-%m-%d")

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()

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
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()

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

        await browser.close()

    return capture_logs


def _now_iso() -> str:
    from datetime import datetime

    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")
