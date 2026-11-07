from pathlib import Path

from playwright.sync_api import Page, sync_playwright

BASE_URL = "http://localhost:8501"
OUTPUT_DIR = Path("docs/assets/screenshots/phase-2")
CHROME_PATH = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"


def open_setup(page: Page) -> None:
    page.goto(BASE_URL, wait_until="networkidle")
    page.get_by_role("radio", name="AI Campaign Setup").click(force=True)
    page.get_by_role("heading", name="AI Campaign Setup").wait_for()


def screenshot(page: Page, name: str) -> None:
    page.locator('[data-testid="stMain"]').evaluate("element => element.scrollTop = 0")
    page.screenshot(path=OUTPUT_DIR / name, full_page=True)


def generate(page: Page, prompt: str) -> None:
    page.get_by_label("캠페인 요청").fill(prompt)
    page.get_by_role("button", name="AI 초안 생성").click()


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(executable_path=CHROME_PATH, headless=True)
        context = browser.new_context(viewport={"width": 1440, "height": 1400})

        page = context.new_page()
        open_setup(page)
        incomplete = "캠페인명: Phase 2 데모; 목표: 신규 앱 설치; 총예산: 300만원"
        page.get_by_label("캠페인 요청").fill(incomplete)
        screenshot(page, "01-natural-language-input.png")
        page.get_by_role("button", name="AI 초안 생성").click()
        page.get_by_text("NEEDS_CLARIFICATION", exact=False).wait_for()
        screenshot(page, "02-needs-clarification.png")

        page.get_by_label("추가 정보").fill(
            "일예산: 10만원; 시작일: 2026-12-01; 종료일: 2026-12-31; "
            '채널: mobile, search; 타게팅: {"country":"KR","audience":"synthetic"}'
        )
        page.get_by_role("button", name="초안 보완").click()
        page.get_by_text("초안 상태: READY", exact=True).wait_for()
        screenshot(page, "03-ready-preview.png")
        page.get_by_role("button", name="확인 후 DRAFT 저장").click()
        page.get_by_role("heading", name="Campaign Detail").wait_for()
        screenshot(page, "04-draft-saved-detail.png")

        validation_page = context.new_page()
        open_setup(validation_page)
        generate(
            validation_page,
            '{"name":"Validation Demo","objective":"Install","total_budget_krw":100000,'
            '"daily_budget_krw":200000,"start_date":"2026-12-01",'
            '"end_date":"2026-12-31","channels":["mobile"],"targeting":{}}',
        )
        validation_page.get_by_text("VALIDATION_FAILED", exact=False).wait_for()
        screenshot(validation_page, "05-validation-blocked.png")

        error_page = context.new_page()
        open_setup(error_page)
        generate(error_page, "{not-valid-json")
        error_page.get_by_text("PROVIDER_ERROR", exact=False).wait_for()
        screenshot(error_page, "06-provider-error.png")
        browser.close()


if __name__ == "__main__":
    main()
