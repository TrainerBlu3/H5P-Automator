"""
Standalone Moodle login flow, used by the main window's Moodle login/status
button. Adapted from content_checker.py's ContentChecker._scrape_moodle —
same login sequence (Manual Login click, Microsoft SSO handling, stale-session
logout, credential auto-fill, manual-login fallback wait loop), but stops once
logged in instead of continuing on to scrape the course page. content_checker.py
itself is left untouched — this is a separate, standalone entry point.
"""
from playwright.async_api import BrowserContext

from config import SESSION_FILE

MOODLE_LOGIN_URL = "https://mymoodle.okanagan.bc.ca/login/index.php?saml=off"


async def run_moodle_login_only(
    context: BrowserContext,
    moodle_url: str,
    moodle_username: str = "",
    moodle_password: str = "",
    sso_password: str = "",
    log_fn=None,
) -> bool:
    """Open Moodle in a new tab, log in (auto-fill if credentials given, else
    wait for manual login), save the shared session, then close the tab.
    Returns True on success."""
    def log(msg, tag="info"):
        if log_fn:
            log_fn(msg, tag)
        print(msg)

    tab = await context.new_page()
    try:
        target = moodle_url or "https://mymoodle.okanagan.bc.ca/"
        log("Opening Moodle…", "info")
        try:
            await tab.goto(target, wait_until="domcontentloaded", timeout=30000)
        except Exception:
            pass
        await tab.wait_for_timeout(1500)

        if "login" not in tab.url.lower() and "course" in tab.url.lower():
            log("✓ Already logged in to Moodle", "success")
            await context.storage_state(path=SESSION_FILE)
            return True

        moodle_user = moodle_username
        moodle_pass = moodle_password
        sso_pass = sso_password or moodle_pass

        async def _click_manual_login():
            log("  Navigating to Manual Login form…", "info")
            try:
                await tab.goto(MOODLE_LOGIN_URL, wait_until="domcontentloaded", timeout=15000)
                await tab.wait_for_timeout(1000)
                logout_btn = tab.locator('button:has-text("Log out")')
                if await logout_btn.count() > 0:
                    log("  Clearing existing SSO session (Log out)…", "info")
                    await logout_btn.first.click()
                    await tab.wait_for_load_state("domcontentloaded", timeout=15000)
                    await tab.wait_for_timeout(1000)
                    await tab.goto(MOODLE_LOGIN_URL, wait_until="domcontentloaded", timeout=15000)
                    await tab.wait_for_timeout(1000)
                return True
            except Exception:
                return False

        async def _handle_microsoft_sso():
            if "microsoftonline.com" not in tab.url:
                return
            log("  Microsoft SSO detected — selecting account…", "info")
            try:
                await tab.wait_for_timeout(2000)
                clicked = await tab.evaluate("""() => {
                    function findAndClick(root) {
                        for (const el of root.querySelectorAll('*')) {
                            const text = el.textContent || '';
                            if (text.includes('okanagan.bc.ca') && el.children.length === 0) {
                                let p = el;
                                for (let i = 0; i < 6; i++) {
                                    if (!p) break;
                                    if (p.tagName === 'DIV' && (p.getAttribute('role') === 'button'
                                            || p.onclick || p.getAttribute('tabindex') === '0')) {
                                        p.click(); return true;
                                    }
                                    p = p.parentElement;
                                }
                                el.click(); return true;
                            }
                        }
                        return false;
                    }
                    return findAndClick(document);
                }""")
                if clicked:
                    await tab.wait_for_load_state("domcontentloaded", timeout=10000)
                    await tab.wait_for_timeout(2000)
            except Exception:
                pass

            if "microsoftonline.com" in tab.url:
                log("  Entering Microsoft password…", "info")
                try:
                    pwd_input = tab.locator('#i0118')
                    await pwd_input.wait_for(state="visible", timeout=8000)
                    await pwd_input.fill(sso_pass)
                    await tab.locator('#idSIButton9').click()
                    await tab.wait_for_load_state("domcontentloaded", timeout=15000)
                    await tab.wait_for_timeout(2000)
                    if "microsoftonline.com" in tab.url:
                        stay_no = tab.locator('#idBtn_Back')
                        if await stay_no.count() > 0:
                            log("  Dismissing 'Stay signed in?' prompt…", "info")
                            await stay_no.click()
                            await tab.wait_for_load_state("domcontentloaded", timeout=10000)
                            await tab.wait_for_timeout(1500)
                except Exception as e:
                    log(f"  ⚠ Microsoft password step failed: {e}", "warning")

        await _click_manual_login()
        await _handle_microsoft_sso()

        if "loginredirect" in tab.url:
            log("  Clearing stale session (Log out)…", "info")
            try:
                logout_btn = tab.locator('button[type="submit"].btn-primary')
                if await logout_btn.count() > 0:
                    await logout_btn.first.click()
                    await tab.wait_for_load_state("domcontentloaded", timeout=10000)
                    await tab.wait_for_timeout(2000)
            except Exception:
                pass
            await _click_manual_login()
            await _handle_microsoft_sso()

        if "saml=off" in tab.url or ("login" in tab.url.lower() and "microsoftonline" not in tab.url):
            if moodle_user and moodle_pass:
                log("  Filling Moodle credentials…", "info")
                try:
                    await tab.evaluate("""([u, p]) => {
                        const set = Object.getOwnPropertyDescriptor(
                            window.HTMLInputElement.prototype, 'value').set;
                        const uEl = document.querySelector('#username');
                        const pEl = document.querySelector('#password');
                        set.call(uEl, u); uEl.dispatchEvent(new Event('input', {bubbles:true}));
                        set.call(pEl, p); pEl.dispatchEvent(new Event('input', {bubbles:true}));
                        document.querySelector('#loginbtn').click();
                    }""", [moodle_user, moodle_pass])
                    await tab.wait_for_load_state("domcontentloaded", timeout=15000)
                    await tab.wait_for_timeout(2000)
                    log("✓ Moodle login complete", "success")
                except Exception as e:
                    log(f"✗ Auto-login failed: {e}", "error")
                    return False
            else:
                log("  No Moodle credentials saved — log in manually in the browser window.", "warning")
                for i in range(120):
                    await tab.wait_for_timeout(3000)
                    if i % 10 == 9:
                        log(f"  Waiting for Moodle login… ({(i + 1) * 3}s)", "dim")
                    if "login" not in tab.url.lower():
                        log("✓ Moodle login detected", "success")
                        await tab.wait_for_timeout(1500)
                        break
                else:
                    log("✗ Moodle login timed out", "error")
                    return False

        try:
            await context.storage_state(path=SESSION_FILE)
            log(f"Moodle: session saved to {SESSION_FILE}", "success")
        except Exception:
            pass
        return True
    finally:
        await tab.close()
