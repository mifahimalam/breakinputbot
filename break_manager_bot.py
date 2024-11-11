import discord
from discord.ext import commands, tasks
import re  # Import regex for time matching
import os  # Importing the os library to access the token
from keep_alive import keep_alive  # Import the keep_alive function from the keep_alive.py file
from datetime import datetime, time, timedelta

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
proposed_break_queue = []  # New queue for proposed breaks
proposed_time_slots = {}  # Dictionary to store time slots for proposed breaks

MAX_BREAK = 3
MAX_ADHOC = 3
MAX_OFFLINE = 3
TOTAL_LIMIT = 5

# Regex pattern to detect time mentions in various formats (e.g., "at 6:00 PM" or "around 14:30")
time_pattern = re.compile(r"\b(?:will|at|in|around|@)?\s?(\d{1,2})([:.]\d{2})?\s?(AM|PM|am|pm)?\b", re.IGNORECASE)

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

def format_proposed_break_queue():
    """Format the Proposed Break Queue list."""
    proposed_break_text = "\n".join(
        [f"- {user} at {proposed_time_slots[user]}" for user in proposed_break_queue]
    ) or "*None*"
    return f"**__Proposed Break Queue__**\n{proposed_break_text}\n"

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

    # Check if the message contains "break at 6 PM" or similar, and trigger break action
    if "at" in content:
        # Check for time-related request, e.g., "break at 6 PM"
        match = time_pattern.search(content)
        if match:
            hour = match.group(1)
            minute = match.group(2) if match.group(2) else ":00"  # Default to :00 if no minute is given
            period = match.group(3).upper() if match.group(3) else ""

            time_slot = f"{hour}{minute} {period}".strip()  # Format time string

            # Store the time slot for the user in the proposed break queue
            proposed_break_queue.append(user)
            proposed_time_slots[user] = time_slot

            await message.channel.send(
                f"Thanks {user} bro! Your proposed break time of {time_slot} has been recorded. Take a chill pill! "
                f"You are now in the Proposed Break Queue. Don't worry!"
            )
            return  # Stop further processing to avoid triggering other commands

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
        if user in proposed_break_queue:
            proposed_break_queue.remove(user)
            removed = True

        if removed:
            await message.channel.send(
                f"**Our bro, {user} is now back and will do whatever they were doing before!!! Hip, hip, hurray!!!**\n\n"
                f"{format_proposed_break_queue()}"
                f"{format_queue('Break Queue', break_queue, MAX_BREAK)}"
                f"{format_queue('Ad-hoc Queue', adhoc_queue, MAX_ADHOC)}"
                f"{format_queue('Offline Agents', offline_queue, MAX_OFFLINE)}"
            )
        else:
            await message.channel.send(f"{user} bro, you're not in any queue. Chill homie!")

        return  # Stop further processing to avoid triggering other commands like "break" or "offline"

    # Check if the message contains other commands (e.g., break, offline, adhoc)
    if "offline" in content:
        if user in break_queue or user in adhoc_queue or user in offline_queue:
            await message.channel.send(f"{user} bro, you're already in one of the queues. You have to leave the current queue before joining another.")
        elif can_go_offline():
            # Remove user from all other queues if they're in one
            if user in break_queue:
                break_queue.remove(user)
            if user in adhoc_queue:
                adhoc_queue.remove(user)
            offline_queue.append(user)
            await message.channel.send(
                f"**{user} bro is now marked as offline! Rest of us, keep working!**\n\n"
                f"{format_proposed_break_queue()}"
                f"{format_queue('Break Queue', break_queue, MAX_BREAK)}"
                f"{format_queue('Ad-hoc Queue', adhoc_queue, MAX_ADHOC)}"
                f"{format_queue('Offline Agents', offline_queue, MAX_OFFLINE)}"
            )
        else:
            await message.channel.send("Bro! Offline limit reached. Please wait for someone to return.")

    elif "break" in content:
        if user in break_queue:
            await message.channel.send(f"{user} bro, chill! You're already on a break my homie!")
        elif user in offline_queue or user in adhoc_queue:
            # Remove user from all other queues if they're in one
            if user in offline_queue:
                offline_queue.remove(user)
            if user in adhoc_queue:
                adhoc_queue.remove(user)
            break_queue.append(user)
            await message.channel.send(
                f"**{user} bro is now on break! Let's keep it together!**\n\n"
                f"{format_proposed_break_queue()}"
                f"{format_queue('Break Queue', break_queue, MAX_BREAK)}"
                f"{format_queue('Ad-hoc Queue', adhoc_queue, MAX_ADHOC)}"
                f"{format_queue('Offline Agents', offline_queue, MAX_OFFLINE)}"
            )
        elif can_take_break():
            break_queue.append(user)
            await message.channel.send(
                f"**{user} bro is now on break! Let's keep it together!**\n\n"
                f"{format_proposed_break_queue()}"
                f"{format_queue('Break Queue', break_queue, MAX_BREAK)}"
                f"{format_queue('Ad-hoc Queue', adhoc_queue, MAX_ADHOC)}"
                f"{format_queue('Offline Agents', offline_queue, MAX_OFFLINE)}"
            )
        else:
            await message.channel.send("Bro! Please! Break limit reached. Wait for someone to return? Thanks mate!")

    elif "adhoc" in content:
        if user in adhoc_queue:
            await message.channel.send(f"{user} bro, you're already on ad-hoc work! Chill!")
        elif user in break_queue or user in offline_queue:
            # Remove user from all other queues if they're in one
            if user in break_queue:
                break_queue.remove(user)
            if user in offline_queue:
                offline_queue.remove(user)
            adhoc_queue.append(user)
            await message.channel.send(
                f"**{user} bro is now on ad-hoc work. Rest of us, keep working!!!**\n\n"
                f"{format_proposed_break_queue()}"
                f"{format_queue('Break Queue', break_queue, MAX_BREAK)}"
                f"{format_queue('Ad-hoc Queue', adhoc_queue, MAX_ADHOC)}"
                f"{format_queue('Offline Agents', offline_queue, MAX_OFFLINE)}"
            )
        elif can_take_adhoc():
            adhoc_queue.append(user)
            await message.channel.send(
                f"**{user} bro is now on ad-hoc work. Rest of us, keep working!!!**\n\n"
                f"{format_proposed_break_queue()}"
                f"{format_queue('Break Queue', break_queue, MAX_BREAK)}"
                f"{format_queue('Ad-hoc Queue', adhoc_queue, MAX_ADHOC)}"
                f"{format_queue('Offline Agents', offline_queue, MAX_OFFLINE)}"
            )
        else:
            await message.channel.send("My bro! Ad-hoc work limit reached. Please do you ad-hoc after someone is done with thiers.")

    # Handle "status" command if "back" or "did not" was not in the message
    elif "status" in content:
        total_away = len(break_queue) + len(adhoc_queue) + len(offline_queue)
        status_message = f"{format_proposed_break_queue()}" \
                         f"{format_queue('Break Queue', break_queue, MAX_BREAK)}" \
                         f"{format_queue('Ad-hoc Queue', adhoc_queue, MAX_ADHOC)}" \
                         f"{format_queue('Offline Agents', offline_queue, MAX_OFFLINE)}" \
                         f"\n**Total Away from chat: {total_away}/{TOTAL_LIMIT}**"
        await message.channel.send(status_message)

@tasks.loop(minutes=60)  # Task runs every 60 minutes
async def send_periodic_status():
    # Get current time in GMT+6
    now = datetime.utcnow() + timedelta(hours=6)
    start_time = time(13, 15)  # 1:15 PM
    end_time = time(21, 45)    # 9:45 PM

    # Check if current time is within the desired time range
    if start_time <= now.time() <= end_time:
        channel = bot.get_channel(STATUS_CHANNEL_ID)
        if channel is None:
            print("BRO WHERE IS THE STATUS CHANNEL?")
            return

        total_away = len(break_queue) + len(adhoc_queue) + len(offline_queue)
        status_message = f"**Periodic Status Update:**\n" \
                         f"{format_proposed_break_queue()}" \
                         f"{format_queue('Break Queue', break_queue, MAX_BREAK)}" \
                         f"{format_queue('Ad-hoc Queue', adhoc_queue, MAX_ADHOC)}" \
                         f"{format_queue('Offline Agents', offline_queue, MAX_OFFLINE)}" \
                         f"\n**Total Away from chat: {total_away}/{TOTAL_LIMIT}**"

        await channel.send(status_message)

# Start the bot
keep_alive()
bot.run(TOKEN)
