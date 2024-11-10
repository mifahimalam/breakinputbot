import discord
from discord.ext import commands, tasks
import re
import os
from keep_alive import keep_alive

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

# Regex pattern to detect time mentions in the message
time_pattern = re.compile(r"\b(will|at|in|around)?\s?(\d{1,2}[:.]\d{2})\b", re.IGNORECASE)

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
    send_periodic_status.start()  # Start periodic status updates when the bot is ready

@bot.event
async def on_message(message):
    if message.author == bot.user:
        return  # Ignore messages from the bot itself

    content = message.content.lower()  # Convert message content to lowercase for case-insensitive matching
    user = message.author.display_name  # Use display name instead of username

    # Check if the message contains a time-related request like "will take a break at 9:45"
    match = time_pattern.search(content)
    if match:
        time_str = match.group(2)  # Extract the time part (e.g., 9:45)
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
            await update_status_in_channel()

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
            await update_status_in_channel()
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
            await update_status_in_channel()
        elif can_take_break():
            break_queue.append(user)
            await update_status_in_channel()
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
            await update_status_in_channel()
        elif can_take_adhoc():
            adhoc_queue.append(user)
            await update_status_in_channel()
        else:
            await message.channel.send("Ad-hoc work limit reached. Please wait for someone to return.")

    # No action on "status" command here, it will be handled by periodic update and queue changes

# Function for periodic status updates every 30 minutes
@tasks.loop(minutes=30)
async def send_periodic_status():
    await update_status_in_channel()

# Function to send the current status to a designated channel
async def update_status_in_channel():
    channel = bot.get_channel(1305118324547653692)  # Replace with the ID of the channel you want to send updates to
    total_away = len(break_queue) + len(adhoc_queue) + len(offline_queue)
    status_message = (
        f"**__Current Status__**\n\n"
        f"**Total Away:** {total_away}/{TOTAL_LIMIT}\n"
        f"{format_queue('Break Queue', break_queue, MAX_BREAK)}"
        f"{format_queue('Ad-hoc Queue', adhoc_queue, MAX_ADHOC)}"
        f"{format_queue('Offline Agents', offline_queue, MAX_OFFLINE)}"
    )
    if total_away >= TOTAL_LIMIT:
        status_message += "\n🚨 **__TOTAL LIMIT REACHED!__ NO MORE PEOPLE CAN BE AWAY!** 🚨"
    await channel.send(status_message)

# Start the keep-alive function
keep_alive()  # Call the keep_alive function to keep the bot alive
# Run the bot
bot.run(TOKEN)
