import disnake
from disnake.ext import commands
import requests
import random
import difflib

# === CONFIG ===
TOKEN = "YOUR_DISCORD_BOT_TOKEN"
GROQ_API_KEY = "GROQ_API_KEY_HERE"
MODEL = "meta-llama/llama-4-scout-17b-16e-instruct"
POKETCG_API = "https://api.pokemontcg.io/v2/cards"

intents = disnake.Intents.all()
bot = commands.Bot(command_prefix=commands.when_mentioned_or("!"), intents=intents)

# === GET CARD DATA (FUZZY MATCHING) ===
def get_best_card(name):
    r = requests.get(f"{POKETCG_API}?q=name:{name}&pageSize=100")
    if r.status_code == 200 and r.json().get("data"):
        return r.json()["data"][0]
    else:
        # Try fuzzy match
        fallback = requests.get(f"{POKETCG_API}?pageSize=250")
        if fallback.status_code == 200 and fallback.json().get("data"):
            all_cards = fallback.json()["data"]
            names = [card["name"] for card in all_cards]
            closest = difflib.get_close_matches(name, names, n=1, cutoff=0.5)
            if closest:
                for card in all_cards:
                    if card["name"] == closest[0]:
                        return card
    return None

# === AI REPLY HANDLER ===
def ask_groq(question):
    try:
        res = requests.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={"Authorization": f"Bearer {GROQ_API_KEY}"},
            json={
                "model": MODEL,
                "messages": [
                    {"role": "system", "content": "You are a Pokémon TCG expert. Always include the official card image if a card is referenced. Only answer if pinged or replied to."},
                    {"role": "user", "content": question}
                ],
                "temperature": 0.7
            }
        )
        return res.json()["choices"][0]["message"]["content"]
    except Exception as e:
        return f"❌ Groq API Error: {e}"

# === MENTION/REPLY AI TRIGGER ===
@bot.event
async def on_message(message):
    if message.author.bot:
        return

    should_respond = (
        bot.user in message.mentions or
        (message.reference and message.reference.resolved and message.reference.resolved.author.id == bot.user.id)
    )

    if should_respond:
        async with message.channel.typing():
            content = message.content
            card = get_best_card(content)
            img_url = card['images']['large'] if card else None
            ai_response = ask_groq(f"Pokemon TCG Mode: {content}")
            if img_url:
                await message.reply(f"{ai_response}\n{img_url}")
            else:
                await message.reply(ai_response)

    await bot.process_commands(message)

# === /card ===
@bot.slash_command(description="Look up a Pokémon card (auto-corrects name).")
async def card(inter: disnake.ApplicationCommandInteraction, name: str):
    await inter.response.defer()
    card = get_best_card(name)
    if card:
        embed = disnake.Embed(
            title=card['name'],
            description=f"**Set:** {card['set']['name']}\n**Rarity:** {card.get('rarity', 'Unknown')}",
            color=0x2ECC71
        )
        embed.set_image(url=card['images']['large'])

        prices = card.get('tcgplayer', {}).get('prices', {})
        if 'normal' in prices and 'market' in prices['normal']:
            price = prices['normal']['market']
            embed.add_field(name="Market Price", value=f"${price:.2f}", inline=False)

        await inter.send(embed=embed)
    else:
        await inter.send("❌ Could not find a matching card.")

# === /pricecheck ===
@bot.slash_command(description="Check Pokémon card prices (auto-corrects name).")
async def pricecheck(inter: disnake.ApplicationCommandInteraction, name: str):
    await inter.response.defer()
    card = get_best_card(name)
    if card and 'tcgplayer' in card:
        prices = card['tcgplayer']['prices']
        embed = disnake.Embed(title=f"Prices for {card['name']}", color=0x3498DB)
        embed.set_image(url=card['images']['large'])

        for rarity in prices:
            if 'market' in prices[rarity]:
                embed.add_field(
                    name=f"{rarity.capitalize()} Market",
                    value=f"${prices[rarity]['market']:.2f}",
                    inline=True
                )
        await inter.send(embed=embed)
    else:
        await inter.send("❌ Price data not found.")

# === /openpack ===
@bot.slash_command(description="Open a simulated Pokémon pack from a set.")
async def openpack(inter: disnake.ApplicationCommandInteraction, set_name: str = "base1"):
    await inter.response.defer()
    r = requests.get(f"{POKETCG_API}?q=set.id:{set_name}&pageSize=100")
    if r.status_code == 200 and r.json().get("data"):
        all_cards = r.json()["data"]
        pack = random.sample(all_cards, min(10, len(all_cards)))
        embed = disnake.Embed(title=f"🃏 Simulated Pack from: {set_name}", color=0xE67E22)
        for card in pack:
            embed.add_field(name=card['name'], value=card.get('rarity', 'Unknown'), inline=True)
        embed.set_footer(text="Not real cards. Simulated pull.")
        await inter.send(embed=embed)
    else:
        await inter.send("❌ Could not open that set.")

# === READY ===
@bot.event
async def on_ready():
    print(f"✅ {bot.user} is online and ready!")

bot.run(TOKEN)
