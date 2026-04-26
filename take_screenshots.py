import asyncio
from playwright.async_api import async_playwright
import os
import random

async def main():
    if not os.path.exists('screenshots'):
        os.makedirs('screenshots')

    rand_email = f"johndoe_{random.randint(1000, 9999)}@example.com"

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        # Using a slightly larger viewport to fit modals well
        context = await browser.new_context(viewport={'width': 1280, 'height': 900})
        page = await context.new_page()

        # We already have login_page and chat_interface, but let's just do them all or skip the old ones.
        # I'll just capture the new ones to save time, but wait, the user didn't say to replace, they said ADD.
        # I will only capture profile and weather.

        print("Registering fake user for profile screenshot...")
        await page.goto('http://127.0.0.1:5000/login.html')
        await asyncio.sleep(2)
        await page.click('#showRegister')
        await asyncio.sleep(1)
        
        # Fake details
        await page.fill('#regName', 'John Doe')
        await page.fill('#regLocation', 'Pune, Maharashtra')
        await page.fill('#regMobile', '9876543210')
        await page.fill('#regEmail', rand_email)
        await page.fill('#regPassword', 'password123')
        await page.click('#registerBtn')
        
        await asyncio.sleep(5)

        print("Logging in...")
        await page.goto('http://127.0.0.1:5000/login.html')
        await asyncio.sleep(2)
        await page.fill('#email', rand_email)
        await page.fill('#password', 'password123')
        await page.click('#loginBtn')
        
        await asyncio.sleep(5)
        
        # 1. Take Profile Modal Screenshot
        print("Opening Profile Modal...")
        await page.click('#userProfile')
        await asyncio.sleep(2)
        
        # Add some fake crop data to make it look good
        await page.fill('#profFarmSize', '5 Acres')
        await page.fill('#profCrops', 'Wheat, Soyabean')
        await page.fill('#profSoilType', 'Black Cotton Soil')
        
        # We just want a screenshot of the modal, but taking the full page with modal open is good too
        await page.screenshot(path='screenshots/profile_page.png')
        
        # Close profile modal
        await page.click('#closeProfileBtn')
        await asyncio.sleep(1)

        # 2. Take Weather Modal Screenshot
        print("Opening Weather Modal...")
        await page.click('#weatherBadgeBtn')
        await asyncio.sleep(2)
        
        # Change location to a specific area (e.g., Pune) using the new edit button
        await page.click('#editWeatherLocBtn')
        await asyncio.sleep(1)
        await page.fill('#weatherLocInput', 'Pune')
        await page.click('#weatherLocSearchBtn')
        
        print("Waiting for weather data to load...")
        # Wait for the weather to load completely (temperature changes from --° to actual value)
        try:
            await page.wait_for_function('document.getElementById("weatherCurrentTemp").innerText !== "--°"', timeout=25000)
            # Give it an extra second for chart animations
            await asyncio.sleep(1.5)
        except Exception as e:
            print("Timeout waiting for weather data:", e)
            await asyncio.sleep(10) # Fallback wait
        
        await page.screenshot(path='screenshots/weather_dashboard.png')

        await browser.close()
        print("Done!")

if __name__ == '__main__':
    asyncio.run(main())
