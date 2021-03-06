# imports
import typing as t
import re
import datetime as dt
import asyncio
import random
from enum import Enum

import discord
import wavelink
from discord.ext import commands

from ..data.langs import music_py as mp


#global vars
URL_REGEX = r"(?i)\b((?:https?://|www\d{0,3}[.]|[a-z0-9.\-]+[.][a-z]{2,4}/)(?:[^\s()<>]+|\(([^\s()<>]+|(\([^\s()<>]+\)))*\))+(?:\(([^\s()<>]+|(\([^\s()<>]+\)))*\)|[^\s`!()\[\]{};:'\".,<>?«»“”‘’]))"
OPTIONS = { # choose track options 1-5
    "1️⃣": 0,
    "2⃣": 1,
    "3⃣": 2,
    "4⃣": 3,
    "5⃣": 4,
}

colour_info = 0x5bc0de  # blue info colour
colour_error = 0xdc3545  # red warning colour


# errors
class AlreadyConnectedToChannel(commands.CommandError):
    pass


class NoVoiceChannel(commands.CommandError):
    pass


class QueueIsEmpty(commands.CommandError):
    pass


class NoTracksFound(commands.CommandError):
    pass


class PlayerIsAlreadyPaused(commands.CommandError):
    pass


class PlayerIsAlreadyPlaying(commands.CommandError):
    pass


class NoMoreTracks(commands.CommandError):
    pass


class NoPreviousTracks(commands.CommandError):
    pass


class InvalidRepeatMode(commands.CommandError):
    pass


class RepeatMode(Enum):
    NONE = 0
    ONE = 1
    ALL = 2
    

# Queue class
class Queue:
    def __init__(self):
        self._queue = []
        self.position = 0
        self.repeat_mode = RepeatMode.NONE
        
    @property
    def is_empty(self):
        return not self._queue
    
    @property  # current track in queue
    def current_track(self):
        if not self._queue:
            raise QueueIsEmpty
        
        if self.position <= len(self._queue) -1:
            return self._queue[self.position]
    
    @property  # next tracks in queue
    def upcoming(self):
        if not self._queue:
            raise QueueIsEmpty
        
        return self._queue[self.position + 1:]
    
    @property  # tracks played in past
    def history(self):
        if not self._queue:
            raise QueueIsEmpty
        
        return self._queue[:self.position]
    
    @property  # length of queue
    def length(self):
        return len(self._queue)

    def add(self, *args):
        self._queue.extend(args)  # extends queue with track/tracks
    
    def get_next_track(self):
        if not self._queue:
            raise QueueIsEmpty
        
        self.position += 1

        if self.position < 0:
            return None
        elif self.position > len(self._queue)-1:  # check if there's no songs left
            if self.repeat_mode == RepeatMode.ALL:
                self.position = 0
            else:
                return None
        
        return self._queue[self.position]
    
    def shuffle(self):
        if not self._queue:
            raise QueueIsEmpty
        
        upcoming = self._queue  # to shuffle just upcoming tracks not all queue with history
        random.shuffle(upcoming)
        self._queue = self._queue[:self.position + 1]
        self._queue.extend(upcoming)
        
    def set_repeat_mode(self, mode):
        if mode in ["none", "0"]:
            self.repeat_mode = RepeatMode.NONE
        if mode in ["1", "one"]:
            self.repeat_mode = RepeatMode.ONE
        if mode == "all":
            self.repeat_mode = RepeatMode.ALL

    def empty(self):  # clearing queue
        self.position = 0
        self._queue.clear()


# custom Player class with full queue
class Player(wavelink.Player):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.queue = Queue()
        
    async def connect(self, ctx, channel=None):
        if self.is_connected:  # check for player connected
            raise AlreadyConnectedToChannel
        
        if (channel := getattr(ctx.author.voice, "channel", channel)) is None:  # check
            raise NoVoiceChannel
        
        await super().connect(channel.id)  # connecting to voice channel
        return channel
    
    async def p_disconnect(self):
        try:
            await self.destroy()  # destroy player while disconnecting
        except KeyError:
            pass
        
    async def add_tracks(self, ctx, tracks):
        if not tracks:
            raise NoTracksFound
        
        if isinstance(tracks, wavelink.TrackPlaylist):
            self.queue.add(*tracks.tracks)
        elif len(tracks) == 1:
            self.queue.add(tracks[0])
            embed = discord.Embed(title=f"{mp['added_tracks']} `{tracks[0].title}`.", colour=colour_info)
            await ctx.send(embed=embed)
        else:
            if (track := await self.choose_track(ctx, tracks)) is not None:
                self.queue.add(track)
                embed = discord.Embed(title=f"{mp['added_tracks']} `{tracks[0].title}`.", colour=colour_info)
                await ctx.send(embed=embed)
        
        if not self.is_playing and not self.queue.is_empty:
            await self.start_playback()
            
    async def choose_track(self, ctx, tracks):
        def _check(r, u):
            return (
                r.emoji in OPTIONS.keys()
                and u == ctx.author
                and r.message.id == msg.id
            )
            
        embed = discord.Embed(
            title = f"{mp['choose_track']}",
            description = (
                "\n".join(
                    f"**{1+i}.** {t.title} ({t.length//60000}:{str(t.length%60).zfill(2)})"  # (fix hours issue)
                    for i, t in enumerate(tracks[:5])
                )    
            ),
            colour = ctx.author.colour,
            timestamp=dt.datetime.utcnow()
        )
        embed.set_author(name=f"{mp['query_results']}")
        embed.set_footer(text=f"{mp['invoke']} {ctx.author.display_name}", icon_url=ctx.author.avatar_url)
        
        msg = await ctx.send(embed=embed)  # msg variable for check function
        for emoji in list(OPTIONS.keys())[:min(len(tracks), len(OPTIONS))]:
            await msg.add_reaction(emoji)
        try:
            reaction, _ = await self.bot.wait_for("reaction_add", timeout=60, check=_check)
        except  asyncio.TimeoutError:
            await msg.delete()
            await ctx.message.delete()
        else:
            await msg.delete()
            return tracks[OPTIONS[reaction.emoji]]
            
    async def start_playback(self):
        await self.play(self.queue.current_track)
        
    async def advance(self):
        try:
            if (track := self.queue.get_next_track()) is not None:
                await self.play(track)
        except QueueIsEmpty:
            pass
        
    async def repeat_track(self):
        await self.play(self.queue.current_track)
        
        
class Music(commands.Cog, wavelink.WavelinkMixin):
    def __init__(self, bot):
        self.bot = bot
        self.wavelink = wavelink.Client(bot=bot)
        self.bot.loop.create_task(self.start_nodes())
        
    @commands.Cog.listener() # checking for member left
    async def on_voice_state_update(self, member, before, after):
        if not member.bot and after.channel is None:
            if not [m for m in before.channel.members if not m.bot]:
                pass
                # set delay before leaving if there's no member in voice channel
    
    @wavelink.WavelinkMixin.listener()
    async def on_node_ready(self, node):
        print(f"Wavelink is now connected {node.identifier}")  # connected wavelink to the node MAIN
        
    @wavelink.WavelinkMixin.listener("on_track_stuck")
    @wavelink.WavelinkMixin.listener("on_track_end")
    @wavelink.WavelinkMixin.listener("on_track_exception")
    async def on_player_stop(self, node, payload):  # player stop errors handling
        if payload.player.queue.repeat_mode == RepeatMode.ONE:
            await payload.player.repeat_track()
        else:
            await payload.player.advance()
        
    async def cog_check(self, ctx):  # it will check every commands in the cog
        if isinstance(ctx.channel, discord.DMChannel):
            embed = discord.Embed(title=f"{mp['dm_error']}", colour=colour_error)
            await ctx.send(embed=embed)
            return False
        
        return True
    
    async def start_nodes(self):
        await self.bot.wait_until_ready()
        
        nodes = {
            "MAIN": {
                "host": "127.0.0.1",
                "port": 2333,
                "rest_uri": "http://127.0.0.1:2333",
                "password": "youshallnotpass",
                "identifier": "MAIN",
                "region": "europe",
            }
        }
        
        for node in nodes.values():
            await self.wavelink.initiate_node(**node)
        
    def get_player(self, obj):
        if isinstance(obj, commands.Context):
            return self.wavelink.get_player(obj.guild.id, cls=Player, context=obj)
        
        elif isinstance(obj, discord.Guild):
            return self.wavelink.get_player(obj.id, cls=Player)
        
    # commands
    @commands.command(name="connect", aliases=['join'])
    async def connect(self, ctx, *, channel: t.Optional[discord.VoiceChannel]):
        # if no channel defined bot will join user's channel
        player = self.get_player(ctx)
        channel = await player.connect(ctx, channel)
        embed = discord.Embed(title=f"{mp['connected_to']} {channel.name}.", colour=colour_info)
        await ctx.send(embed=embed)
        
    @connect.error
    async def connect_command_error(self, ctx, exc):
        if isinstance(exc, AlreadyConnectedToChannel):
            embed = discord.Embed(title=f"{mp['already_connected_error']}", colour=colour_error)
            await ctx.send(embed=embed)
        elif isinstance(exc, NoVoiceChannel):
            embed = discord.Embed(title=f"{mp['no_voice_channel_error']}", colour=colour_error)
            await ctx.send(embed=embed)
            
    @commands.command(name="disconnect", aliases=['leave'])
    async def disconnect(self, ctx):
        player = self.get_player(ctx)
        await player.p_disconnect()
        
        embed=discord.Embed(title=f"{mp['disconnect_from']}", colour=colour_info)
        await ctx.send(embed=embed)
        
    @commands.command(name="play", aliases=['p'])
    async def play(self, ctx, *, query: t.Optional[str]): # with optional no need to add resume command
        player = self.get_player(ctx)
        
        if not player.is_connected:
            await player.connect(ctx)
            
        if query is None:           
            if player.queue.is_empty:
                raise QueueIsEmpty
            
            await player.set_pause(False)
            embed = discord.Embed(title=f"{mp['resumed']}", colour=colour_info)
            await ctx.send(embed=embed)
        
        else:
            query = query.strip("<>")  # prevent stopping embed creating
            if not query == "":
                if not re.match(URL_REGEX, query):
                    query = f"ytsearch:{query}"
                
                await player.add_tracks(ctx, await self.wavelink.get_tracks(query))  # wavelink finding the song
            else:
                pass   
            
    @play.error
    async def play_command_error(self, ctx, exc):
        if isinstance(exc, QueueIsEmpty):
            embed = discord.Embed(title=f"{mp['queue_empty_error']}", colour=colour_error)
            await ctx.send(embed=embed)

    @commands.command(name="pause")
    async def pause(self, ctx):
        player = self.get_player(ctx)
        
        if player.is_paused:
            raise PlayerIsAlreadyPaused
        
        await player.set_pause(True)
        embed = discord.Embed(title=f"{mp['paused']}", colour=colour_info)
        await ctx.send(embed=embed)
        
    @pause.error
    async def pause_command_error(self, ctx, exc):
        if isinstance(exc, PlayerIsAlreadyPaused):
            embed=discord.Embed(title=f"{mp['already_paused_error']}", colour=colour_error)
            await ctx.send(embed=embed)
    
    @commands.command(name="stop")
    async def stop(self, ctx):
        player = self.get_player(ctx)
        player.queue.empty()
        await player.stop()
        embed = discord.Embed(title=f"{mp['stopped']}", colour=colour_info)
        await ctx.send(embed=embed)
        
    @commands.command("next", aliases=['skip', 'forceskip', 'fs', 'n'])
    async def next(self, ctx):
        player = self.get_player(ctx)
        
        if not player.queue.upcoming:
            raise NoMoreTracks

        await player.stop()
        embed=discord.Embed(title=f"{mp['skipped']}", colour=colour_info)
        await ctx.send(embed=embed)
        
    @next.error
    async def next_command_error(self, ctx, exc):
        if isinstance(exc, QueueIsEmpty):
            embed = discord.Embed(title=f"{mp['queue_empty_error']}", colour=colour_error)
            await ctx.send(embed=embed)
        elif isinstance(exc, NoMoreTracks):
            embed = discord.Embed(title=f"{mp['no_more_tracks_error']}", colour=colour_error)
            await ctx.send(embed=embed)
            
    @commands.command("previous", aliases=['prev'])
    async def previous(self, ctx):
        player = self.get_player(ctx)
        
        if not player.queue.history:
            raise NoPreviousTracks

        player.queue.position -= 2
        await player.stop()
        embed=discord.Embed(title=f"{mp['previous']}", colour=colour_info)
        await ctx.send(embed=embed)
        
    @previous.error
    async def previous_command_error(self, ctx, exc):
        if isinstance(exc, QueueIsEmpty):
            embed = discord.Embed(title=f"{mp['queue_empty_error']}", colour=colour_error)
            await ctx.send(embed=embed)
        elif isinstance(exc, NoPreviousTracks):
            embed = discord.Embed(title=f"{mp['no_previous_tracks_error']}", colour=colour_error)
            await ctx.send(embed=embed)
            
    @commands.command(name="shuffle")
    async def shuffle(self, ctx):
        player = self.get_player(ctx)
        player.queue.shuffle()
        embed=discord.Embed(title=f"{mp['shuffled']}", colour=colour_info)
        await ctx.send(embed=embed)
        
    @shuffle.error
    async def shuffle_command_error(self, ctx, exc):
        if isinstance(exc, QueueIsEmpty):
            embed=discord.Embed(title=f"{mp['queue_empty_error']}", colour=colour_error)
            await ctx.send(embed=embed)
            
    @commands.command(name="repeat", aliases=['loop'])
    async def repeat(self, ctx, mode: str):
        if mode not in ("none", "1", "all"):
            raise InvalidRepeatMode
        
        player = self.get_player(ctx)
        player.queue.set_repeat_mode(mode)
        embed=discord.Embed(title=f"{mp['repeat_mode']} {mode}.", colour=colour_info)
        await ctx.send(embed=embed)

    @commands.command(name="queue", aliases=['q'])
    async def queue(self, ctx, show: t.Optional[int] = 10):
        player = self.get_player(ctx)
        
        if player.queue.is_empty:
            raise QueueIsEmpty
        
        embed = discord.Embed(
            title=f"{mp['q_title']}",
            description=f"{mp['q_description']}",
            colour=ctx.author.colour,
            timestamp=dt.datetime.utcnow()
        )
        embed.set_author(name="")
        embed.set_footer(text=f"{mp['invoke']} {ctx.author.display_name}", icon_url=ctx.author.avatar_url)
        embed.add_field(name=f"{mp['q_current']}", 
                        value=player.queue.current_track.title,
                        inline=False
                        )
        if upcoming := player.queue.upcoming:
            embed.add_field(
                name=f"{mp['q_next']}",
                value="\n".join(t.title for t in upcoming[:show]),
                inline=False,
            )

        await ctx.send(embed=embed)
        
    @queue.error
    async def queue_command_error(self, ctx, exc):
        if isinstance(exc, QueueIsEmpty):
            embed=discord.Embed(title=f"{mp['queue_empty_error']}", colour=colour_error)
            await ctx.send(embed=embed)
        
    
def setup(bot):  # adding music class as cog
    bot.add_cog(Music(bot))
