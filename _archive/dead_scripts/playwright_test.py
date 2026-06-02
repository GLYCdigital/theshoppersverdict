"""Quick Playwright test against Amazon."""
import asyncio
from playwright.async_api import async_playwright

async def test():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        page = await context.new_page()
        
        print("Navigating to Amazon...")
        try:
            await page.goto("https://www.amazon.com/dp/B00FLYWNYQ", wait_until="domcontentloaded", timeout=30000)
            await page.wait_for_timeout(3000)
            
            # Get title
            title = await page.title()
            print(f"Title: {title}")
            
            # Try to get product title
            el = await page.query_selector("#productTitle")
            if el:
                print(f"Product: {await el.inner_text()}")
            
            # Try to get rating
            el = await page.query_selector(".a-icon-alt")
            if el:
                print(f"Rating: {await el.inner_text()}")
            
            # Try to get review count
            el = await page.query_selector("#acrCustomerReviewText")
            if el:
                print(f"Reviews: {await el.inner_text()}")
            
            # Try to get price
            el = await page.query_selector(".a-price-whole")
            if el:
                print(f"Price: ${await el.inner_text()}")
            
            # Try to get image
            el = await page.query_selector("#landingImage")
            if el:
                src = await el.get_attribute("src")
                print(f"Image: {src}")
            
            # Try to get a few review texts
            print("\nTop reviews:")
            reviews = await page.query_selector_all("[data-hook='review-body']")
            for i, r in enumerate(reviews[:3], 1):
                text = await r.inner_text()
                print(f"\nReview {i}: {text[:200]}...")
            
        except Exception as e:
            print(f"Error: {e}")
        
        await browser.close()

asyncio.run(test())
