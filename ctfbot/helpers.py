import csv
import discord
import math

MAX_FIELDS = 25


def get_event_ctx(data, ctx):
    category_id = ctx.channel.category_id
    return get_event(data, category_id)


def get_event_from_channel(data, channel):
    category_id = channel.category_id if channel else None
    return get_event(data, category_id)


def get_event(data, category_id):
    event_categories = data.event_categories
    if category_id is None or category_id not in event_categories:
        return None
    return data.events[event_categories[category_id]]


async def update_indicies(event, index_to_start):
    challenges = event.challenges
    for _, indices in challenges.category_to_chall_board.items():
        if indices.category_name_index >= index_to_start:
            indices.category_name_index += 1
        if indices.last_challenge_index >= index_to_start:
            indices.last_challenge_index += 1
    for category_and_challenge, index in challenges.category_challenge_to_chall_board.items():
        if index >= index_to_start:
            challenges.category_challenge_to_chall_board[category_and_challenge] += 1


async def move_board(event, index_to_insert, challenge_channel):
    challenges = event.challenges
    back_chall_board_index = len(challenges.chall_board_msg_ids) - 1
    start_chall_board_index = math.floor(index_to_insert / MAX_FIELDS)
    message_chall_board: discord.Message = await challenge_channel.fetch_message(
        challenges.chall_board_msg_ids[start_chall_board_index])
    embed = message_chall_board.embeds[0]
    field_value = embed.fields[-1].value
    embed.remove_field(-1)
    await message_chall_board.edit(embed=embed)

    for board in range(
            start_chall_board_index + 1,
            back_chall_board_index - 1):
        message_chall_board: discord.Message = await challenge_channel.fetch_message(
            challenges.chall_board_msg_ids[board])
        embed = message_chall_board.embeds[0]
        field_value_save = embed.fields[-1].value
        embed.remove_field(-1)
        embed.insert_field_at(0, name='', value=field_value, inline=False)
        field_value = field_value_save

    message_chall_board: discord.Message = await challenge_channel.fetch_message(
        challenges.chall_board_msg_ids[back_chall_board_index])
    embed = message_chall_board.embeds[0]
    embed.insert_field_at(0, name='', value=field_value, inline=False)
    await message_chall_board.edit(embed=embed)


async def get_embed_from_index(index, challenges, challenge_channel):
    message_chall_board: discord.Message = await challenge_channel.fetch_message(
        challenges.chall_board_msg_ids[math.floor(index / MAX_FIELDS)])
    embed = message_chall_board.embeds[0]
    return embed, message_chall_board


def gen_csv_of_solves(event, data, filename):
    user_solves = event.challenges.solves_per_user.items()
    data = [
        (user_id, data.user_to_ctfd.get(user_id, 'N/A'), solves)
        for user_id, solves in user_solves
    ]
    with open(filename, mode='w', newline='') as file:
        writer = csv.writer(file)
        writer.writerow(['User ID', 'CTFd Username', 'Solves'])
        writer.writerows(data)
