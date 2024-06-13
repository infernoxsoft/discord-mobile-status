import sys

sys.dont_write_bytecode = True


from modified_bot_instance import CustomBot
from discord import Intents
from os import getenv


bot = CustomBot(
    command_prefix="!",
    intents=Intents.all(),
    ws_identify_properties={
        "$os": sys.platform,
        "$browser": "Discord Android",
        "$device": "Discord Android",
        "$referrer": "",
        "$referring_domain": "",
    },
)


@bot.event
async def on_ready() -> None:
    print("Your bot is successfully started with mobile phone status. Check it out!")


bot.run(token=getenv("DISCORD_BOT_TOKEN", None))
