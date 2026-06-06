import time
from typing import Callable

from playwright.sync_api import Page, Route, sync_playwright

from mindful_news.http import USER_AGENT

AD_DOMAINS = (
    "googlesyndication",
    "doubleclick",
    "genecy",
    "smartadserver",
    "amazon-adsystem",
)


def _block_ads(route: Route) -> None:
    if any(domain in route.request.url for domain in AD_DOMAINS):
        route.abort()
    else:
        route.continue_()


def with_page(callback: Callable) -> list:
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        context = browser.new_context(user_agent=USER_AGENT, locale="es-UY")
        context.route("**/*", _block_ads)
        page = context.new_page()
        try:
            return callback(page)
        finally:
            context.close()
            browser.close()


def scroll_until(page: Page, count_js: str, target: int | None = None, max_scrolls: int = 300) -> int:
    previous = 0
    stale = 0
    for _ in range(max_scrolls):
        page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        time.sleep(0.8)
        current = page.evaluate(count_js)
        if current == previous:
            stale += 1
        else:
            stale = 0
        previous = current
        if target and current >= target:
            break
        if stale >= 8:
            break
    return previous
