from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
import math

import discord
from discord.ext import commands
import jsonpickle
from decouple import config

from ctfbot import ctftime
from ctfbot.data import Chall_board_indicies, Category_and_challenge, Challenges, Event, GlobalData
from ctfbot.helpers import get_event_ctx, get_event_from_channel, update_indicies, move_board, get_embed_from_index, gen_csv_of_solves

JSON_DATA_FILE = Path.cwd() / 'data.json'
MAX_FIELDS = 25
OFFICER_ROLE_ID = int(config('OFFICER_ROLE_ID'))


def iso_to_pretty(iso):
    return datetime.fromisoformat(iso).strftime("%B %d at %I%p")


class CtfCog(commands.Cog):
    data: GlobalData = None

    @staticmethod
    def create_event_embed(event):
        embed = discord.Embed(title=f'{event["title"]} — {event["id"]}',
                              description=event['description'],
                              url=event['ctftime_url'])
        embed.set_thumbnail(url=event['logo'])
        embed.add_field(name='Start', value=iso_to_pretty(event['start']))
        embed.add_field(name='Finish', value=iso_to_pretty(event['finish']))
        if event['weight'] > 1e-9:
            embed.add_field(name='Weight', value=event['weight'])
        return embed

    def __init__(self, bot):
        self.load_data()
        self.bot = bot
        # self.scheduler = sched.scheduler(datetime.utcnow, time.sleep)

    @commands.Cog.listener()
    async def on_command_error(self, ctx, error):
        await ctx.respond("An internal error occurred")

    def write_data(self):
        if not JSON_DATA_FILE.exists():
            JSON_DATA_FILE.touch()
        JSON_DATA_FILE.write_text(
            jsonpickle.encode(
                self.data,
                indent=4,
                keys=True))

    def load_data(self):
        try:
            self.data = jsonpickle.decode(
                JSON_DATA_FILE.read_text(), keys=True)

        except OSError:
            self.data = GlobalData()
            self.write_data()

    @commands.slash_command()
    async def upcoming(self, ctx: discord.ApplicationContext):
        events = ctftime.get_upcoming()
        await ctx.respond(f'Found {len(events)} events in the next week:')
        for event in events:
            await ctx.respond(embed=self.create_event_embed(event))

    @commands.slash_command()
    async def event(
            self,
            ctx: discord.ApplicationContext,
            event_id: discord.Option(int)):
        event = ctftime.get_event(event_id)
        if event is None:
            await ctx.respond("Event not found")
            return
        await ctx.respond(embed=self.create_event_embed(event))

    @commands.slash_command()
    @commands.has_role(OFFICER_ROLE_ID)
    async def register(
            self,
            ctx: discord.ApplicationContext,
            event_id: discord.Option(int),
            category_name: discord.Option(str),
            ctf_verified_required: discord.Option(bool)):
        data = self.data.servers[ctx.guild_id]
        if str(event_id) in data.events or str(
                event_id) in data.archived_events:
            await ctx.respond('You have already registered/played this event!')
            return
        event = ctftime.get_event(event_id)

        if event is None:
            await ctx.respond('Event not found')
            return

        guild: discord.Guild = ctx.guild
        category: discord.CategoryChannel = await guild.create_category(name=category_name + "🚩",
                                                                        position=config('CTF_CATEGORY_POS'))
        data.event_categories[category.id] = event_id
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(
                send_messages=False,
                add_reactions=False,
                manage_threads=False)}
        channel_join: discord.TextChannel = await guild.create_text_channel(name='join-ctf',
                                                                            category=category, overwrites=overwrites)
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(
                read_messages=False)}
        channel_join_logs: discord.TextChannel = await guild.create_text_channel(name='logs',
                                                                                 category=category,
                                                                                 overwrites=overwrites)
        channel_challenges: discord.TextChannel = await guild.create_text_channel(name='challenges',
                                                                                  category=category,
                                                                                  overwrites=overwrites)
        channel_general: discord.TextChannel = await guild.create_text_channel(name='general',
                                                                               category=category,
                                                                               overwrites=overwrites)
        message_chall_board_embed = discord.Embed(
            title=f"{category_name} Challenges",
            description="Current and solved challenges. To add a challenge, use the command /challenge in" +
            f"{channel_general.mention}. To solve a challenge, use the command /solve in a challenge thread." +
            " If you created a challenge by mistake, use the /hide command",
            color=discord.Colour.yellow(),
        )
        message_chall_board: discord.Message = await channel_challenges.send(embed=message_chall_board_embed)
        message_info: discord.Message = await channel_join.send(embed=self.create_event_embed(event))
        message_join_embed = discord.Embed(
            title=f"Join {category_name}",
            description="To join the CTF, react with the :white_check_mark: emoji below!",
            color=discord.Colour.green(),
        )

        message_join: discord.Message = await channel_join.send(embed=message_join_embed)
        await message_join.add_reaction("✅")
        if ctf_verified_required:
            message_verified_embed = discord.Embed(
                title=f"This is a CTF-Verified ✅ event",
                description="You must have the CTF-Verified role to join. "
                + "Please message an admin/officer to obtain this role.",
                color=discord.Colour.green(),
            )
            message_verified: discord.Message = await channel_join.send(embed=message_verified_embed)

        challenges_instance = Challenges()

        data.events[event_id] = Event(
            ctf_verified=ctf_verified_required,
            channel_join=channel_join.id,
            channel_logs=channel_join_logs.id,
            channel_challenges=channel_challenges.id,
            channel_general=channel_general.id,
            join_message=message_join.id,
            challenges=challenges_instance
        )
        await ctx.respond(f"Event Created! Join at {channel_join.mention}")
        self.write_data()

    @commands.slash_command()
    async def connect_to_ctfd(self, ctx: discord.ApplicationContext,
                              username: discord.Option(str)):
        data = self.data.servers[ctx.guild_id]
        data.user_to_ctfd[ctx.author.id] = username
        await ctx.respond(ctx.author.mention +
                          'has connected to the [CTFd](https://ctfd.wolvsec.org/) with username ' +
                          username + ' to get CTF solve points! (/connect_to_ctfd)')
        self.write_data()

    @commands.slash_command()
    @commands.has_role(OFFICER_ROLE_ID)
    async def end_ctf(self, ctx: discord.ApplicationContext):
        data = self.data.servers[ctx.guild_id]
        guild: discord.Guild = ctx.guild
        if (event := get_event_ctx(data, ctx)) is None:
            await ctx.respond('Current channel is not an active CTF')
            return
        join_channel = guild.get_channel(event.channel_join)
        logs_channel = guild.get_channel(event.channel_logs)
        challenge_channel = guild.get_channel(event.channel_challenges)
        general_channel = guild.get_channel(event.channel_general)
        message_end = discord.Embed(
            title=f"This CTF has been ended! 🛑",
            description=f"Thank you for playing! This channel is now publicly viewable.",
            color=discord.Colour.red(),
        )
        await general_channel.send(embed=message_end)
        for message_id in event.challenges.chall_board_msg_ids:
            message_chall_board: discord.Message = await challenge_channel.fetch_message(message_id)
            await general_channel.send(embed=message_chall_board.embeds[0])
        filename = "solves.csv"
        gen_csv_of_solves(event, data, filename)
        with open(filename, 'rb') as file:
            await general_channel.send("Here is the CSV file of solves for each user:", file=discord.File(file, filename))
        category_id = ctx.channel.category_id
        category = guild.get_channel(category_id)
        await general_channel.edit(name=category.name)

        delete_string = "TO BE DELETED ❌"
        await category.edit(name=delete_string)
        await join_channel.edit(name=delete_string)
        await logs_channel.edit(name=delete_string)
        await challenge_channel.edit(name=delete_string)

        archive_category_id = config('ARCHIVE_CATEGORY_ID', cast=int)
        archive_category = guild.get_channel(archive_category_id)

        try:
            await general_channel.edit(category=archive_category)
        except Exception as e:
            await general_channel.send("ERROR: Unable to move to archive category")

        event_id = data.event_categories[category_id]
        data.archived_events.append(event_id)
        del data.events[event_id]
        del data.event_categories[category_id]
        await ctx.respond('Event has been sucessfully ended!')
        self.write_data()

    @commands.slash_command()
    async def team(
            self,
            ctx: discord.ApplicationContext,
            team_id: discord.Option(int)):
        team = ctftime.get_team(team_id)
        if team is None:
            await ctx.respond("Team not found")
            return
        embed = discord.Embed(title=team['primary_alias'])
        columns = defaultdict(str)
        for year in team['rating']:
            rating = team['rating'][year]
            columns['Year'] += year + '\n'
            if 'rating_place' in rating:
                columns['Rank'] += str(rating['rating_place'])
            columns['Rank'] += '\n'
            if 'rating_points' in rating:
                columns['Points'] += f'{rating["rating_points"]:.1f}' + " "
            columns['Points'] += '\n'
        for name, value in columns.items():
            embed.add_field(name=name, value=value)
        embed.set_thumbnail(url=team['logo'])
        await ctx.respond(embed=embed)

    @commands.slash_command()
    async def challenge(
            self,
            ctx: discord.ApplicationContext,
            chal_category: discord.Option(str),
            chal_name: discord.Option(str)):
        banned_strings = ['→', '**', '~~', '@']
        if any(
                banned_string in chal_category or banned_string in chal_name for banned_string in banned_strings):
            await ctx.respond('Invalid character in challenge name/category')
            return
        if len(chal_name) > 50 or len(chal_category) > 50:
            await ctx.respond('Challenge name or can not be longer than 50 characters')
            return
        data = self.data.servers[ctx.guild_id]
        guild: discord.Guild = ctx.guild
        if (event := get_event_ctx(data, ctx)) is None:
            await ctx.respond('Current channel is not an active CTF')
            return
        challenges = event.challenges
        challenge_channel = guild.get_channel(event.channel_challenges)
        if (chal_category, chal_name) in challenges.category_challenge_to_chall_board:
            await ctx.respond('Challenge already exists')
            return

        space_allocated = 2 if chal_category not in challenges.category_to_chall_board else 1
        if (math.floor((challenges.chall_board_field_count - 1 + space_allocated) /
                       MAX_FIELDS) > len(challenges.chall_board_msg_ids) - 1):
            message_chall_board_embed = discord.Embed(
                description="Challenges", color=discord.Colour.yellow())
            message_chall_board: discord.Message = await challenge_channel.send(
                embed=message_chall_board_embed)
            challenges.chall_board_msg_ids.append(message_chall_board.id)

        if chal_category not in challenges.category_to_chall_board:
            last_board_pos = len(challenges.chall_board_msg_ids) - 1
            challenges.category_to_chall_board[chal_category] = Chall_board_indicies(
                challenges.chall_board_field_count, challenges.chall_board_field_count + 1)
            message_chall_board: discord.Message = await challenge_channel.fetch_message(
                challenges.chall_board_msg_ids[last_board_pos])
            embed = message_chall_board.embeds[0]
            embed.add_field(name=f'__**{chal_category}**__', value='')
            challenges.chall_board_field_count += 1
            await message_chall_board.edit(embed=embed)
            index_to_insert = challenges.chall_board_field_count
        else:
            index_to_insert = challenges.category_to_chall_board[
                chal_category].last_challenge_index + 1
            challenges.category_to_chall_board[chal_category].last_challenge_index += 1
            await update_indicies(event, index_to_insert + 1)
            board_shift_needed = (
                math.floor(
                    index_to_insert /
                    MAX_FIELDS) +
                1) != len(
                challenges.chall_board_msg_ids)
            if (board_shift_needed):
                await move_board(event, index_to_insert, challenge_channel)

        message_chall_board: discord.Message = await challenge_channel.fetch_message(
            challenges.chall_board_msg_ids[math.floor(index_to_insert / MAX_FIELDS)])
        embed = message_chall_board.embeds[0]
        challenges.category_challenge_to_chall_board[(
            chal_category, chal_name)] = index_to_insert
        thread = await guild.get_channel(event.channel_general).create_thread(
            name=chal_category + '/' + chal_name, type=discord.ChannelType.public_thread)
        embed.insert_field_at(
            index_to_insert %
            MAX_FIELDS,
            name='',
            value=chal_name +
            ' → ' +
            thread.mention,
            inline=False)
        challenges.chall_board_field_count += 1
        challenges.thread_id_to_challenge[thread.id] = Category_and_challenge(
            chal_category, chal_name)
        await message_chall_board.edit(embed=embed)
        await ctx.respond(f'Challenge created {thread.mention}')
        self.write_data()

    @commands.slash_command()
    async def hide(self, ctx: discord.ApplicationContext):
        data = self.data.servers[ctx.guild_id]
        guild: discord.Guild = ctx.guild
        thread = ctx.channel
        if (event := get_event_ctx(data, ctx)) is None:
            await ctx.respond('Current channel is not an active CTF')
            return
        challenges = event.challenges
        challenge_channel = guild.get_channel(event.channel_challenges)
        if thread.id not in challenges.thread_id_to_challenge:
            await ctx.respond('This is not a CTF thread')
            return
        if thread.id in challenges.solved_challs:
            await ctx.respond('Challenge solved, can not hide')
            return
        category_and_challenge = challenges.thread_id_to_challenge[ctx.channel_id]
        category = category_and_challenge.category
        challenge = category_and_challenge.challenge
        index = challenges.category_challenge_to_chall_board[(
            category, challenge)]
        embed, message_chall_board = await get_embed_from_index(index, challenges, challenge_channel)
        if thread.id in challenges.hidden_challs:
            challenges.hidden_challs.remove(thread.id)
            embed.set_field_at(
                index %
                MAX_FIELDS,
                name='',
                value=challenge +
                ' → ' +
                thread.mention,
                inline=False)
            await thread.edit(archived=False)
            await message_chall_board.edit(embed=embed)
            await ctx.respond(f'Challenge un-hidden. To hide, use /hide again')
        else:
            challenges.hidden_challs.add(thread.id)
            embed.set_field_at(
                index %
                MAX_FIELDS,
                name='',
                value="~~" +
                challenge +
                ' → ' +
                thread.mention +
                '~~ is hidden',
                inline=False)
            await message_chall_board.edit(embed=embed)
            await ctx.respond('Challenge hidden. To unhide, use /hide again')
            await thread.edit(archived=True)
        self.write_data()

    @commands.slash_command()
    async def solve(self, ctx: discord.ApplicationContext,
                    i_have_submitted_the_flag: discord.Option(bool)):
        data = self.data.servers[ctx.guild_id]
        guild: discord.Guild = ctx.guild
        thread = ctx.channel
        if (event := get_event_ctx(data, ctx)) is None:
            await ctx.respond('Current channel is not an active CTF')
            return
        challenges = event.challenges
        challenge_channel = guild.get_channel(event.channel_challenges)
        general_channel = guild.get_channel(event.channel_general)
        if thread.id not in challenges.thread_id_to_challenge:
            await ctx.respond('This is not a CTF thread')
            return
        if thread.id in challenges.solved_challs:
            await ctx.respond('Challenge solved already')
            return
        if thread.id in challenges.hidden_challs:
            await ctx.respond('Challenge hidden, can not solve')
            return
        if not i_have_submitted_the_flag:
            await ctx.respond('You need to submit the flag first!')
            return
        category_and_challenge = challenges.thread_id_to_challenge[ctx.channel_id]
        category = category_and_challenge.category
        challenge = category_and_challenge.challenge
        index = challenges.category_challenge_to_chall_board[(
            category, challenge)]
        embed, message_chall_board = await get_embed_from_index(index, challenges, challenge_channel)

        challenges.solved_challs.add(thread.id)
        embed.set_field_at(
            index %
            MAX_FIELDS,
            name='',
            value="~~" +
            challenge +
            ' → ' +
            thread.mention +
            '~~ has been solved by ' +
            ctx.author.mention +
            '!',
            inline=False)
        await message_chall_board.edit(embed=embed)
        challenges.solves_per_user[ctx.author.id] += 1
        message_challenges_embed = discord.Embed(
            title=f"{category}/{challenge} has been solved! 🎉",
            description=f"{ctx.author.mention} has solved the challenge! Total solves this CTF: **{challenges.solves_per_user[ctx.author.id]}**",
            color=discord.Colour.green(),
        )
        message_solve: discord.Message = await general_channel.send(embed=message_challenges_embed)
        await ctx.respond('Challenge has been solved! 🎉')
        await thread.edit(archived=True)
        self.write_data()

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload):
        if payload.member.bot:
            return
        guild = self.bot.get_guild(payload.guild_id)
        data = self.data.servers[guild.id]
        channel = guild.get_channel(payload.channel_id)
        if (event := get_event_from_channel(data, channel)) is None:
            return
        if (event.join_message != payload.message_id):
            return
        player = await guild.fetch_member(payload.user_id)
        if event.ctf_verified and discord.utils.get(
            guild.roles,
            id=config(
                'CTF_VERIFIED_ROLE_ID',
                cast=int)) not in player.roles:
            player = await self.bot.fetch_user(payload.user_id)
            await player.send('You do not have the CTF-Verified role! Please contact an admin to get this role.')
            return
        await guild.get_channel(event.channel_logs).set_permissions(player, read_messages=True, send_messages=False,
                                                                    add_reactions=False, manage_threads=False)
        await guild.get_channel(event.channel_challenges).set_permissions(player, read_messages=True, send_messages=False,
                                                                          add_reactions=False, manage_threads=False)
        await guild.get_channel(event.channel_general).set_permissions(player, read_messages=True)
        if payload.user_id not in event.challenges.solves_per_user:
            event.challenges.solves_per_user[payload.user_id] = 0
        await guild.get_channel(event.channel_logs).send(f'{player.mention} has joined the CTF!')
        self.write_data()

    @commands.Cog.listener()
    async def on_raw_reaction_remove(self, payload):
        guild = self.bot.get_guild(payload.guild_id)
        data = self.data.servers[guild.id]
        channel = guild.get_channel(payload.channel_id)
        if (event := get_event_from_channel(data, channel)) is None:
            return
        if (event.join_message != payload.message_id):
            return
        player = await guild.fetch_member(payload.user_id)
        await guild.get_channel(event.channel_logs).set_permissions(player, read_messages=False)
        await guild.get_channel(event.channel_join).set_permissions(player, read_messages=False)
        await guild.get_channel(event.channel_general).set_permissions(player, read_messages=False)
        await guild.get_channel(event.channel_logs).send(f'{player.mention} has left the CTF!')
        self.write_data()

    # @commands.slash_command()
    # async def schedule(self, ctx: discord.ApplicationContext):
    #     events = self.data.servers[ctx.guild_id].events
    #     if events:
    #         description = '\n'.join(
    #             ctx.bot.get_channel(
    #                 int(channel_id)).mention for channel_id in events.values())
    #         embed = discord.Embed(
    #             title='Upcoming registered events',
    #             description=description)
    #         await ctx.respond(embed=embed)
    #     else:
    #         await ctx.respond('No upcoming events at the moment')

    # @commands.slash_command()
    # async def reminder(self, ctx: discord.ApplicationContext):
    #     data = self.data.servers[ctx.guild_id]
    #     if ctx.channel_id in data.reminders:
    #         await ctx.respond('Removed reminder for this event')
    #         data.reminders[ctx.channel_id] = datetime.now(timezone.utc)
    #     else:
    #         await ctx.respond('Added reminder for this event')
    #         del data.reminders[ctx.channel_id]
    #     self.write_data()