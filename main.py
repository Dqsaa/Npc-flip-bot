import requests
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException
from flask import Flask, jsonify, render_template_string
from flask_socketio import SocketIO
import threading
import time
from datetime import datetime, timezone, timedelta

# Set up Flask-SocketIO server
app = Flask(__name__)
socketio = SocketIO(app)

options = Options()
options.add_argument('--headless')
options.add_argument('--disable-gpu')
options.add_argument('--no-sandbox')
options.add_argument('--disable-dev-shm-usage')

# Discord webhook URL
WEBHOOK_URL = "https://discord.com/api/webhooks/1328491060372181053/E7yKR0xmIzNH3x6Phj2Fq_LFP6jLL7K3N-Dut1kVZtbOEEjQ5rumOYfTdelPe_S0_LJ3"

# Store sent items with timestamps
sent_items = {}

EST = timezone(timedelta(hours=-5))


def emit_sent_items():
    """Send the current sent_items to all connected clients."""
    items = [
        {
            "name": name.split('-')[0],
            "coinsPerHour": details['coins_per_hour'],
            "maxProfit": details['max_profit'],
            # Convert timestamp to EST and format it as AM/PM
            "timestamp": details['timestamp'].astimezone(EST).strftime("%I:%M %p")
        }
        for name, details in sent_items.items()
    ]
    socketio.emit('update_sent_items', items)

def reset_storage():
    """Reset the sent_items storage every hour and notify clients."""
    global sent_items
    while True:
        time.sleep(3600)  # Wait for one hour
        sent_items = {}
        print("Storage reset.")
        emit_sent_items()

def send_to_discord(item_name, coins_per_hour, max_profit, image_url):
    """Send an embedded message to Discord and update sent_items."""
    global sent_items
    try:
        print(f"Preparing to send webhook for {item_name} to Discord...")
        embed = {
            "content": "<@715223773120430191> get flippin nih",
            "embeds": [
                {
                    "title": f"{item_name}",
                    "color": 0x00FF00,
                    "thumbnail": {"url": image_url},
                    "fields": [
                        {"name": "Coins per Hour", "value": f"{coins_per_hour:,} coins", "inline": True},
                        {"name": "Max Profit", "value": f"{max_profit:,} coins", "inline": True}
                    ]
                }
            ]
        }
        print(f"Webhook payload: {embed}")

        # Send the webhook request
        response = requests.post(WEBHOOK_URL, json=embed)
        print(f"Webhook response: {response.status_code}, {response.text}")

        if response.status_code != 204:
            print(f"Failed to send message to Discord: {response.status_code} {response.text}")
            return

        # Add item to sent_items and emit update
        item_key = f"{item_name}-{image_url}"
        sent_items[item_key] = {
            "coins_per_hour": coins_per_hour,
            "max_profit": max_profit,
            "timestamp": datetime.now()
        }
        print(f"Successfully sent webhook for {item_name}. Updating sent items...")
        emit_sent_items()
    except requests.exceptions.RequestException as e:
        print(f"Error sending webhook: {e}")
    except Exception as e:
        print(f"Unexpected error in send_to_discord: {e}")

def real_time_scraper():
    """Scrape data and send updates for items that pass filters."""
    global sent_items
    driver = webdriver.Chrome(options=options)
    url = "https://www.skyblock.bz/npc"
    driver.get(url)

    COINS_PER_HOUR_THRESHOLD = 10_000_000
    MAX_PROFIT_THRESHOLD = 20_000_000

    try:
        WebDriverWait(driver, 20).until(
            EC.presence_of_element_located((By.CLASS_NAME, 'edges'))
        )
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        time.sleep(2)

        cards = driver.find_elements(By.CLASS_NAME, 'card')
        print(f"Number of items found: {len(cards)}")

        for card in cards:
            try:
                item_name = card.find_element(By.CLASS_NAME, 'item-name').text
                details = card.find_element(By.CLASS_NAME, 'card_menu').text
                image_element = card.find_element(By.TAG_NAME, 'img')
                image_url = image_element.get_attribute('src')

                # Extract relevant data
                details_lines = details.split('\n')
                coins_per_hour = 0
                max_profit = 0

                for line in details_lines:
                    if "Coins per Hour" in line:
                        coins_per_hour = float(line.split(': ')[1].replace(',', '').replace(' coins', ''))
                    elif "Max Profit" in line:
                        max_profit = float(line.split(': ')[1].replace(',', '').replace(' coins', ''))

                # Apply filters
                if coins_per_hour >= COINS_PER_HOUR_THRESHOLD and max_profit >= MAX_PROFIT_THRESHOLD:
                    item_key = f"{item_name}-{image_url}"

                    # Check if item is already sent
                    if item_key not in sent_items:
                        # Send to Discord
                        send_to_discord(item_name, coins_per_hour, max_profit, image_url)

                        # Add to sent items
                        sent_items[item_key] = {
                            "coins_per_hour": coins_per_hour,
                            "max_profit": max_profit,
                            "timestamp": datetime.now()
                        }
                        emit_sent_items()
                        print(f"Sent to Discord: {item_name}")
            except NoSuchElementException:
                continue
    except TimeoutException:
        print("Error: The page took too long to load.")
    except Exception as e:
        print(f"Unexpected error: {e}")
    finally:
        driver.quit()

def run_scraper():
    while True:
        real_time_scraper()
        time.sleep(60)  # Pause between scrapes to avoid overloading the website

# Status route for UptimeRobot
@app.route('/status', methods=['GET'])
def status():
    return jsonify({"status": "running", "sent_items_count": len(sent_items)})

# Simple webpage route
@app.route('/')
def home():
    """Main webpage with real-time updates."""
    return render_template_string("""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>NPC Flipper</title>
        <script src="https://cdn.socket.io/4.0.0/socket.io.min.js"></script>
        <style>
            body { font-family: Arial, sans-serif; }
            table { width: 100%; border-collapse: collapse; }
            th, td { border: 1px solid #ddd; padding: 8px; text-align: left; }
            th { background-color: #f2f2f2; }
        </style>
    </head>
    <body>
        <h1>NPC Flipper</h1>
        <h2>Sent Items</h2>
        <table>
            <thead>
                <tr>
                    <th>Item Name</th>
                    <th>Coins per Hour</th>
                    <th>Max Profit</th>
                    <th>Timestamp</th>
                </tr>
            </thead>
            <tbody id="sent-items">
                <!-- Sent items will be dynamically inserted here -->
            </tbody>
        </table>
        <script>
            const socket = io();
            const sentItemsTable = document.getElementById('sent-items');

            // Listen for updates to sent_items
            socket.on('update_sent_items', (data) => {
                sentItemsTable.innerHTML = ''; // Clear the table
                data.forEach(item => {
                    const row = document.createElement('tr');
                    row.innerHTML = `
                        <td>${item.name}</td>
                        <td>${item.coinsPerHour.toLocaleString()} coins</td>
                        <td>${item.maxProfit.toLocaleString()} coins</td>
                        <td>${item.timestamp}</td>
                    `;
                    sentItemsTable.appendChild(row);
                });
            });
        </script>
    </body>
    </html>
    """)

if __name__ == "__main__":
    # Start the scraper thread
    scraper_thread = threading.Thread(target=run_scraper, daemon=True)
    scraper_thread.start()

    # Start the storage reset thread
    reset_thread = threading.Thread(target=reset_storage, daemon=True)
    reset_thread.start()

    print("Starting WebSocket server...")
    socketio.run(app, host='0.0.0.0', port=8080, use_reloader=False, log_output=True, allow_unsafe_werkzeug=True)
