from pathlib import Path

import discord
from discord.ext import commands

class MusicBot(commands.Bot):
    def __init__(self):
        self._cogs = [p.stem for p in Path(".").glob("./bot/cogs/*.py")] # cogs loading
        super().__init__(command_prefix=self.prefix, case_insensitive=True, intensts=discord.Intents.all()) # prefix
        
    def setup(self):
        print("Settup running")
        
        for cog in self._cogs:
            self.load_extension(f"bot.cogs.{cog}")
            print(f"Loaded {cog} cog.")
        
        print("setup completed")
        
    def run(self):
        self.setup()
        
        with open("./bot/data/token.0", "r", encoding="UTF-8") as f: # token reading
            TOKEN = f.read()
        
        print("Running Bot")
        super().run(TOKEN, reconnect=True)
        
    async def shutdown(self):
        print("Shutdown bot connection")
        await super().close()
        
    async def close(self):
        print("Keyboard interrupt")
        await self.shutdown()
    
    async def on_connect(self):
        print("Bot connected to discord")
    
    async def on_resumed(self):
        print("Bot resumed")
        
    async def on_disconnect(self):
        print("Bot disconnected")
    
    async def on_ready(self):
        self.client_id = (await self.application_info()).id
        print("Bot is now ready to use.")
        print(35*"-")
        
    async def prefix(self, bot, msg):
        return commands.when_mentioned_or("`")(bot, msg) # prefix
    
    async def process_commands(self, msg):
        ctx = await self.get_context(msg, cls=commands.Context)
        
        if ctx.command is not None:
            await self.invoke(ctx)
            
    async def on_message(self, msg):
        if not msg.author.bot:
            await self.process_commands(msg)