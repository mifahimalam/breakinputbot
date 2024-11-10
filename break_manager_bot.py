import discord
from discord.ext import commands, tasks
import re  # Import regex for time matching
import os  # Importing the os library to access the token
from keep_alive import keep_alive  # Import the keep_alive function from the keep_alive.py file

# Replace with your bot's token
TOKEN = os.getenv("DISCORD_TOKEN")

intents = discord.Intents.default()
intents.message_content = True  # Enables reading message content

bot = commands.Bot(command_prefix="!", intents=intents)

# Track users in queues
break_queue = []
adhoc_queue = []
offline_queue = []
time_slots = {}  # Dictionary to store time slots for users

MAX_BREAK = 3
MAX_ADHOC = 3
MAX_OFFLINE = 3
TOTAL_LIMIT = 5

# Regex pattern to detect time mentions in the message (e.g., "at 6 PM", "in 10:30", etc.)
time_pattern = re.compile(r"\b(at|in|around)?\s?(\d{1,2}[:.]\d{2}|\d{1,2}\s?[APap][Mm])\b", re.IGNORECASE)

# Set up the designated channel ID for status updates
STATUS_CHANNEL_ID = 1305118324547653692  # Replace with your actual channel ID

# Functions to check if users can join the queues
def can_take_break():
    return len(break_queue) < MAX_BREAK and (len(break_queue) + len(adhoc_queue) + len(offline_queue)) < TOTAL_LIMIT

def can_take_adhoc():
    return len(adhoc_queue) < MAX_ADHOC and (len(break_queue) + len(adhoc_queue) + len(offline_queue)) < TOTAL_LIMIT

def can_go_offline():
    return len(offline_queue) < MAX_OFFLINE and (len(break_queue) + len(adhoc_queue) + len(offline_queue)) < TOTAL_LIMIT

def format_queue(queue_name, queue_list, max_limit):
    """Format queue list with Markdown styling."""
    queue_text = "\n".join([f"- {user}" for user in queue_list]) or "*None*"
    queue_count = len(queue_list)
    queue_status = f"**__{queue_name} ({queue_count}/{max_limit})__**\n{queue_text}\n"

    # Add warning if queue limit is reached
    if queue_count >= max_limit:
        queue_status += f"\n🚨 **__{queue_name.upper()} LIMIT REACHED!__** 🚨\n"
    return queue_status

@bot.event
async def on_ready():
    print(f'Logged in as {bot.user}')
    send_periodic_status.start()  # Start the periodic status update task after the bot is ready

@bot.event
async def on_message(message):
    if message.author == bot.user:
        return  # Ignore messages from the bot itself

    content = message.content.lower()  # Convert message content to lowercase for case-insensitive matching
    user = message.author.display_name  # Use display name instead of username

    # Check if the message contains a time-related request like "will take a break at 9:45"
    match = time_pattern.search(content)
    if match:
        time_str = match.group(2)  # Extract the time part (e.g., 9:45, 6 PM)
        time_slot = time_str.strip()  # Clean the time string (remove any spaces)

        # Store the time slot for the user
        time_slots[user] = time_slot

        await message.channel.send(f"Thank you {user}, your time of {time_slot} has been acknowledged. You have been added to the time schedule at that time.")

        # Prevent further processing, don't allow break/adhoc/other queue triggers
        return

    # Check if the message contains "back" or "did not" - prioritizing these keywords first
    if "back" in content or "did not" in content:
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

        if removed:
            await message.channel.send(
                f"**{user} has been removed from all queues as they are back or did not take action.**\n\n"
                f"{format_queue('Break Queue', break_queue, MAX_BREAK)}"
                f"{format_queue('Ad-hoc Queue', adhoc_queue, MAX_ADHOC)}"
                f"{format_queue('Offline Agents', offline_queue, MAX_OFFLINE)}"
            )
        else:
            await message.channel.send(f"{user}, you're not in any queue.")

        return  # Stop further processing to avoid triggering other commands like "break" or "offline"

    # Check if the message contains other commands (e.g., break, offline, adhoc)
    if "offline" in content:
        if user in break_queue or user in adhoc_queue or user in offline_queue:
            await message.channel.send(f"{user}, you're already in one of the queues. Please leave the current queue before joining another.")
        elif can_go_offline():
            # Remove user from all other queues if they're in one
            if user in break_queue:
                break_queue.remove(user)
            if user in adhoc_queue:
                adhoc_queue.remove(user)
            offline_queue.append(user)
            await message.channel.send(
                f"**{user} is now marked as offline.**\n\n"
                f"{format_queue('Break Queue', break_queue, MAX_BREAK)}"
                f"{format_queue('Ad-hoc Queue', adhoc_queue, MAX_ADHOC)}"
                f"{format_queue('Offline Agents', offline_queue, MAX_OFFLINE)}"
            )
        else:
            await message.channel.send("Offline limit reached. Please wait for someone to return.")

    elif "break" in content:
        if user in break_queue:
            await message.channel.send(f"{user}, you're already on break!")
        elif user in offline_queue or user in adhoc_queue:
            # Remove user from all other queues if they're in one
            if user in offline_queue:
                offline_queue.remove(user)
            if user in adhoc_queue:
                adhoc_queue.remove(user)
            break_queue.append(user)
            await message.channel.send(
                f"**{user} is now on break.**\n\n"
                f"{format_queue('Break Queue', break_queue, MAX_BREAK)}"
                f"{format_queue('Ad-hoc Queue', adhoc_queue, MAX_ADHOC)}"
                f"{format_queue('Offline Agents', offline_queue, MAX_OFFLINE)}"
            )
        elif can_take_break():
            break_queue.append(user)
            await message.channel.send(
                f"**{user} is now on break.**\n\n"
                f"{format_queue('Break Queue', break_queue, MAX_BREAK)}"
                f"{format_queue('Ad-hoc Queue', adhoc_queue, MAX_ADHOC)}"
                f"{format_queue('Offline Agents', offline_queue, MAX_OFFLINE)}"
            )
        else:
            await message.channel.send("Break limit reached. Please wait for someone to return.")

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
                f"{format_queue('Break Queue', break_queue, MAX_BREAK)}"
                f"{format_queue('Ad-hoc Queue', adhoc_queue, MAX_ADHOC)}"
                f"{format_queue('Offline Agents', offline_queue, MAX_OFFLINE)}"
            )
        elif can_take_adhoc():
            adhoc_queue.append(user)
            await message.channel.send(
                f"**{user} is now on ad-hoc work.**\n\n"
                f"{format_queue('Break Queue', break_queue, MAX_BREAK)}"
                f"{format_queue('Ad-hoc Queue', adhoc_queue, MAX_ADHOC)}"
                f"{format_queue('Offline Agents', offline_queue, MAX_OFFLINE)}"
            )
        else:
            await message.channel.send("Ad-hoc work limit reached. Please wait for someone to return.")

    else:
        await message.channel.send(f"Sorry, {user}. I didn't understand your request.")

    await bot.process_commands(message)

# Periodic status update task
@tasks.loop(minutes=5)
async def send_periodic_status():
    channel = bot.get_channel(STATUS_CHANNEL_ID)
    if channel:
        await channel.send(
            f"**Current Queue Status:**\n\n"
            f"{format_queue('Break Queue', break_queue, MAX_BREAK)}"
            f"{format_queue('Ad-hoc Queue', adhoc_queue, MAX_ADHOC)}"
            f"{format_queue('Offline Agents', offline_queue, MAX_OFFLINE)}"
        )

# Start the bot
keep_alive()
bot.run(TOKEN)
