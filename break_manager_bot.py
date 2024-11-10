import discord
from discord.ext import commands
import re
import os
import openai  # Import OpenAI for AI-powered responses
from keep_alive import keep_alive

# Replace with your bot's token and OpenAI API key
TOKEN = os.getenv("DISCORD_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

# Configure OpenAI API key
openai.api_key = OPENAI_API_KEY

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)

# Track users in queues
break_queue = []
adhoc_queue = []
offline_queue = []
time_slots = {}

MAX_BREAK = 3
MAX_ADHOC = 3
MAX_OFFLINE = 3
TOTAL_LIMIT = 5

time_pattern = re.compile(r"\b(will|at|in|around)?\s?(\d{1,2}[:.]\d{2})\b", re.IGNORECASE)

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

async def get_ai_response(user_message):
    """Get an AI response for a more conversational experience."""
    response = openai.Completion.create(
        model="text-davinci-003",
        prompt=(
            f"You are an assistant in charge of managing a break schedule. "
            f"People can go on 'break', 'adhoc', or 'offline' but only within limits. Respond to the following in a friendly and professional tone:\n\nUser: {user_message}\nAI:"
        ),
        max_tokens=50,
        temperature=0.7,
    )
    return response.choices[0].text.strip()

@bot.event
async def on_ready():
    print(f'Logged in as {bot.user}')

@bot.event
async def on_message(message):
    if message.author == bot.user:
        return

    content = message.content.lower()
    user = message.author.display_name

    match = time_pattern.search(content)
    if match:
        time_str = match.group(2)
        time_slot = time_str.strip()
        time_slots[user] = time_slot
        await message.channel.send(
            f"Thank you {user}, your time of {time_slot} has been acknowledged."
        )
        return

    if "back" in content or "did not" in content:
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
        return

    if "offline" in content:
        if user in break_queue or user in adhoc_queue or user in offline_queue:
            await message.channel.send(
                f"{user}, you're already in one of the queues."
            )
        elif can_go_offline():
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

    elif "status" in content:
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
        await message.channel.send(status_message)

    # AI response for more conversational interaction
    ai_response = await get_ai_response(message.content)
    await message.channel.send(ai_response)

keep_alive()
bot.run(TOKEN)
