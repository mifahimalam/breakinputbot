import discord
from discord.ext import commands, tasks
import re
import os
import json
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime, time, timedelta
from keep_alive import keep_alive

# Replace with your bot's token
TOKEN = os.getenv("DISCORD_TOKEN")

# Setup Google Sheets API connection
def connect_to_google_sheets():
    creds_json = os.getenv("GOOGLE_SHEET_CREDS")
    credentials = json.loads(creds_json)
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    service_account_credentials = ServiceAccountCredentials.from_json_keyfile_dict(credentials, scope)
    client = gspread.authorize(service_account_credentials)
    return client

# Connect to Google Sheets
google_client = connect_to_google_sheets()
spreadsheet = google_client.open("Break Input Manager Database")  # Replace with your sheet name
offline_sheet = spreadsheet.worksheet("Offline Queue Database")
break_sheet = spreadsheet.worksheet("Break Queue Database")

intents = discord.Intents.default()
intents.message_content = True  # Enables reading message content

bot = commands.Bot(command_prefix="!", intents=intents)

# Track users in queues
break_queue = []
adhoc_queue = []
offline_queue = []
time_slots = {}  # Dictionary to store time slots for users
proposed_break_queue = []  # New queue for proposed breaks
proposed_time_slots = {}  # Dictionary to store time slots for proposed breaks

MAX_BREAK = 3
MAX_ADHOC = 3
MAX_OFFLINE = 3
TOTAL_LIMIT = 5

# Regex pattern to detect time mentions
time_pattern = re.compile(r"\b(?:will|at|in|around|@)?\s?(\d{1,2})([:.]\d{2})?\s?(AM|PM|am|pm)?\b", re.IGNORECASE)

# Designated channel for status updates
STATUS_CHANNEL_ID = 1305118324547653692  # Replace with your actual channel ID

# Functions to log data in Google Sheets
def log_to_sheet(sheet, username, action_time):
    """Log user action to Google Sheets."""
    sheet.append_row([username, action_time])

def record_offline(user):
    """Record the user going offline."""
    action_time = (datetime.utcnow() + timedelta(hours=6)).strftime("%Y-%m-%d %H:%M:%S")
    log_to_sheet(offline_sheet, user, action_time)

def record_break(user):
    """Record the user going on break."""
    action_time = (datetime.utcnow() + timedelta(hours=6)).strftime("%Y-%m-%d %H:%M:%S")
    log_to_sheet(break_sheet, user, action_time)

# Functions for queue management
def can_take_break():
    return len(break_queue) < MAX_BREAK and (len(break_queue) + len(adhoc_queue) + len(offline_queue)) < TOTAL_LIMIT

def can_take_adhoc():
    return len(adhoc_queue) < MAX_ADHOC and (len(break_queue) + len(adhoc_queue) + len(offline_queue)) < TOTAL_LIMIT

def can_go_offline():
    return len(offline_queue) < MAX_OFFLINE and (len(break_queue) + len(adhoc_queue) + len(offline_queue)) < TOTAL_LIMIT

def format_queue(queue_name, queue_list, max_limit):
    queue_text = "\n".join([f"- {user}" for user in queue_list]) or "*None*"
    queue_count = len(queue_list)
    queue_status = f"**__{queue_name} ({queue_count}/{max_limit})__**\n{queue_text}\n"
    if queue_count >= max_limit:
        queue_status += f"\n🚨 **__{queue_name.upper()} LIMIT REACHED!__** 🚨\n"
    return queue_status

def format_proposed_break_queue():
    proposed_break_text = "\n".join(
        [f"- {user} at {proposed_time_slots[user]}" for user in proposed_break_queue]
    ) or "*None*"
    return f"**__Proposed Break Queue__**\n{proposed_break_text}\n"

@bot.event
async def on_ready():
    print(f'Logged in as {bot.user}')
    send_periodic_status.start()

@bot.event
async def on_message(message):
    if message.author == bot.user:
        return

    content = message.content.lower()
    user = message.author.display_name

    # Handle proposed break queue
    if "at" in content:
        match = time_pattern.search(content)
        if match:
            hour = match.group(1)
            minute = match.group(2) if match.group(2) else ":00"
            period = match.group(3).upper() if match.group(3) else ""
            time_slot = f"{hour}{minute} {period}".strip()

            if user in proposed_time_slots and proposed_time_slots[user] == time_slot:
                await message.channel.send(
                    f"{user}, you've already proposed this break time ({time_slot}). No changes made."
                )
            elif user in proposed_time_slots:
                previous_time = proposed_time_slots[user]
                proposed_time_slots[user] = time_slot
                await message.channel.send(
                    f"{user}, your break time has been updated from {previous_time} to {time_slot}."
                )
            else:
                proposed_break_queue.append(user)
                proposed_time_slots[user] = time_slot
                await message.channel.send(
                    f"{user}, your proposed break time ({time_slot}) has been recorded."
                )
            return
    # Check if the message contains "back" or "did not" - prioritizing these keywords first
    if "back" in content or "did not" in content or "online" in content:
        # Remove the user from all queues (break, adhoc, offline)
        removed = False
        if user in break_queue:
            break_queue.remove(user)
            removed = True
        if user in adhoc_queue:
            adhoc_queue.remove(user)
            removed = True
        if user in offline_queue:
            offline_queue.remove(user)
            removed = True
        if user in proposed_break_queue:
            proposed_break_queue.remove(user)
            removed = True

        if removed:
            await message.channel.send(
                f"**{user} is now back to their original work.**\n\n"
                f"{format_proposed_break_queue()}"
                f"{format_queue('Break Queue', break_queue, MAX_BREAK)}"
                f"{format_queue('Ad-hoc Queue', adhoc_queue, MAX_ADHOC)}"
                f"{format_queue('Offline Agents', offline_queue, MAX_OFFLINE)}"
            )
        else:
            await message.channel.send(f"{user}, you're not in any queue.")

            return  # Stop further processing to avoid triggering other commands like "break" or "offline"

    # Handle offline queue
    if "offline" in content:
        if user in offline_queue:
            await message.channel.send(f"{user}, you're already marked as offline.")
        elif can_go_offline():
            offline_queue.append(user)
            record_offline(user)
            await message.channel.send(
                f"{user} is now offline.\n\n"
                f"{format_proposed_break_queue()}"
                f"{format_queue('Break Queue', break_queue, MAX_BREAK)}"
                f"{format_queue('Ad-hoc Queue', adhoc_queue, MAX_ADHOC)}"
                f"{format_queue('Offline Agents', offline_queue, MAX_OFFLINE)}"
            )
        else:
            await message.channel.send("Offline limit reached. Please wait for someone to return.")

    # Handle break queue
    elif "break" in content:
        if user in break_queue:
            await message.channel.send(f"{user}, you're already on break.")
        elif can_take_break():
            break_queue.append(user)
            record_break(user)
            await message.channel.send(
                f"{user} is now on break.\n\n"
                f"{format_proposed_break_queue()}"
                f"{format_queue('Break Queue', break_queue, MAX_BREAK)}"
                f"{format_queue('Ad-hoc Queue', adhoc_queue, MAX_ADHOC)}"
                f"{format_queue('Offline Agents', offline_queue, MAX_OFFLINE)}"
            )
        else:
            await message.channel.send("Break limit reached. Please wait for someone to return.")
            
    # Handle break queue
    elif "adhoc" in content:
        if user in adhoc_queue:
            await message.channel.send(f"{user}, you're already on ad-hoc work!")
        elif user in break_queue or user in offline_queue:
            # Remove user from all other queues if they're in one
            if user in break_queue:
                break_queue.remove(user)
            if user in offline_queue:
                offline_queue.remove(user)
            adhoc_queue.append(user)
            await message.channel.send(
                f"**{user} is now on ad-hoc work.**\n\n"
                f"{format_proposed_break_queue()}"
                f"{format_queue('Break Queue', break_queue, MAX_BREAK)}"
                f"{format_queue('Ad-hoc Queue', adhoc_queue, MAX_ADHOC)}"
                f"{format_queue('Offline Agents', offline_queue, MAX_OFFLINE)}"
            )
        elif can_take_adhoc():
            adhoc_queue.append(user)
            await message.channel.send(
                f"**{user} is now on ad-hoc work.**\n\n"
                f"{format_proposed_break_queue()}"
                f"{format_queue('Break Queue', break_queue, MAX_BREAK)}"
                f"{format_queue('Ad-hoc Queue', adhoc_queue, MAX_ADHOC)}"
                f"{format_queue('Offline Agents', offline_queue, MAX_OFFLINE)}"
            )
        else:
            await message.channel.send("Ad-hoc work limit reached. Please do your ad-hoc after someone is done with theirs.")

    # Handle "status" command if "back" or "did not" was not in the message
    elif "status" in content:
        total_away = len(break_queue) + len(adhoc_queue) + len(offline_queue)
        status_message = f"{format_proposed_break_queue()}" \
                         f"{format_queue('Break Queue', break_queue, MAX_BREAK)}" \
                         f"{format_queue('Ad-hoc Queue', adhoc_queue, MAX_ADHOC)}" \
                         f"{format_queue('Offline Agents', offline_queue, MAX_OFFLINE)}" \
                         f"\n**Total Away from chat: {total_away}/{TOTAL_LIMIT}**"
        await message.channel.send(status_message)

@tasks.loop(minutes=30)
async def send_periodic_status():
    now = datetime.utcnow() + timedelta(hours=6)
    start_time = time(13, 15)
    end_time = time(21, 45)

    if start_time <= now.time() <= end_time:
        channel = bot.get_channel(STATUS_CHANNEL_ID)
        if channel:
            total_away = len(break_queue) + len(adhoc_queue) + len(offline_queue)
            status_message = f"**30-Minute Status Update:**\n" \
                             f"{format_proposed_break_queue()}" \
                             f"{format_queue('Break Queue', break_queue, MAX_BREAK)}" \
                             f"{format_queue('Ad-hoc Queue', adhoc_queue, MAX_ADHOC)}" \
                             f"{format_queue('Offline Agents', offline_queue, MAX_OFFLINE)}" \
                             f"\n**Total Away from chat: {total_away}/{TOTAL_LIMIT}**"
            await channel.send(status_message)

# Start the bot
keep_alive()
bot.run(TOKEN)
