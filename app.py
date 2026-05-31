"""
Google Hotels Price Scraper - Flask Backend
Strategy:
1. Use Playwright ONCE to load the page, extract hotel token + cookies + session params
2. Use requests (fast HTTP) to call the yY52ce batchexecute API once per month
3. Parse the structured JSON response - no HTML parsing needed
Total time: ~5-10 seconds for a full year (12 API calls)
"""

import asyncio
import json
import re
import os
import requests
import nest_asyncio
from datetime import datetime, date
from calendar import monthrange
from flask import Flask, request, jsonify
from flask_cors import CORS
from urllib.parse import quote, urlencode

# Required for asyncio compatibility with gunicorn
nest_asyncio.apply()

app = Flask(__name__)
CORS(app)

@app.route("/")
def index():
    return app.send_static_file("index.html")

app.static_folder = "."
app.static_url_path = ""



def months_in_range(start: date, end: date):
    """Return list of (year, month) tuples covering start..end."""
    months = []
    y, m = start.year, start.month
    while (y, m) <= (end.year, end.month):
        months.append((y, m))
        m += 1
        if m > 12:
            m = 1
            y += 1
    return months


def month_window(year: int, month: int):
    """Return (start_list, end_list) covering the full month for the API call.
    Google's API wants the last day of previous month as window start."""
    # Start: last day of previous month
    if month == 1:
        prev_year, prev_month = year - 1, 12
    else:
        prev_year, prev_month = year, month - 1
    prev_last = monthrange(prev_year, prev_month)[1]
    start = [prev_year, prev_month, prev_last]
    # End: last day of this month
    this_last = monthrange(year, month)[1]
    end = [year, month, this_last]
    return start, end


def parse_yY52ce_response(text: str) -> dict:
    """Parse the yY52ce batchexecute response into {date_str: price_int}."""
    results = {}
    m = re.search(r'\["wrb\.fr","yY52ce","(.+?)",null,null,null', text, re.DOTALL)
    if not m:
        return results
    try:
        inner = json.loads('"' + m.group(1) + '"')
        parsed = json.loads(inner)
        entries = parsed[1]
        for entry in entries:
            try:
                price_str = entry[1][0]          # "$897"
                price = int(price_str.replace('$', '').replace(',', ''))
                ci = entry[8][0]                  # [2026, 6, 3]
                date_str = f"{ci[0]}-{ci[1]:02d}-{ci[2]:02d}"
                results[date_str] = price
            except (IndexError, TypeError, ValueError, KeyError):
                pass
    except Exception:
        pass
    return results


async def get_session_and_token(hotel_name: str) -> dict:
    """
    Use Playwright once to:
    1. Load the search page and click into the hotel
    2. Extract the hotel token from the entity URL
    3. Capture cookies + f.sid + bl from a batchexecute request
    """
    from playwright.async_api import async_playwright

    session_data = {
        "token": None,
        "cookies": {},
        "sid": None,
        "bl": None,
        "f_sid": None,
    }
    captured = []

    async with async_playwright() as p:

        print("Chromium exists:", os.path.exists("/usr/bin/chromium"))

        browser = await p.chromium.launch(
            executable_path="/usr/bin/chromium",
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-dev-shm-usage",
                "--disable-gpu",
                "--disable-blink-features=AutomationControlled",
                "--disable-setuid-sandbox",
                "--single-process",
                "--no-zygote",
            ]
        )

        context = await browser.new_context(
            viewport={"width": 1400, "height": 900},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            locale="en-US",
        )

        page = await context.new_page()

        await page.add_init_script(
            "Object.defineProperty(navigator, 'webdriver', { get: () => undefined });"
        )

        async def on_request(req):
            if "batchexecute" in req.url and not captured:
                url = req.url

                sid_m = re.search(r"f\.sid=(-?\d+)", url)
                bl_m = re.search(r"bl=([^&]+)", url)

                if sid_m:
                    session_data["f_sid"] = sid_m.group(1)

                if bl_m:
                    session_data["bl"] = bl_m.group(1)

                captured.append(True)

        page.on("request", on_request)

        encoded = quote(hotel_name)

        await page.goto(
            f"https://www.google.com/travel/search?q={encoded}&hl=en&gl=sg&curr=USD",
            wait_until="commit",
            timeout=20000,
        )

        print("Status:", response.status if response else "No response")
        print("Final URL:", page.url)
        
        await page.screenshot(path="/tmp/google.png")
        
        print(await page.title())
        print((await page.content())[:2000])

        await page.wait_for_timeout(3000)

        links = await page.eval_on_selector_all(
            'a[href*="/travel/hotels/entity/"]',
            "els => els.map(e => e.href)"
        )

        for link in links:
            token_m = re.search(
                r"/travel/hotels/entity/([A-Za-z0-9_=-]+)",
                link
            )

            if token_m:
                session_data["token"] = token_m.group(1)
                break

        if session_data["token"]:
            try:
                await page.click(
                    'a[href*="/travel/hotels/entity/"]',
                    timeout=5000
                )

                await page.wait_for_timeout(2000)

                await page.get_by_text(
                    "Prices",
                    exact=True
                ).first.click(timeout=4000)

                await page.wait_for_timeout(2000)

                await page.mouse.click(433, 215)

                await page.wait_for_timeout(2500)

            except Exception as e:
                print("Click sequence failed:", e)

        cookies = await context.cookies()

        session_data["cookies"] = {
            c["name"]: c["value"]
            for c in cookies
        }

        await browser.close()

    return session_data


def fetch_month_prices(session: dict, year: int, month: int) -> dict:
    """Call the yY52ce API for one month. Returns {date_str: price}."""
    start, end = month_window(year, month)

    inner_payload = json.dumps([None, [start, end, 1], None, session["token"], "SGD"])
    freq = json.dumps([[["yY52ce", inner_payload, None, "generic"]]])

    params = {
        "rpcids": "yY52ce",
        "source-path": "/travel/search",
        "hl": "en",
        "gl": "sg",
        "soc-app": "162",
        "soc-platform": "1",
        "soc-device": "1",
        "rt": "c",
    }
    if session.get("f_sid"):
        params["f.sid"] = session["f_sid"]
    if session.get("bl"):
        params["bl"] = session["bl"]

    headers = {
        "Content-Type": "application/x-www-form-urlencoded;charset=UTF-8",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Referer": "https://www.google.com/travel/search",
        "x-same-domain": "1",
        "x-goog-ext-259736195-jspb": '["en-US","SG","USD",1,null,[-480],null,null,7,[]]',
        "x-goog-ext-190139975-jspb": '["SG","ZZ","ZwswOw=="]',
    }

    resp = requests.post(
        "https://www.google.com/_/TravelFrontendUi/data/batchexecute",
        params=params,
        data={"f.req": freq},
        headers=headers,
        cookies=session["cookies"],
        timeout=15,
    )
    if resp.status_code != 200:
        return {}
    return parse_yY52ce_response(resp.text)


async def scrape_hotel_prices(hotel_name: str, start_date: str, end_date: str):
    start = datetime.strptime(start_date, "%Y-%m-%d").date()
    end   = datetime.strptime(end_date,   "%Y-%m-%d").date()
    debug = []

    # Step 1: Browser session (one-time, ~15-20s)
    debug.append("Launching browser to get session token...")
    session = await get_session_and_token(hotel_name)

    if not session["token"]:
        return [], ["ERROR: Could not find hotel token. Check hotel name."]

    debug.append(f"Hotel token: {session['token']}")
    debug.append(f"Session ID: {session['f_sid']}, Build: {session['bl']}")
    debug.append(f"Cookies: {len(session['cookies'])} captured")

    # Step 2: API calls — one per month (fast, ~1s each)
    all_prices = {}
    months = months_in_range(start, end)
    debug.append(f"Fetching {len(months)} months via API...")

    for year, month in months:
        prices = fetch_month_prices(session, year, month)
        debug.append(f"  {year}-{month:02d}: {len(prices)} prices fetched")
        all_prices.update(prices)

    # Step 3: Build results for requested date range
    results = []
    current = start
    while current <= end:
        ds = current.strftime("%Y-%m-%d")
        results.append({
            "date": ds,
            "price": all_prices.get(ds),
            "day_of_week": current.strftime("%a"),
            "month": current.strftime("%B %Y"),
        })
        from datetime import timedelta
        current += timedelta(days=1)

    debug.append(f"Done. {len([r for r in results if r['price']])} prices found out of {len(results)} days.")
    return results, debug


def calculate_stats(results):
    monthly = {}
    all_prices = []
    for r in results:
        if r["price"] is None:
            continue
        m = r["month"]
        monthly.setdefault(m, []).append(r["price"])
        all_prices.append(r["price"])

    return {
        "monthly": {
            m: {
                "average": round(sum(p) / len(p), 2),
                "min": min(p), "max": max(p), "count": len(p),
            }
            for m, p in monthly.items()
        },
        "overall_average": round(sum(all_prices) / len(all_prices), 2) if all_prices else None,
        "total_nights": len(all_prices),
    }


@app.route("/api/scrape", methods=["POST"])
def scrape():
    data = request.get_json()
    hotel_name = (data.get("hotel_name") or "").strip()
    start_date = (data.get("start_date") or "").strip()
    end_date   = (data.get("end_date")   or "").strip()

    if not hotel_name or not start_date or not end_date:
        return jsonify({"error": "Missing required fields"}), 400

    try:
        s = datetime.strptime(start_date, "%Y-%m-%d")
        e = datetime.strptime(end_date,   "%Y-%m-%d")
        if e <= s:
            return jsonify({"error": "End date must be after start date"}), 400
    except ValueError:
        return jsonify({"error": "Invalid date format"}), 400

    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            results, debug = loop.run_until_complete(scrape_hotel_prices(hotel_name, start_date, end_date))
        finally:
            loop.close()
        stats = calculate_stats(results)
        return jsonify({
            "hotel": hotel_name,
            "start_date": start_date,
            "end_date": end_date,
            "results": results,
            "stats": stats,
            "debug": debug,
        })
    except Exception as e:
        import traceback
        return jsonify({"error": str(e), "trace": traceback.format_exc()}), 500


@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"})


if __name__ == "__main__":
    import os
    port = int(os.environ.get("PORT", 5050))
    app.run(debug=False, host="0.0.0.0", port=port)
