from pathlib import Path


def main():
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-dev-shm-usage"]
        )
        page = browser.new_page()
        page.goto("https://example.com")
        out = Path(__file__).resolve().parent / "example.png"
        page.screenshot(path=str(out), full_page=True)
        browser.close()


if __name__ == "__main__":
    main()
